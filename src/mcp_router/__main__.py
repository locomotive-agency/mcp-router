"""Entry point for stdio subprocess mode"""

import argparse
import asyncio
import os
import uvicorn

from mcp_router.logging_config import configure_logging, get_logger
from mcp_router.server import run_stdio_mode
from mcp_router.asgi import asgi_app
from mcp_router.config import Config
from mcp_router.app import app
from mcp_router.container_manager import ContainerManager
from mcp_router.models import MCPServer, db, clear_database

# Configure logging before anything else
configure_logging(
    log_level=Config.LOG_LEVEL,
    log_format=Config.LOG_FORMAT,
    log_file=Config.LOG_FILE,
    json_logs=Config.LOG_JSON,
)

logger = get_logger(__name__)


async def run_http_mode():
    """Run the ASGI application with Uvicorn."""
    config = uvicorn.Config(
        asgi_app,
        host=Config.MCP_HOST,
        port=Config.FLASK_PORT,
        log_config=None,
        access_log=True,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def initialize_mcp_router():
    """
    Initialize MCP Router resources on startup.

    - Checks for Docker daemon
    - Ensures base Docker images exist
    - Creates/verifies system servers (like mcp-python-interpreter)
    - Rebuilds any servers that are pending or have missing images
    - Mounts all 'ready' servers to the running router
    """
    logger.info("Initializing MCP Router resources...")

    with app.app_context():
        # Initialize container manager
        container_manager = ContainerManager(app)

        # 1. Check if Docker is running
        if not container_manager.check_docker_running():
            logger.error("Docker is not running. Please start Docker and restart the application.")
            exit(1)
        logger.info("Docker is running.")

        # 2. Ensure base images exist
        try:
            logger.info("Ensuring base Docker images exist...")
            container_manager.ensure_image_exists(Config.MCP_NODE_IMAGE)
            container_manager.ensure_image_exists(Config.MCP_PYTHON_IMAGE)
            logger.info("Base Docker images are available.")
        except Exception as e:
            logger.error(f"Failed to ensure base images: {e}. Please check your Docker setup.")
            exit(1)

        # 3. Ensure Python interpreter server exists in the database
        sandbox_server = MCPServer.query.filter_by(
            github_url="https://github.com/yzfly/mcp-python-interpreter"
        ).first()
        if not sandbox_server:
            logger.info("Creating mcp-python-interpreter system server in database.")
            sandbox_server = MCPServer(
                name="Python Interpreter",
                github_url="https://github.com/yzfly/mcp-python-interpreter",
                description="Execute Python code in a secure sandbox environment",
                runtime_type="uvx",
                install_command="pip install mcp-python-interpreter",
                start_command="uvx mcp-python-interpreter --dir /data/python-sandbox",
                is_active=True,
                build_status="pending",
            )
            db.session.add(sandbox_server)
            db.session.commit()

        # 4. Find all active servers and rebuild them all on startup
        logger.info("Rebuilding all active server images on startup...")
        all_active_servers = MCPServer.query.filter_by(is_active=True).all()

        if all_active_servers:
            logger.info(f"Found {len(all_active_servers)} active servers to rebuild.")
            for server in all_active_servers:
                try:
                    logger.info(f"Building image for {server.name}...")
                    server.build_status = "building"
                    server.build_logs = "Building..."
                    db.session.commit()

                    image_tag = container_manager.build_server_image(server)
                    server.build_status = "built"
                    server.image_tag = image_tag
                    server.build_logs = f"Successfully built image {image_tag}"
                    db.session.commit()
                    logger.info(f"Successfully built image for {server.name}.")
                except Exception as e:
                    logger.error(f"Failed to build {server.name}: {e}")
                    server.build_status = "failed"
                    server.build_logs = str(e)
                    db.session.commit()
        else:
            logger.info("No active servers found to build.")

        # 5. Mount all successfully built servers to the router
        built_servers = MCPServer.query.filter_by(is_active=True, build_status="built").all()
        if built_servers:
            logger.info(f"Mounting {len(built_servers)} built servers...")
            dynamic_manager = app.mcp_router._dynamic_manager
            for server in built_servers:
                try:
                    await dynamic_manager.add_server(server)
                except Exception as e:
                    logger.error(f"Failed to mount server '{server.name}': {e}")
        else:
            logger.info("No built servers to mount.")


async def main():
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

    # Initialize resources
    await initialize_mcp_router()

    if transport_mode == "stdio":
        logger.info("Starting MCP Router in STDIO mode...")
        run_stdio_mode()
    elif transport_mode == "http":
        logger.info("Starting MCP Router in HTTP mode...")
        await run_http_mode()
    else:
        # This should not be reachable due to argparse `choices`
        raise ValueError(f"Invalid transport mode: {transport_mode}")


if __name__ == "__main__":
    asyncio.run(main())
