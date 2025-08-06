"""
STDIO transport module for running MCP Anywhere server with STDIO MCP transport.

This module runs the full application (web UI + MCP manager) but provides MCP
over STDIO transport instead of HTTP. This is different from the lightweight
gateway which doesn't include the web UI.
"""

import asyncio
import uvicorn

from mcp_anywhere.web.app import create_app
from mcp_anywhere.logging_config import configure_logging, get_logger
from mcp_anywhere.config import Config


async def run_stdio_server(
    host: str = "0.0.0.0", port: int = 8000, log_level: str = "info"
) -> None:
    """
    Run the full MCP Anywhere server with STDIO transport for MCP.

    This provides:
    - Web UI for management at the specified host:port
    - MCP protocol over STDIO (no OAuth required)

    Args:
        host: Host address for the web UI
        port: Port number for the web UI
        log_level: Logging level for uvicorn
    """
    # Configure logging for STDIO server mode
    configure_logging(
        log_level=Config.LOG_LEVEL,
        log_format=Config.LOG_FORMAT,
        log_file=Config.LOG_FILE,
        json_logs=Config.LOG_JSON,
    )

    logger = get_logger(__name__)
    logger.info(f"Starting MCP Anywhere Server with STDIO transport")
    logger.info(f"Web UI: http://{host}:{port}/")
    logger.info(f"MCP: Available over stdio (no OAuth required)")

    # Create app with stdio transport mode (no OAuth on MCP)
    app = create_app(transport_mode="stdio")
    startup_complete = asyncio.Event()

    # Store the original lifespan handler to delegate to it
    original_lifespan = app.router.lifespan_context
    original_asgi_app = app

    async def lifespan_extending_app(scope, receive, send):
        if scope["type"] == "lifespan":
            # Create a custom receive function to intercept startup.complete
            async def custom_receive():
                message = await receive()
                if message["type"] == "lifespan.startup.complete":
                    startup_complete.set()
                return message

            # Delegate to the original lifespan handler with our custom receive
            await app.router.lifespan(scope, custom_receive, send)
        else:
            await original_asgi_app(scope, receive, send)

    # Replace the app's __call__ method to use our extending app
    app.__call__ = lifespan_extending_app

    # Configure uvicorn for the web UI
    config = uvicorn.Config(app, host=host, port=port, log_level=log_level.lower())
    server = uvicorn.Server(config=config)
    server_task = asyncio.create_task(server.serve())

    # Wait for startup to complete
    await startup_complete.wait()
    logger.info("Web UI has started and lifespan is complete.")

    try:
        # Get the MCP manager from app state
        mcp_manager = app.state.mcp_manager
        if mcp_manager is None:
            raise AttributeError("MCP manager not found in application state")

        # Start the STDIO transport for MCP
        stdio_task = asyncio.create_task(mcp_manager.router.run(transport="stdio"))
        logger.info("STDIO MCP transport started")

        # Run both the web server and STDIO transport concurrently
        await asyncio.gather(server_task, stdio_task)

    except asyncio.CancelledError:
        logger.info("STDIO server tasks cancelled")
        server.should_exit = True
        await server.shutdown()
        raise
    except (RuntimeError, ValueError, OSError) as e:
        logger.error(f"Failed to start STDIO server: {e}")
        server.should_exit = True
        await server.shutdown()
        raise
