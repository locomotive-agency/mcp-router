"""Web server entry point"""

import logging
import sys
from mcp_router.app import app
from mcp_router.models import db
from mcp_router.config import Config

logger = logging.getLogger(__name__)


def check_docker_availability() -> bool:
    """Check if Docker is available and accessible.

    Returns:
        True if Docker is available, False otherwise
    """
    try:
        import docker

        client = docker.from_env()
        client.ping()
        logger.info("Docker is available and accessible")
        return True
    except ImportError:
        logger.error(
            "Docker Python library is not installed. Please install it with: pip install docker"
        )
        return False
    except Exception as e:
        if "permission denied" in str(e).lower():
            logger.error("Docker is installed but not accessible. Please ensure:")
            logger.error("  - Docker service is running")
            logger.error("  - Current user has permission to access Docker")
            logger.error("  - Try: sudo usermod -aG docker $USER (then restart)")
        else:
            logger.error(f"Docker is not available: {e}")
            logger.error("Please ensure Docker is installed and running")
        return False


def main() -> None:
    """Run the Flask web server"""
    # Check Docker availability early
    if not check_docker_availability():
        logger.error("=" * 60)
        logger.error("CRITICAL: Docker is required for MCP Router functionality")
        logger.error("MCP Router uses Docker containers to run MCP servers safely")
        logger.error("")
        logger.error("For deployment environments without Docker:")
        logger.error("  - Use a platform that supports Docker (Docker, Railway, etc.)")
        logger.error("  - Or install Docker in your deployment environment")
        logger.error("=" * 60)
        sys.exit(1)

    # Ensure database is created
    with app.app_context():
        db.create_all()
        logger.info("Database initialized")

    # (Image preparation now handled in mcp_router.app)

    port = Config.FLASK_PORT
    # Run the development server
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"])


if __name__ == "__main__":
    main()
