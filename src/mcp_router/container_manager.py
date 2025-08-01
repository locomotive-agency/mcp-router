"""
Manages container lifecycle for MCP servers in any language.

Supports:
- npx: Node.js/JavaScript servers
- uvx: Python servers
"""

from typing import Dict, Any, Optional, List
from flask import Flask
from llm_sandbox import SandboxSession
from mcp_router.models import MCPServer, db, get_active_servers, get_built_servers
from mcp_router.config import Config
from docker import DockerClient
from docker.errors import ImageNotFound
import time
import shlex
import json
import os
from mcp_router.logging_config import get_logger

logger = get_logger(__name__)


class ContainerManager:
    """Manages container lifecycle with language-agnostic sandbox support"""

    def __init__(self, app: Optional[Flask] = None):
        """Initialize with optional Flask app for database access"""
        self.app = app

        self.docker_host = Config.DOCKER_HOST
        # Get Python image from config
        self.python_image = Config.MCP_PYTHON_IMAGE
        # Get Node.js image from config
        self.node_image = Config.MCP_NODE_IMAGE
        # Docker client with extended timeout for large operations
        self.docker_client: DockerClient = DockerClient.from_env(timeout=Config.DOCKER_TIMEOUT)

    def _check_docker_running(self) -> bool:
        """Check if the Docker daemon is running."""
        try:
            self.docker_client.ping()
            return True
        except Exception:
            return False

    def get_image_tag(self, server: MCPServer) -> str:
        """Generate the Docker image tag for a server."""
        return f"mcp-router/server-{server.id}"

    def _ensure_image_exists(self, image_name: str) -> None:
        """Checks if a Docker image exists locally and pulls it if not."""
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

    def _parse_install_command(self, server: MCPServer) -> str:
        """Parse and validate install command for container execution."""
        cmd = server.install_command.strip()

        if not cmd:
            return ""

        # Basic validation - ensure it's not trying to do something harmful
        if any(danger in cmd.lower() for danger in ["rm -rf", "dd if=", "> /dev/"]):
            logger.warning(f"Potentially dangerous install command blocked: {cmd}")
            return ""

        cmd_parts = shlex.split(cmd)

        # For npx servers, we might need to transform the command
        if server.runtime_type == "npx":
            # If user provides "npx @package", transform to proper install
            if cmd_parts[0] == "npx":
                package = cmd_parts[1].strip()
                # Add --no-audit flag to speed up npm install
                return f"npm install -g --no-audit {package}"
            # If already npm install, add optimization flags
            elif cmd_parts[0] == "npm" and cmd_parts[1] == "install":
                # Add --no-audit if not already present
                if "--no-audit" not in cmd:
                    return cmd.replace("npm install", "npm install --no-audit")
                return cmd
            # Otherwise assume it's a package name
            else:
                return f"npm install -g --no-audit {cmd_parts[0]}"

        # For Python/uvx, ensure uv is installed first
        if server.runtime_type == "uvx":
            # For uvx servers, we need to install uv first
            # Since SandboxSession might not handle shell operators well,
            # we'll install uv separately in the build process
            return cmd if cmd.strip() else ""

        # For other Python packages, return as-is since pip handles their own parsing
        return cmd

    def _parse_start_command(self, server: MCPServer) -> List[str]:
        """Parse start command into Docker command array."""
        cmd = server.start_command.strip()

        if not cmd:
            return []

        try:
            # Use shlex to properly parse the command
            parts = shlex.split(cmd)

            if server.runtime_type in ["npx", "uvx"]:
                # For stdio-based servers, ensure stdio transport is specified
                if "stdio" not in parts:
                    parts.append("stdio")
                return parts
            else:
                # For other types, return parsed command as-is
                return parts

        except ValueError as e:
            # shlex parsing failed (e.g., unmatched quotes)
            logger.error(f"Failed to parse command '{cmd}': {e}")
            # Fall back to simple split
            return cmd.split()

    def test_server(self, server: MCPServer) -> Dict[str, Any]:
        """Test server by verifying its Docker image exists and can start."""
        logger.info(f"Testing server: {server.name}")
        start_time = time.time()

        try:
            image_tag = self.get_image_tag(server)

            # First, verify image exists
            try:
                self.docker_client.images.get(image_tag)
            except ImageNotFound:
                return {
                    "status": "error",
                    "message": f"Docker image not found: {image_tag}",
                    "duration": time.time() - start_time,
                }

            # Get the actual command we'll run
            run_command = self._parse_start_command(server)
            if not run_command:
                return {
                    "status": "error",
                    "message": "No start command configured",
                    "duration": time.time() - start_time,
                }

            # Simple test: Run the container briefly and see if it starts
            # For MCP servers, they should stay running waiting for input
            container = None
            try:
                container = self.docker_client.containers.run(
                    image_tag,
                    command=run_command,
                    detach=True,
                    remove=False,  # We'll clean up manually
                    mem_limit="256m",
                    cpu_quota=50000,  # 0.5 CPU
                    environment=self._get_env_vars(server),
                    stdin_open=True,  # MCP servers need stdin
                    tty=False,
                )

                # Wait a moment to see if it crashes immediately
                time.sleep(1)

                # Check if still running
                container.reload()
                is_running = container.status == "running"

                # Get logs for diagnostics
                logs = container.logs(tail=20).decode("utf-8", errors="ignore")

                # Clean up
                try:
                    container.stop(timeout=2)
                    container.remove()
                except Exception:
                    pass

                if is_running:
                    return {
                        "status": "success",
                        "message": "Server started successfully",
                        "duration": time.time() - start_time,
                        "image_tag": image_tag,
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Server exited immediately. Check logs.",
                        "logs_preview": logs[:200] if logs else "No logs",
                        "duration": time.time() - start_time,
                    }

            finally:
                # Ensure cleanup even if something goes wrong
                if container:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Error testing server {server.name}: {e}")
            return {
                "status": "error",
                "message": f"Test failed: {str(e)}",
                "duration": time.time() - start_time,
            }

    def build_server_image(self, server: MCPServer) -> str:
        """Build a Docker image for an MCP server with dependencies pre-installed."""
        image_tag = self.get_image_tag(server)

        logger.info(f"Building Docker image for server {server.name} ({server.runtime_type})")

        try:
            # Determine base image and install command
            if server.runtime_type == "npx":
                lang = "javascript"
                base_image = self.node_image
            elif server.runtime_type == "uvx":
                lang = "python"
                base_image = self.python_image
            else:
                raise ValueError(f"Unsupported runtime type: {server.runtime_type}")

            # Parse the install command for container execution
            install_command = self._parse_install_command(server)

            # Use LLM-Sandbox to create container and install dependencies
            with SandboxSession(
                lang=lang,
                image=base_image,
                client=self.docker_client,
                keep_template=True,
                commit_container=True,
                docker_host=self.docker_host,
                execution_timeout=Config.DOCKER_TIMEOUT,  # Use configured timeout
                default_timeout=Config.DOCKER_TIMEOUT,  # Use configured timeout
                runtime_config={
                    "mem_limit": "512m",  # Reduced memory to work within Fly.io constraints
                    "cpu_quota": 100000,  # 1 CPU to speed up builds
                },
            ) as session:
                # Progress logging
                logger.info(f"Step 1/3: Setting up container for {server.name}...")

                # For uvx servers, install uv first
                if server.runtime_type == "uvx":
                    logger.info("Installing uv for uvx server...")
                    uv_result = session.execute_command("pip install uv")
                    if uv_result.exit_code != 0:
                        raise RuntimeError(f"Failed to install uv: {uv_result.stderr}")
                    logger.info("uv installed successfully")

                # Create Python sandbox directory for mcp-python-interpreter if this is a uvx server
                if (
                    server.runtime_type == "uvx" and "mcp-python-interpreter" in server.start_command
                ):
                    logger.info("Creating Python sandbox directory for mcp-python-interpreter...")
                    mkdir_result = session.execute_command(
                        "mkdir -p /data/python-sandbox && chmod 755 /data/python-sandbox"
                    )
                    if mkdir_result.exit_code != 0:
                        logger.warning(f"Failed to create sandbox directory: {mkdir_result.stderr}")

                # Install dependencies only if install_command is not empty
                if install_command:
                    logger.info(f"Step 2/3: Installing {server.name} dependencies...")
                    logger.info(f"Running: {install_command}")
                    result = session.execute_command(install_command)

                    if result.exit_code != 0:
                        raise RuntimeError(f"Failed to install {install_command}: {result.stderr}")

                    logger.info("Dependencies installed successfully")
                else:
                    logger.info("No install command provided, skipping dependency installation")

                # Get the container that was just used
                container = session.container
                if not container:
                    raise RuntimeError("Sandbox session did not create a container.")

                # Commit the container to a new image with explicit settings
                # Use a larger timeout and resource-friendly settings
                logger.info(f"Step 3/3: Creating image {image_tag}...")
                container.commit(
                    repository=image_tag,
                    conf={
                        "Cmd": None,  # Will be set at runtime
                        "WorkingDir": "/app",
                    },
                )

            logger.info(f"Successfully built and tagged image {image_tag}")
            return image_tag

        except Exception as e:
            logger.error(f"Failed to build image for server {server.name}: {e}")
            raise

    def load_default_servers(self, json_file_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load default server configurations from JSON file."""
        if json_file_path is None:
            json_file_path = Config.DEFAULT_SERVERS_FILE

        try:
            if not os.path.exists(json_file_path):
                logger.warning(f"Default servers file not found: {json_file_path}")
                return []

            with open(json_file_path, "r", encoding="utf-8") as f:
                servers_config = json.load(f)

            logger.info(
                f"Loaded {len(servers_config)} default server configurations from {json_file_path}"
            )
            return servers_config

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON file {json_file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load default servers from {json_file_path}: {e}")
            raise

    def ensure_default_servers(self, json_file_path: Optional[str] = None) -> None:
        """Ensure default servers exist in the database."""
        if json_file_path is None:
            json_file_path = Config.DEFAULT_SERVERS_FILE

        if not self.app:
            logger.error("Flask app context required for database operations")
            return

        try:
            default_servers = self.load_default_servers(json_file_path)

            with self.app.app_context():
                for server_config in default_servers:
                    # Check if server already exists
                    existing_server = MCPServer.query.filter_by(
                        github_url=server_config.get("github_url")
                    ).first()

                    if not existing_server:
                        logger.info(f"Creating default server: {server_config.get('name')}")
                        new_server = MCPServer(
                            name=server_config.get("name"),
                            github_url=server_config.get("github_url"),
                            description=server_config.get("description"),
                            runtime_type=server_config.get("runtime_type"),
                            install_command=server_config.get("install_command"),
                            start_command=server_config.get("start_command"),
                            is_active=server_config.get("is_active", True),
                            build_status=server_config.get("build_status", "pending"),
                        )

                        db.session.add(new_server)

                db.session.commit()
                logger.info("Default servers ensured in database")

        except Exception as e:
            logger.error(f"Failed to ensure default servers: {e}")
            if self.app:
                with self.app.app_context():
                    db.session.rollback()
            raise

    async def initialize_and_build_servers(self) -> None:
        """Initialize MCP Router resources: check Docker, ensure images, build servers."""
        if not self.app:
            logger.error("Flask app context required for server initialization")
            return

        logger.info("Initializing MCP Router resources...")

        # 1. Check if Docker is running
        if not self._check_docker_running():
            logger.error("Docker is not running. Please start Docker and restart the application.")
            raise RuntimeError("Docker daemon is not running")
        logger.info("Docker is running.")

        # 2. Ensure base images exist
        try:
            logger.info("Ensuring base Docker images exist...")
            self._ensure_image_exists(Config.MCP_NODE_IMAGE)
            self._ensure_image_exists(Config.MCP_PYTHON_IMAGE)
            logger.info("Base Docker images are available.")
        except Exception as e:
            logger.error(f"Failed to ensure base images: {e}. Please check your Docker setup.")
            raise

        # 3. Ensure default servers exist in the database
        try:
            self.ensure_default_servers()
        except Exception as e:
            logger.error(f"Failed to ensure default servers: {e}")
            raise

        # 4. Find all active servers and rebuild them all on startup
        logger.info("Rebuilding all active server images on startup...")

        with self.app.app_context():
            all_active_servers = get_active_servers()

            if all_active_servers:
                logger.info(f"Found {len(all_active_servers)} active servers to rebuild.")
                for server in all_active_servers:
                    try:
                        logger.info(f"Building image for {server.name}...")
                        server.build_status = "building"
                        server.build_logs = "Building..."
                        db.session.commit()

                        image_tag = self.build_server_image(server)
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

    async def mount_built_servers(self, mcp_manager) -> None:
        """Mount all successfully built servers to the router."""
        if not self.app:
            logger.error("Flask app context required for mounting servers")
            return

        with self.app.app_context():
            built_servers = get_built_servers()

            if built_servers:
                logger.info(f"Mounting {len(built_servers)} built servers...")
                for server in built_servers:
                    try:
                        await mcp_manager.add_server(server)
                    except Exception as e:
                        logger.error(f"Failed to mount server '{server.name}': {e}")
            else:
                logger.info("No built servers to mount.")
