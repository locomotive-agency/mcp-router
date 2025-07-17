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
import time
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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

    def _create_sandbox_session(
        self, server: MCPServer, use_template: bool = True
    ) -> SandboxSession:
        """Create a sandbox session based on server runtime type

        Args:
            server: MCPServer instance
            use_template: Whether to use/create a template container for reuse

        Returns:
            SandboxSession configured for the server
        """
        # Get environment variables for the server
        env_vars = self._get_env_vars(server)

        # Common runtime configuration for resource limits and environment
        runtime_config = {
            "mem_limit": "512m",  # 512MB memory limit
            "cpu_period": 100000,
            "cpu_quota": 50000,  # 50% of one CPU
            "pids_limit": 100,  # Process limit
            "environment": env_vars,  # Pass environment variables at container level
        }

        # Base configuration
        base_config = {
            "docker_host": self.docker_host,
            "backend": "docker",
            "runtime_config": runtime_config,
            "default_timeout": 60.0,  # 60 second timeout
            "verbose": True,
        }

        # For tests, we don't want to commit containers
        if use_template:
            base_config["keep_template"] = True
            # Use template names for reuse across sessions
            if server.runtime_type == "npx":
                base_config["template_name"] = "mcp-router-node-template"
            elif server.runtime_type == "uvx":
                base_config["template_name"] = "mcp-router-python-template"
        else:
            # For tests, don't keep templates or commit
            base_config["keep_template"] = False
            base_config["commit_container"] = False

        if server.runtime_type == "npx":
            # Node.js/JavaScript servers
            return SandboxSession(lang="javascript", image=self.node_image, **base_config)
        elif server.runtime_type == "uvx":
            # Python servers
            return SandboxSession(lang="python", image=self.python_image, **base_config)
        else:
            # Custom Docker image - we need to determine the language
            # Default to python for custom images, but this could be configured
            return SandboxSession(
                lang="python",  # Required parameter, defaulting to python
                image=server.start_command,  # Custom image
                **base_config,
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def test_server(self, server: MCPServer) -> Dict[str, Any]:
        """Test server connection with retry logic

        Args:
            server: MCPServer instance to test

        Returns:
            Dict containing test results

        Note:
            Will retry up to 3 times with exponential backoff
        """
        logger.info(f"Testing server: {server.name} ({server.runtime_type})")
        try:
            start_time = time.time()

            # Create sandbox session WITHOUT template for tests (faster, no commit)
            with self._create_sandbox_session(server, use_template=False) as sandbox:
                if server.runtime_type == "npx":
                    # Simplified test - just check if npx is available and package info
                    code = f"""
const {{ exec }} = require('child_process');

// First check if npx is available
exec('npx --version', (err, stdout, stderr) => {{
    if (err) {{
        console.error('npx not available:', stderr);
        process.exit(1);
    }}
    console.log('npx version:', stdout.trim());

    // Quick check for package info without installing
    exec('npm view {server.start_command} version', {{timeout: 10000}}, (err, stdout, stderr) => {{
        if (err) {{
            console.log(JSON.stringify({{
                status: 'warning',
                message: 'Package check failed - may need installation',
                npx_available: true,
                package_check: stderr || err.message
            }}));
        }} else {{
            console.log(JSON.stringify({{
                status: 'success',
                message: 'Package exists in registry',
                npx_available: true,
                package_version: stdout.trim()
            }}));
        }}
    }});
}});
"""
                    # Run the code with reasonable timeout
                    result = sandbox.run(code, timeout=60.0)

                elif server.runtime_type == "uvx":
                    # Simplified Python/uvx test
                    code = f"""
import subprocess
import json
import sys

# Check if uvx is available
try:
    result = subprocess.run(['which', 'uvx'], capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        print(json.dumps({{
            'status': 'error',
            'message': 'uvx not found in PATH'
        }}))
        sys.exit(1)

    # Quick check if package exists without running it
    cmd = ['pip', 'index', 'versions', '{server.start_command}']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    if result.returncode == 0 and result.stdout:
        print(json.dumps({{
            'status': 'success',
            'message': 'Package exists in PyPI',
            'uvx_available': True,
            'package_info': result.stdout.strip()[:200]  # First 200 chars
        }}))
    else:
        print(json.dumps({{
            'status': 'warning',
            'message': 'Package check inconclusive',
            'uvx_available': True
        }}))
except subprocess.TimeoutExpired:
    print(json.dumps({{
        'status': 'error',
        'message': 'Check timed out'
    }}))
except Exception as e:
    print(json.dumps({{
        'status': 'error',
        'message': str(e)
    }}))
"""
                    # Run the code with reasonable timeout
                    result = sandbox.run(code, timeout=60.0)

                else:
                    # Custom Docker - just check if container can run
                    code = 'echo \'{"status": "success", "message": "Container is functional"}\''
                    # Run the code with reasonable timeout (even simple commands might need time for container startup)
                    result = sandbox.run(code, timeout=30.0)

                elapsed_time = time.time() - start_time

                # Parse output
                if result.exit_code == 0:
                    output = result.stdout.strip()

                    # Try to parse JSON output
                    try:
                        # Get the last line that looks like JSON
                        lines = output.split("\n")
                        json_line = None
                        for line in reversed(lines):
                            if line.strip().startswith("{"):
                                json_line = line
                                break

                        if json_line:
                            data = json.loads(json_line)
                            return {
                                "status": data.get("status", "success"),
                                "message": data.get("message", "Test completed"),
                                "exit_code": result.exit_code,
                                "output": output,
                                "elapsed_time": elapsed_time,
                                **{k: v for k, v in data.items() if k not in ["status", "message"]},
                            }
                    except json.JSONDecodeError:
                        pass

                    return {
                        "status": "success",
                        "message": "Container test successful",
                        "exit_code": result.exit_code,
                        "output": output,
                        "elapsed_time": elapsed_time,
                    }
                else:
                    return {
                        "status": "error",
                        "exit_code": result.exit_code,
                        "message": f"Test failed with exit code {result.exit_code}",
                        "stderr": result.stderr,
                        "stdout": result.stdout,
                        "elapsed_time": elapsed_time,
                    }

        except Exception as e:
            logger.error(f"Error testing server {server.name}: {e}", exc_info=True)
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def pull_server_image(self, server_id: str) -> Dict[str, Any]:
        """Pulls the Docker image for a specific server with retry logic.

        Args:
            server_id: ID of the server to pull image for

        Returns:
            Dictionary with status and image information

        Note:
            Will retry up to 3 times with exponential backoff
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def run_server_in_sandbox(self, server: MCPServer) -> Dict[str, Any]:
        """Run an MCP server inside a sandbox container with retry logic

        Args:
            server: MCPServer instance to run

        Returns:
            Dict containing execution results

        Note:
            Will retry up to 3 times with exponential backoff
        """
        logger.info(f"Starting server {server.name} in sandbox")
        try:
            # Create sandbox session with template for actual server runs
            with self._create_sandbox_session(server, use_template=True) as sandbox:
                # Build the command based on runtime type
                if server.runtime_type == "npx":
                    # For npx servers, we run them directly
                    command = f"npx -y {server.start_command}"
                    # Add stdio transport args if needed
                    if "--stdio" not in command:
                        command += " stdio"

                elif server.runtime_type == "uvx":
                    # For Python/uvx servers
                    command = f"uvx {server.start_command}"
                    if "--stdio" not in command:
                        command += " stdio"

                else:
                    # Custom command
                    command = server.start_command

                # Create the runner script
                if server.runtime_type in ["npx", "uvx"]:
                    # Use shell command directly for npx/uvx
                    runner_code = command
                else:
                    # For custom Docker, use the command as-is
                    runner_code = command

                # Run in sandbox (env vars already in container)
                # Note: For long-running servers, we might want to use a different approach
                # This is primarily for testing/short runs
                result = sandbox.run(
                    runner_code, timeout=300.0  # 5 minute timeout for server operations
                )

                return {
                    "success": result.exit_code == 0,
                    "output": result.stdout,
                    "error": result.stderr if result.exit_code != 0 else None,
                    "exit_code": result.exit_code,
                }

        except Exception as e:
            logger.error(f"Error running server {server.name} in sandbox: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def initialize_templates(self) -> None:
        """Pre-create template containers for faster startup

        This should be called once at startup to create template containers
        that can be reused for all operations, significantly speeding up
        container creation.
        """
        logger.info("Initializing template containers...")

        # Create a dummy server for each runtime type
        dummy_servers = [
            MCPServer(
                name="template-npx", runtime_type="npx", start_command="dummy", env_variables=[]
            ),
            MCPServer(
                name="template-uvx", runtime_type="uvx", start_command="dummy", env_variables=[]
            ),
        ]

        for server in dummy_servers:
            try:
                # Create session with template to establish the template container
                with self._create_sandbox_session(server, use_template=True) as sandbox:
                    # Run a simple command to ensure container is ready
                    if server.runtime_type == "npx":
                        sandbox.run("node --version", timeout=10.0)
                    else:
                        sandbox.run("python --version", timeout=10.0)
                logger.info(f"Template container created for {server.runtime_type}")
            except Exception as e:
                logger.error(f"Failed to create template for {server.runtime_type}: {e}")
