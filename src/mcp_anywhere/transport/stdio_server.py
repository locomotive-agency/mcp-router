"""STDIO transport module for running MCP Anywhere admin web UI only.

This server provides:
- Web UI for management at the specified host:port
- Container build/initialization lifecycle (handled by app lifespan)

It does NOT start MCP over STDIO. To connect via STDIO, use:
    mcp-anywhere connect
which leverages the stdio gateway.
"""

import uvicorn

from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import configure_logging, get_logger
from mcp_anywhere.web.app import create_app


async def run_stdio_server(host: str = None, port: int = None) -> None:
    """Run MCP Anywhere with the admin UI only (no MCP over STDIO).

    Args:
        host: Host address for the web UI (defaults to Config.DEFAULT_HOST)
        port: Port number for the web UI (defaults to Config.DEFAULT_PORT)
    """
    # Use Config defaults if not provided
    if host is None:
        host = Config.DEFAULT_HOST
    if port is None:
        port = Config.DEFAULT_PORT

    # Configure logging for STDIO admin UI mode
    configure_logging(
        log_level=Config.LOG_LEVEL,
        log_format=Config.LOG_FORMAT,
        log_file=Config.LOG_FILE,
        json_logs=Config.LOG_JSON,
    )

    logger = get_logger(__name__)
    logger.info("Starting MCP Anywhere Server with STDIO admin UI")
    logger.info(f"Web UI: http://{host}:{port}/")
    logger.info("Note: MCP over STDIO is available via 'mcp-anywhere connect'")

    try:
        # Create the Starlette application in stdio mode (no OAuth on MCP)
        app = await create_app(transport_mode="stdio")

        # Configure uvicorn for the web UI
        config = uvicorn.Config(
            app, host=host, port=port, log_level=Config.LOG_LEVEL.lower()
        )
        server = uvicorn.Server(config=config)

        # Run the server
        await server.serve()

    except (RuntimeError, ValueError, OSError) as e:
        logger.exception(f"Failed to start STDIO admin UI server: {e}")
        raise
