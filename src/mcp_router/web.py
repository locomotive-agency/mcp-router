"""Web server entry point"""

import logging

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
