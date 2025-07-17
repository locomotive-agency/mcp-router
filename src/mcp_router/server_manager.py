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
            # For STDIO mode, show command for local clients
            status_info.update(
                {
                    "connection_info": {
                        "type": "stdio",
                        "description": "Connect via Claude Desktop or local clients",
                        "command": "python -m mcp_router --transport stdio",
                        "web_ui_url": f"http://127.0.0.1:{Config.FLASK_PORT}",
                        "web_ui_description": "Web UI running in background for server management",
                        "config_download_url": f"http://127.0.0.1:{Config.FLASK_PORT}/config/claude-desktop",
                        "config_description": "Download Claude Desktop configuration file",
                    }
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

            # Add authentication information - get current auth type from database
            try:
                from mcp_router.models import get_auth_type

                current_auth_type = get_auth_type()
            except Exception:
                # Fallback to environment configuration if database unavailable
                current_auth_type = Config.MCP_AUTH_TYPE

            # Always show both auth methods are available
            auth_info = {
                "auth_type": current_auth_type,
                "oauth_available": True,
                "oauth_metadata_url": f"{base_url}/.well-known/oauth-authorization-server",
            }

            if current_auth_type == "oauth":
                auth_info.update(
                    {
                        "primary_auth": "OAuth 2.1 with PKCE",
                        "api_key_available": True,
                    }
                )
            else:  # api_key
                auth_info.update(
                    {
                        "primary_auth": "API Key",
                        "api_key": Config.MCP_API_KEY if Config.MCP_API_KEY else "auto-generated",
                        "oauth_hint": "Switch to OAuth for enhanced security",
                    }
                )

            status_info["connection_info"].update(auth_info)

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
