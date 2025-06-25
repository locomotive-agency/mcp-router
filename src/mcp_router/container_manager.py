"""Manages container lifecycle for MCP servers"""
import asyncio
import logging
from typing import Dict, Any, Optional
from flask import current_app
from llm_sandbox import SandboxSession
from mcp_router.models import get_server_by_id, MCPServer

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
        with self.app.app_context():
            server = get_server_by_id(server_id)
            if not server:
                return {"status": "error", "message": "Server not found"}

            try:
                with self._create_sandbox_session(server) as session:
                    # A simple command to verify the environment is working
                    test_command = "pwd"
                    result = session.execute_command(test_command)

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
        
        if server.runtime_type == "npx":
            return SandboxSession(
                lang="javascript",
                runtime="node",
                timeout=60,
                env_vars=env_vars,
                docker_host=docker_host,
            )
        elif server.runtime_type == "uvx":
            return SandboxSession(
                lang="python",
                timeout=60,
                env_vars=env_vars,
                docker_host=docker_host,
            )
        elif server.runtime_type == "docker":
            # Assuming the image name is stored in `start_command` for Docker,
            # which is a common convention for simple cases.
            # e.g., start_command is "my-docker-image:latest"
            return SandboxSession(
                image=server.start_command,
                timeout=60,
                env_vars=env_vars,
                docker_host=docker_host,
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