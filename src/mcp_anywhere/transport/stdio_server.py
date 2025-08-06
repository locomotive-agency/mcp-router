"""
STDIO transport module for running MCP Anywhere in headless mode.

This module runs the application in a headless stdio mode for terminal-based 
interaction, while concurrently serving the web UI for management.
"""

import asyncio
import uvicorn
from typing import Optional

from mcp_anywhere.web.app import create_app
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


async def run_stdio_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    log_level: str = "info"
) -> None:
    """
    Run the application in a headless stdio mode for terminal-based interaction,
    while concurrently serving the web UI for management.
    """
    logger.info(f"Starting STDIO server with background web UI on {host}:{port}")

    # Create app with stdio transport mode (no JWT on MCP endpoints)
    app = create_app(transport_mode="stdio")
    startup_complete = asyncio.Event()

    # Store the original lifespan handler to delegate to it
    original_lifespan = app.router.lifespan_context
    original_asgi_app = app
    
    async def lifespan_extending_app(scope, receive, send):
        if scope['type'] == 'lifespan':
            # Create a custom receive function to intercept startup.complete
            async def custom_receive():
                message = await receive()
                if message['type'] == 'lifespan.startup.complete':
                    startup_complete.set()
                return message
            
            # Delegate to the original lifespan handler with our custom receive
            await app.router.lifespan(scope, custom_receive, send)
        else:
            await original_asgi_app(scope, receive, send)

    # Replace the app's __call__ method to use our extending app
    app.__call__ = lifespan_extending_app

    config = uvicorn.Config(
        app, host=host, port=port, log_level=log_level.lower()
    )
    server = uvicorn.Server(config=config)
    server_task = asyncio.create_task(server.serve())

    await startup_complete.wait()
    logger.info("Background web UI has started and lifespan is complete.")

    try:
        mcp_manager = app.state.mcp_manager
        if mcp_manager is None:
            raise AttributeError("MCP manager not found in application state")

        stdio_task = asyncio.create_task(mcp_manager.router.run(transport="stdio"))
        logger.info("STDIO transport task created")

        await asyncio.gather(server_task, stdio_task)

    except asyncio.CancelledError:
        logger.info("STDIO server tasks cancelled")
        server.should_exit = True
        await server.shutdown()
        raise
    except Exception as e:
        logger.error(f"Failed to start STDIO server: {e}")
        server.should_exit = True
        await server.shutdown()
        raise
