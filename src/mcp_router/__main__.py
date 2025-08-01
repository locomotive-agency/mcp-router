"""Entry point for stdio subprocess mode"""

import argparse
import asyncio
import os
import uvicorn
from starlette.applications import Starlette

from mcp_router.logging_config import configure_logging, get_logger
from mcp_router.server import run_stdio_mode
from mcp_router.asgi import create_asgi_app
from mcp_router.config import Config
from mcp_router.app import app
from mcp_router.container_manager import ContainerManager
from mcp_router.models import clear_database
from mcp_router.async_utils import EventLoopManager

# Configure logging before anything else
configure_logging(
    log_level=Config.LOG_LEVEL,
    log_format=Config.LOG_FORMAT,
    log_file=Config.LOG_FILE,
    json_logs=Config.LOG_JSON,
)

logger = get_logger(__name__)


async def run_http_mode(asgi_app: Starlette):
    """Run the ASGI application with Uvicorn."""
    loop = asyncio.get_running_loop()
    EventLoopManager.get_instance().set_main_loop(loop)

    config = uvicorn.Config(
        asgi_app,
        host=Config.MCP_HOST,
        port=Config.FLASK_PORT,
        log_config=None,
        access_log=True,
    )
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        # Cleanup on shutdown
        EventLoopManager.get_instance().cleanup()


async def initialize_mcp_router():
    """Initialize MCP Router resources on startup."""
    logger.info("Initializing MCP Router resources...")

    # Initialize container manager
    container_manager = ContainerManager(app)

    try:
        # Initialize and build all servers
        await container_manager.initialize_and_build_servers()

        # Mount all built servers to the router
        mcp_manager = app.mcp_manager
        await container_manager.mount_built_servers(mcp_manager)

        logger.info("MCP Router initialization completed successfully")

    except Exception as e:
        logger.error(f"Failed to initialize MCP Router: {e}")
        exit(1)


async def main():
    """Main entry point for MCP Router application."""
    parser = argparse.ArgumentParser(description="MCP Router")
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "http"],
        default=os.environ.get("MCP_TRANSPORT", "http").lower(),
        help="Transport mode (stdio or http). Overrides MCP_TRANSPORT env var.",
    )
    parser.add_argument(
        "--clear-db",
        action="store_true",
        help="Clear the database before starting (useful for fresh deployments)",
    )
    args = parser.parse_args()

    transport_mode = args.transport

    # Update the Config to reflect the actual runtime transport mode
    Config.MCP_TRANSPORT = transport_mode

    # Clear database if requested
    if args.clear_db:
        logger.info("Clear database flag detected")
        with app.app_context():
            clear_database()
            logger.info("Database cleared successfully")

    asgi_app = await create_asgi_app()

    # Initialize resources
    await initialize_mcp_router()

    if transport_mode == "stdio":
        logger.info("Starting MCP Router in STDIO mode...")
        await run_stdio_mode()
    elif transport_mode == "http":
        logger.info("Starting MCP Router in HTTP mode...")
        await run_http_mode(asgi_app)
    else:
        # This should not be reachable due to argparse `choices`
        raise ValueError(f"Invalid transport mode: {transport_mode}")


if __name__ == "__main__":
    asyncio.run(main())
