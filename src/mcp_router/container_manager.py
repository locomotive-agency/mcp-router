"""
Manages container lifecycle for MCP servers in any language.

Supports:
- npx: Node.js/JavaScript servers
- uvx: Python servers
- docker: Any language via Docker images
"""

import logging
from typing import Dict, Any, Optional
from flask import Flask
from llm_sandbox import SandboxSession
from mcp_router.models import get_server_by_id, MCPServer
from mcp_router.config import Config
from docker import DockerClient
from docker.errors import ImageNotFound


logger = logging.getLogger(__name__)


class ContainerManager:
    """Manages container lifecycle with language-agnostic sandbox support"""

    def __init__(self, app: Optional[Flask] = None):
        """Initialize with optional Flask app for database access"""
        self.app = app
        self._containers: Dict[str, SandboxSession] = {}
        # Get Docker host from config
        self.docker_host = Config.DOCKER_HOST
        # Get Python image from config
        self.python_image = Config.MCP_PYTHON_IMAGE
        # Get Node.js image from config
        self.node_image = Config.MCP_NODE_IMAGE
        # Custom sandbox image
        self.sandbox_image_template = "mcp-router-python-sandbox"
        # Docker client
        self.docker_client: DockerClient = DockerClient.from_env()

    def ensure_image_exists(self, image_name: str) -> None:
        """Checks if a Docker image exists locally and pulls it if not.

        Args:
            image_name: Docker image name to check/pull
        """
        try:
            self.docker_client.images.get(image_name)
            logger.info(f"Image '{image_name}' already exists locally.")
        except ImageNotFound:
            logger.info(f"Image '{image_name}' not found locally. Pulling...")
            try:
                self.docker_client.images.pull(image_name)
                logger.info(f"Successfully pulled image '{image_name}'.")
            except Exception as e:
                logger.error(f"Failed to pull image '{image_name}': {e}")

    def _get_env_vars(self, server: MCPServer) -> Dict[str, str]:
        """Extract environment variables from server configuration"""
        env_vars = {}
        for env_var in server.env_variables:
            if env_var.get("value"):
                env_vars[env_var["key"]] = env_var["value"]
        return env_vars

    def _create_sandbox_session(self, server: MCPServer) -> SandboxSession:
        """Create a sandbox session based on server runtime type"""
        env_vars = self._get_env_vars(server)

        if server.runtime_type == "npx":
            # Node.js/JavaScript servers
            return SandboxSession(
                lang="javascript",
                runtime="node",
                image=self.node_image,  # Use configured Node image
                timeout=60,  # Increased from 30 to 60 seconds
                env_vars=env_vars,
                docker_host=self.docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        elif server.runtime_type == "uvx":
            # Python servers
            return SandboxSession(
                lang="python",
                image=self.python_image,
                timeout=60,  # Increased from 30 to 60 seconds
                env_vars=env_vars,
                docker_host=self.docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        elif server.runtime_type == "docker":
            # Any language via Docker
            return SandboxSession(
                image=server.start_command,
                timeout=60,  # Increased from 30 to 60 seconds
                env_vars=env_vars,
                docker_host=self.docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        else:
            raise ValueError(f"Unsupported runtime type: {server.runtime_type}")

    def test_server(self, server_id: str) -> Dict[str, Any]:
        """
        Test a specific MCP server by running its start command.

        Args:
            server_id: The ID of the server to test

        Returns:
            Dict containing test results with status, output, and error details
        """
        if self.app:
            with self.app.app_context():
                server = get_server_by_id(server_id)
        else:
            server = get_server_by_id(server_id)

        if not server:
            return {"status": "error", "message": f"Server {server_id} not found"}

        logger.info(f"Testing server: {server.name} ({server.runtime_type})")

        try:
            # Create sandbox session
            session = self._create_sandbox_session(server)

            with session:
                # Run installation command if needed
                if server.install_command:
                    # For npm installations, clean cache first to avoid idealTree errors
                    if server.runtime_type == "npx" and "npm install" in server.install_command:
                        logger.info("Cleaning npm cache to avoid conflicts")
                        cache_clean_result = session.execute_command("npm cache clean --force")
                        if cache_clean_result.exit_code != 0:
                            logger.warning(f"npm cache clean failed: {cache_clean_result.stderr}")

                    logger.info(f"Running install command: {server.install_command}")
                    result = session.execute_command(server.install_command)
                    if result.exit_code != 0:
                        # For npm errors, provide more detailed error message
                        error_msg = "Installation failed"
                        if "idealTree" in result.stderr:
                            error_msg += " (npm error: Tracker 'idealTree' already exists - this is typically a transient npm issue)"
                        return {"status": "error", "message": error_msg, "stderr": result.stderr}

                # Run the start command
                logger.info(f"Running start command: {server.start_command}")
                result = session.execute_command(server.start_command)

                return {
                    "status": "success" if result.exit_code == 0 else "error",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                }

        except Exception as e:
            logger.error(f"Error testing server {server_id}: {e}")
            return {"status": "error", "message": str(e)}

    def build_python_sandbox_image(self, force: bool = False) -> Dict[str, Any]:
        """Builds a custom python sandbox image with common libraries pre-installed.

        Args:
            force: Whether to force rebuild even if image exists

        Returns:
            Dictionary with status and message of the build operation
        """
        try:
            # For this library, we "build" by creating a named template container
            # that has the dependencies pre-installed.
            logger.info("Building/Updating the Python sandbox template container...")

            with SandboxSession(
                lang="python",
                image=self.python_image,
                template_name=self.sandbox_image_template,
                commit_container=True,  # This is key: saves the state after the session
                timeout=300,  # 5 minutes for build
                docker_host=self.docker_host,
            ) as session:
                logger.info("Installing common data science libraries into the template...")
                default_libs = ["pandas", "numpy", "matplotlib", "seaborn", "scipy"]
                install_cmd = f"pip install --no-cache-dir {' '.join(default_libs)}"
                result = session.execute_command(install_cmd)

                if result.exit_code != 0:
                    logger.error(
                        f"Failed to install libraries for sandbox template: {result.stderr}"
                    )
                    return {
                        "status": "error",
                        "message": "Library installation failed.",
                        "stderr": result.stderr,
                    }

                logger.info(
                    "Libraries installed. The container state will be committed automatically."
                )

            logger.info(
                f"Successfully built/updated sandbox template: '{self.sandbox_image_template}'"
            )
            return {"status": "success", "message": "Sandbox template updated successfully."}
        except Exception as e:
            logger.error(f"Error building custom sandbox image: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def pull_server_image(self, server_id: str) -> Dict[str, Any]:
        """Pulls the Docker image for a specific server.

        Args:
            server_id: ID of the server to pull image for

        Returns:
            Dictionary with status and image information
        """
        if self.app:
            with self.app.app_context():
                server = get_server_by_id(server_id)
        else:
            server = get_server_by_id(server_id)

        if not server:
            return {"status": "error", "message": f"Server {server_id} not found"}

        image_name = ""
        if server.runtime_type == "npx":
            image_name = self.node_image
        elif server.runtime_type == "uvx":
            image_name = self.python_image
        elif server.runtime_type == "docker":
            image_name = server.start_command
        else:
            return {
                "status": "error",
                "message": f"Unsupported runtime type: {server.runtime_type}",
            }

        try:
            logger.info(f"Pulling image '{image_name}' for server '{server.name}'...")
            self.docker_client.images.pull(image_name)
            logger.info(f"Successfully pulled image: {image_name}")
            return {"status": "success", "image": image_name}
        except Exception as e:
            logger.error(f"Failed to pull image '{image_name}': {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
