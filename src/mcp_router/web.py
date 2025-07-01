"""Web server entry point"""

import logging
import os
import sys
import threading
from mcp_router.app import app
from mcp_router.models import db
from mcp_router.container_manager import ContainerManager
from mcp_router.config import Config

logger = logging.getLogger(__name__)


def check_docker_availability():
    """Check if Docker is available and accessible."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        logger.info("Docker is available and accessible")
        return True
    except ImportError:
        logger.error("Docker Python library is not installed. Please install it with: pip install docker")
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


def prepare_docker_images():
    """
    Checks for and pulls the default Docker images in the background
    to avoid delaying application startup.
    """
    # We need an app context to access the config and create the manager
    with app.app_context():
        logger.info("Starting background preparation of Docker images...")
        manager = ContainerManager(app)
        default_images = [Config.MCP_PYTHON_IMAGE, Config.MCP_NODE_IMAGE]
        for image in default_images:
            manager.ensure_image_exists(image)
        logger.info("Background image preparation complete.")


def main():
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
    
    # Start image preparation in background thread
    prepare_thread = threading.Thread(target=prepare_docker_images, daemon=True)
    prepare_thread.start()
    
    port = int(os.environ.get('FLASK_PORT', 8000))
    # Run the development server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=app.config['DEBUG']
    )

if __name__ == "__main__":
    main() 