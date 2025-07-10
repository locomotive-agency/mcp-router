"""Provides MCP server status information for different transports"""

import logging
from typing import Dict, Any, Optional
from flask import Flask
from mcp_router.config import Config

logger = logging.getLogger(__name__)


class MCPServerManager:
    """Provides static information about the MCP server transport mode"""

    def __init__(self, app: Optional[Flask] = None):
        """Initialize the server manager

        Args:
            app: Flask application instance (kept for compatibility)
        """
        self.app = app

    def get_status(self) -> Dict[str, Any]:
        """Get current server status based on the configured transport mode

        Returns:
            Dict containing status information for the current transport mode
        """
        transport = Config.MCP_TRANSPORT.lower()

        # Base status information
        status_info = {
            "status": "running",
            "transport": transport,
            "started_at": None,  # Not applicable in the new architecture
            "pid": None,  # Not applicable in the new architecture
        }

        if transport == "stdio":
            status_info.update(
                {
                    "connection_info": {
                        "type": "stdio",
                        "command": "python -m mcp_router --transport stdio",
                        "description": "Connect using stdio transport for local clients like Claude Desktop",
                    },
                    "web_ui_url": f"http://127.0.0.1:{Config.FLASK_PORT}",
                    "web_ui_description": "Web UI available in background for server management",
                }
            )
        elif transport == "http":
            # Build connection info for HTTP mode
            base_url = f"http://{Config.MCP_HOST}:{Config.FLASK_PORT}"
            mcp_url = f"{base_url}{Config.MCP_PATH}"

            status_info.update(
                {
                    "connection_info": {
                        "type": "http",
                        "mcp_endpoint": mcp_url,
                        "web_ui_url": base_url,
                        "path": Config.MCP_PATH,
                    },
                    "host": Config.MCP_HOST,
                    "port": Config.FLASK_PORT,
                }
            )

            # Add authentication information
            if Config.MCP_OAUTH_ENABLED:
                status_info["connection_info"].update(
                    {
                        "auth_type": "oauth",
                        "oauth_metadata_url": f"{base_url}/.well-known/oauth-authorization-server",
                    }
                )
            else:
                status_info["connection_info"].update(
                    {
                        "auth_type": "api_key",
                        "api_key": Config.MCP_API_KEY if Config.MCP_API_KEY else "auto-generated",
                    }
                )

        return status_info


# Global instance - will be initialized with app in app.py
server_manager = None


def init_server_manager(app: Flask) -> MCPServerManager:
    """Initialize the global server manager with Flask app

    Args:
        app: Flask application instance

    Returns:
        Initialized MCPServerManager instance
    """
    global server_manager
    server_manager = MCPServerManager(app)
    return server_manager


def get_server_manager() -> MCPServerManager:
    """Get the global server manager instance

    Returns:
        The MCPServerManager instance
    """
    if server_manager is None:
        raise RuntimeError("Server manager has not been initialized.")
    return server_manager
