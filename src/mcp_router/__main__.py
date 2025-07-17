"""Entry point for stdio subprocess mode"""

import argparse
import os
import logging
import uvicorn

from mcp_router.server import run_stdio_mode
from mcp_router.asgi import asgi_app
from mcp_router.config import Config

logger = logging.getLogger(__name__)


def run_http_mode():
    """Run the ASGI application with Uvicorn."""
    uvicorn.run(
        asgi_app,
        host=Config.MCP_HOST,
        port=Config.FLASK_PORT,
        log_level=Config.MCP_LOG_LEVEL.lower(),
    )


def main():
    """
    Main entry point for the MCP Router application.
    Parses command-line arguments and environment variables to select
    and run the appropriate transport mode (HTTP or STDIO).
    """
    parser = argparse.ArgumentParser(description="MCP Router")
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "http"],
        default=os.environ.get("MCP_TRANSPORT", "http").lower(),
        help="Transport mode (stdio or http). Overrides MCP_TRANSPORT env var.",
    )
    args = parser.parse_args()

    transport_mode = args.transport

    # Update the Config to reflect the actual runtime transport mode
    Config.MCP_TRANSPORT = transport_mode

    if transport_mode == "stdio":
        logger.info("Starting MCP Router in STDIO mode...")
        run_stdio_mode()
    elif transport_mode == "http":
        logger.info("Starting MCP Router in HTTP mode...")
        run_http_mode()
    else:
        # This should not be reachable due to argparse `choices`
        raise ValueError(f"Invalid transport mode: {transport_mode}")


if __name__ == "__main__":
    main()
