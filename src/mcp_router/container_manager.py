"""
Manages container lifecycle for MCP servers in any language.

Supports:
- npx: Node.js/JavaScript servers
- uvx: Python servers
- docker: Any language via Docker images
"""
import logging
import os
from typing import Dict, Any, Optional
from flask import Flask
from llm_sandbox import SandboxSession
from mcp_router.models import get_server_by_id, MCPServer
from mcp_router.config import Config

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
                timeout=30,  # Reduced timeout
                env_vars=env_vars,
                docker_host=self.docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        elif server.runtime_type == "uvx":
            # Python servers
            return SandboxSession(
                lang="python",
                image=self.python_image,
                timeout=30,  # Reduced timeout
                env_vars=env_vars,
                docker_host=self.docker_host,
                keep_env=True,  # Reuse containers for performance
            )
        elif server.runtime_type == "docker":
            # Any language via Docker
            return SandboxSession(
                image=server.start_command,
                timeout=30,  # Reduced timeout
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
            return {
                "status": "error",
                "message": f"Server {server_id} not found"
            }
        
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
                        return {
                            "status": "error",
                            "message": error_msg,
                            "stderr": result.stderr
                        }
                
                # Run the start command
                logger.info(f"Running start command: {server.start_command}")
                result = session.execute_command(server.start_command)
                
                return {
                    "status": "success" if result.exit_code == 0 else "error",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code
                }
                
        except Exception as e:
            logger.error(f"Error testing server {server_id}: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def pull_server_image(self, server_id: str) -> Dict[str, Any]:
        """
        Pull Docker image for a specific server.
        Called automatically when a server is added via the web UI.
        
        Args:
            server_id: The ID of the server whose image to pull
            
        Returns:
            Dict containing pull results with status and message
        """
        if self.app:
            with self.app.app_context():
                server = get_server_by_id(server_id)
        else:
            server = get_server_by_id(server_id)
            
        if not server:
            return {
                "status": "error",
                "message": f"Server {server_id} not found"
            }
        
        logger.info(f"Pulling image for server: {server.name} ({server.runtime_type})")
        
        try:
            # Determine which image to pull based on runtime type
            if server.runtime_type == "npx":
                image = self.node_image
            elif server.runtime_type == "uvx":
                image = self.python_image
            elif server.runtime_type == "docker":
                # Extract image name from start command
                image = server.start_command
            else:
                return {
                    "status": "error",
                    "message": f"Unsupported runtime type: {server.runtime_type}"
                }
            
            # Use a temporary sandbox session to pull the image
            session = SandboxSession(
                image=image,
                docker_host=self.docker_host,
                keep_env=False,  # Don't keep this session
            )
            
            with session:
                # The session initialization will pull the image
                logger.info(f"Successfully pulled image: {image}")
                return {
                    "status": "success",
                    "message": f"Image {image} pulled successfully"
                }
                
        except Exception as e:
            logger.error(f"Error pulling image for server {server_id}: {e}")
            return {
                "status": "error",
                "message": str(e)
            } 