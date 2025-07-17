"""Tests for the refactored ServerManager that provides static status information"""

import pytest
from unittest.mock import patch, MagicMock
from mcp_router.server_manager import MCPServerManager, init_server_manager, get_server_manager


class TestMCPServerManager:
    """Test cases for MCPServerManager static status functionality"""

    def test_init_server_manager(self):
        """Test server manager initialization"""
        app = MagicMock()
        manager = MCPServerManager(app)
        assert manager.app == app

    def test_get_status_stdio_mode(self):
        """Test get_status returns correct information for STDIO mode"""
        with patch("mcp_router.server_manager.Config") as mock_config:
            mock_config.MCP_TRANSPORT = "stdio"
            mock_config.FLASK_PORT = 8000

            manager = MCPServerManager()
            status = manager.get_status()

            assert status["status"] == "running"
            assert status["transport"] == "stdio"
            assert status["started_at"] is None
            assert status["pid"] is None

            # Check STDIO-specific connection info
            conn_info = status["connection_info"]
            assert conn_info["type"] == "stdio"
            assert conn_info["command"] == "python -m mcp_router --transport stdio"
            assert "Connect via Claude Desktop" in conn_info["description"]

            # Check configuration download info
            assert "config_download_url" in conn_info
            assert "config_description" in conn_info

    @patch("mcp_router.models.get_auth_type")
    def test_get_status_http_mode_with_oauth(self, mock_get_auth_type):
        """Test get_status returns correct information for HTTP mode with OAuth"""
        mock_get_auth_type.return_value = "oauth"

        with patch("mcp_router.server_manager.Config") as mock_config:
            mock_config.MCP_TRANSPORT = "http"
            mock_config.MCP_HOST = "127.0.0.1"
            mock_config.FLASK_PORT = 8000
            mock_config.MCP_PATH = "/mcp"
            mock_config.MCP_AUTH_TYPE = "oauth"
            mock_config.MCP_API_KEY = "test-key"

            manager = MCPServerManager()
            status = manager.get_status()

            assert status["status"] == "running"
            assert status["transport"] == "http"
            assert status["host"] == "127.0.0.1"
            assert status["port"] == 8000

            # Check HTTP-specific connection info
            conn_info = status["connection_info"]
            assert conn_info["type"] == "http"
            assert conn_info["mcp_endpoint"] == "http://127.0.0.1:8000/mcp"
            assert conn_info["path"] == "/mcp"

            # Check OAuth authentication
            assert conn_info["auth_type"] == "oauth"
            assert "oauth-authorization-server" in conn_info["oauth_metadata_url"]
            assert conn_info["api_key_available"] is True

    @patch("mcp_router.models.get_auth_type")
    def test_get_status_http_mode_with_api_key(self, mock_get_auth_type):
        """Test get_status returns correct information for HTTP mode with API key"""
        mock_get_auth_type.return_value = "api_key"

        with patch("mcp_router.server_manager.Config") as mock_config:
            mock_config.MCP_TRANSPORT = "http"
            mock_config.MCP_HOST = "0.0.0.0"
            mock_config.FLASK_PORT = 8001
            mock_config.MCP_PATH = "/api/mcp"
            mock_config.MCP_AUTH_TYPE = "api_key"
            mock_config.MCP_API_KEY = "test-api-key-123"

            manager = MCPServerManager()
            status = manager.get_status()

            assert status["status"] == "running"
            assert status["transport"] == "http"
            assert status["host"] == "0.0.0.0"
            assert status["port"] == 8001

            # Check HTTP-specific connection info
            conn_info = status["connection_info"]
            assert conn_info["type"] == "http"
            assert conn_info["mcp_endpoint"] == "http://0.0.0.0:8001/api/mcp"
            assert conn_info["path"] == "/api/mcp"

            # Check API key authentication
            assert conn_info["auth_type"] == "api_key"
            assert conn_info["api_key"] == "test-api-key-123"
            assert conn_info["oauth_hint"] == "Switch to OAuth for enhanced security"

    @patch("mcp_router.models.get_auth_type")
    def test_get_status_http_mode_auto_generated_api_key(self, mock_get_auth_type):
        """Test get_status handles auto-generated API key case"""
        mock_get_auth_type.return_value = "api_key"

        with patch("mcp_router.server_manager.Config") as mock_config:
            mock_config.MCP_TRANSPORT = "http"
            mock_config.MCP_HOST = "127.0.0.1"
            mock_config.FLASK_PORT = 8000
            mock_config.MCP_PATH = "/mcp"
            mock_config.MCP_AUTH_TYPE = "api_key"
            mock_config.MCP_API_KEY = None

            manager = MCPServerManager()
            status = manager.get_status()

            conn_info = status["connection_info"]
            assert conn_info["auth_type"] == "api_key"
            assert conn_info["api_key"] == "auto-generated"

    def test_get_status_case_insensitive_transport(self):
        """Test get_status handles case variations in transport configuration"""
        with patch("mcp_router.server_manager.Config") as mock_config:
            mock_config.MCP_TRANSPORT = "STDIO"  # Uppercase
            mock_config.FLASK_PORT = 8000

            manager = MCPServerManager()
            status = manager.get_status()

            assert status["transport"] == "stdio"  # Should be normalized to lowercase
            assert status["connection_info"]["type"] == "stdio"


class TestServerManagerGlobals:
    """Test cases for global server manager functions"""

    def test_init_and_get_server_manager(self):
        """Test global server manager initialization and retrieval"""
        app = MagicMock()

        # Initialize server manager
        manager = init_server_manager(app)
        assert isinstance(manager, MCPServerManager)
        assert manager.app == app

        # Retrieve the same instance
        retrieved_manager = get_server_manager()
        assert retrieved_manager is manager

    def test_get_server_manager_not_initialized_error(self):
        """Test that get_server_manager raises error when not initialized"""
        # Reset the global instance
        import mcp_router.server_manager

        mcp_router.server_manager.server_manager = None

        with pytest.raises(RuntimeError, match="Server manager has not been initialized"):
            get_server_manager()
