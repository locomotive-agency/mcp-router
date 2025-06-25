"""Manages container lifecycle for MCP servers"""
import asyncio
import logging
import os
from typing import Dict, Any, Optional, List
from flask import current_app
from llm_sandbox import SandboxSession
from mcp_router.models import get_server_by_id, MCPServer, get_active_servers

logger = logging.getLogger(__name__)


class ContainerManager:
    """Manages container lifecycle with async bridge for llm-sandbox"""

    def __init__(self, app=None):
        """Initializes the ContainerManager."""
        self.active_sessions: Dict[str, SandboxSession] = {}
        # Hold a reference to the app object to be able to create context in executors
        if app:
            self.app = app
        else:
            self.app = current_app._get_current_object()

    def pull_server_image(self, server_id: str) -> Dict[str, Any]:
        """
        Pull Docker image for a specific server to reduce first-run latency.
        This should be called when a server is added.
        
        Args:
            server_id: The ID of the server to pull image for.
            
        Returns:
            A dictionary with the pull result.
        """
        with self.app.app_context():
            server = get_server_by_id(server_id)
            if not server:
                return {
                    "status": "error",
                    "message": "Server not found"
                }
            
            logger.info(f"Pulling image for server: {server.name} ({server.runtime_type})")
            
            try:
                # Determine the image to pull based on runtime type
                if server.runtime_type == "npx":
                    image = "node:20-alpine"  # Lightweight Node.js image
                elif server.runtime_type == "uvx":
                    image = os.environ.get('MCP_PYTHON_IMAGE', 'python:3.11-alpine')  # Configurable Python image
                elif server.runtime_type == "docker":
                    image = server.start_command  # Docker type uses start_command as image
                else:
                    return {
                        "status": "error",
                        "message": f"Unknown runtime type: {server.runtime_type}"
                    }
                
                # Log the image being pulled
                logger.info(f"Pulling Docker image: {image}")
                
                # Create a temporary session just to trigger image pull
                # The session creation itself will pull the image if not present
                with self._create_sandbox_session(server) as session:
                    pass  # Just creating the session pulls the image
                
                logger.info(f"Successfully pulled image for {server.name}")
                return {
                    "status": "success",
                    "message": f"Image {image} ready",
                    "image": image
                }
                    
            except Exception as e:
                logger.error(f"Failed to pull image for {server.name}: {e}")
                return {
                    "status": "error",
                    "message": str(e)
                }

    def pre_pull_images(self) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Use pull_server_image() when adding individual servers instead.
        Pre-pull Docker images for all active servers to reduce first-run latency.
        This should be called during application startup.
        
        Returns:
            A list of dictionaries with pull results for each server.
        """
        logger.warning("pre_pull_images is deprecated. Use pull_server_image() when adding servers.")
        results = []
        
        with self.app.app_context():
            servers = get_active_servers()
            
            for server in servers:
                result = self.pull_server_image(server.id)
                result["server"] = server.name
                results.append(result)
        
        return results

    async def test_server_spawn(self, server_id: str) -> Dict[str, Any]:
        """
        Tests if a server's container can be spawned successfully by running a simple command.

        Args:
            server_id: The ID of the server to test.

        Returns:
            A dictionary with the test result.
        """
        loop = asyncio.get_running_loop()
        try:
            # Use run_in_executor to call the synchronous DB and sandbox code
            result = await loop.run_in_executor(
                None, self._run_test_sync, server_id
            )
            return result
        except Exception as e:
            logger.error(f"Error testing server spawn for {server_id}: {e}")
            return {"status": "error", "message": str(e)}

    def _run_test_sync(self, server_id: str) -> Dict[str, Any]:
        """
        Synchronous method to fetch server details and run a test in the sandbox.
        This method is designed to be called by `run_in_executor`.
        """
        import time
        start_time = time.time()
        
        with self.app.app_context():
            server = get_server_by_id(server_id)
            if not server:
                return {"status": "error", "message": "Server not found"}

            try:
                logger.info(f"Creating sandbox session for {server.name} ({server.runtime_type})")
                session_start = time.time()
                
                with self._create_sandbox_session(server) as session:
                    session_created = time.time()
                    logger.info(f"Session created in {session_created - session_start:.2f}s")
                    
                    # A simple command to verify the environment is working
                    test_command = "pwd"
                    cmd_start = time.time()
                    result = session.execute_command(test_command)
                    cmd_end = time.time()
                    logger.info(f"Command executed in {cmd_end - cmd_start:.2f}s")

                    total_time = time.time() - start_time
                    logger.info(f"Total test time: {total_time:.2f}s")

                    if result.exit_code == 0:
                        return {
                            "status": "success",
                            "message": "Container spawned successfully.",
                            "details": result.stdout.strip(),
                        }
                    else:
                        return {
                            "status": "error",
                            "message": "Container test command failed.",
                            "details": result.stderr,
                        }
            except Exception as e:
                logger.error(f"Sandbox session failed for server {server.id}: {e}")
                return {"status": "error", "message": f"Sandbox creation failed: {e}"}

    def _create_sandbox_session(self, server: MCPServer) -> SandboxSession:
        """Helper to create a SandboxSession based on server runtime"""
        env_vars = self._get_env_vars(server)
        
        # Define docker_host for macOS, where the socket might not be in the default location
        docker_host = "unix:///Users/jroakes/.docker/run/docker.sock"
        
        # Use lightweight images for better performance
        # Note: Alpine images are much smaller but may have compatibility issues
        # with some Python packages that require compiled dependencies (numpy, pandas, etc.)
        # If you encounter issues, switch to python:3.11-slim-bullseye
        if server.runtime_type == "npx":
            return SandboxSession(
                lang="javascript",
                runtime="node",
                image="node:20-alpine",  # Alpine image is ~50MB vs ~400MB for full
                timeout=30,  # Reduced from 60 to 30 seconds
                env_vars=env_vars,
                docker_host=docker_host,
                keep_env=True,  # Reuse containers to avoid image pull delays
            )
        elif server.runtime_type == "uvx":
            # For Python, you might need to use slim-bullseye instead of Alpine
            # if the server uses packages with C extensions (numpy, pandas, scipy, etc.)
            # Options: "python:3.11-alpine" (~50MB) or "python:3.11-slim-bullseye" (~150MB)
            python_image = os.environ.get('MCP_PYTHON_IMAGE', 'python:3.11-alpine')
            return SandboxSession(
                lang="python",
                image=python_image,
                timeout=30,  # Reduced from 60 to 30 seconds
                env_vars=env_vars,
                docker_host=docker_host,
                keep_env=True,  # Reuse containers to avoid image pull delays
            )
        elif server.runtime_type == "docker":
            # Assuming the image name is stored in `start_command` for Docker,
            # which is a common convention for simple cases.
            # e.g., start_command is "my-docker-image:latest"
            return SandboxSession(
                image=server.start_command,
                timeout=30,  # Reduced from 60 to 30 seconds
                env_vars=env_vars,
                docker_host=docker_host,
                keep_env=True,  # Reuse containers to avoid image pull delays
            )
        else:
            raise ValueError(f"Unsupported runtime type: {server.runtime_type}")

    def _get_env_vars(self, server: MCPServer) -> Dict[str, str]:
        """Extract environment variables from server config"""
        env_vars = {}
        for env in server.env_variables:
            if env.get("value"):
                env_vars[env["key"]] = env["value"]
        return env_vars

    async def execute_server_tool(self, server_id: str, tool_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call in a containerized MCP server.
        This involves installing dependencies and then running the start command.
        
        Args:
            server_id: The ID of the server to execute.
            tool_params: A dictionary of parameters to pass to the tool.

        Returns:
            A dictionary with the execution result.
        """
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, self._run_tool_sync, server_id, tool_params
            )
            return result
        except Exception as e:
            logger.error(f"Error executing tool for server {server_id}: {e}")
            return {"status": "error", "message": str(e)}

    def _run_tool_sync(self, server_id: str, tool_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synchronous method to run the full tool execution flow in the sandbox.
        """
        with self.app.app_context():
            server = get_server_by_id(server_id)
            if not server:
                return {"status": "error", "message": "Server not found"}

            try:
                with self._create_sandbox_session(server) as session:
                    # 1. Install dependencies if an install command is provided
                    if server.install_command:
                        install_result = session.execute_command(server.install_command)
                        if install_result.exit_code != 0:
                            return {
                                "status": "error",
                                "message": "Installation command failed",
                                "details": install_result.stderr,
                            }

                    # 2. Construct the start command with parameters
                    # A simple CLI argument format is assumed: --key value
                    params_str = " ".join([f"--{k} '{v}'" for k, v in tool_params.items()])
                    full_command = f"{server.start_command} {params_str}"
                    
                    # 3. Execute the tool command
                    exec_result = session.execute_command(full_command)

                    if exec_result.exit_code == 0:
                        return {
                            "status": "success",
                            "message": "Tool executed successfully.",
                            "result": exec_result.stdout,
                        }
                    else:
                        return {
                            "status": "error",
                            "message": "Tool execution failed.",
                            "details": exec_result.stderr,
                        }
            except Exception as e:
                logger.error(f"Sandbox tool execution failed for server {server.id}: {e}")
                return {"status": "error", "message": f"Sandbox execution failed: {e}"} 