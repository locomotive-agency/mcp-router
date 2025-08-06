"""HTTP transport module for running MCP Anywhere as a web server."""

import uvicorn

from mcp_anywhere.web.app import create_app
from mcp_anywhere.logging_config import configure_logging, get_logger
from mcp_anywhere.config import Config


async def run_http_server(host: str = "0.0.0.0", port: int = 8000, log_level: str = "info") -> None:
    """
    Run the MCP Anywhere as an HTTP web server using uvicorn.

    Args:
        host: Host address to bind to
        port: Port number to bind to
        log_level: Logging level for uvicorn
    """
    # Configure logging for HTTP server mode
    configure_logging(
        log_level=Config.LOG_LEVEL,
        log_format=Config.LOG_FORMAT,
        log_file=Config.LOG_FILE,
        json_logs=Config.LOG_JSON,
    )

    logger = get_logger(__name__)
    logger.info(f"Starting MCP Anywhere Server with HTTP transport")
    logger.info(f"Web UI: http://{host}:{port}/")
    logger.info(f"MCP Endpoint: http://{host}:{port}/mcp (with OAuth)")

    try:
        # Create the Starlette application with http transport mode
        app = create_app(transport_mode="http")

        # Create uvicorn server configuration
        config = uvicorn.Config(app, host=host, port=port, log_level=log_level)

        # Create and run the server
        server = uvicorn.Server(config)
        await server.serve()

    except (RuntimeError, ValueError, OSError) as e:
        logger.error(f"Failed to start HTTP server: {e}")
        raise
