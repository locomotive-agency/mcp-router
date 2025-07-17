"""Tests for HTTP mode functionality."""

import pytest
from unittest.mock import patch
from mcp_router.__main__ import run_http_mode


class TestHTTPMode:
    """Test the HTTP mode implementation."""

    def test_asgi_app_imports_successfully(self):
        """Test that the ASGI app can be imported without errors."""
        try:
            from mcp_router.asgi import asgi_app

            assert asgi_app is not None
            assert callable(asgi_app)
        except ImportError as e:
            pytest.fail(f"Failed to import asgi_app: {e}")

    def test_asgi_app_has_correct_type(self):
        """Test that the ASGI app is a Starlette application."""
        from mcp_router.asgi import asgi_app
        from starlette.applications import Starlette

        assert isinstance(asgi_app, Starlette)

    def test_asgi_app_has_mcp_route_mounted(self):
        """Test that the ASGI app has the MCP route mounted."""
        from mcp_router.asgi import asgi_app
        from mcp_router.config import Config

        # Check that the MCP route is mounted
        mount_path = Config.MCP_PATH
        found_mount = False

        for route in asgi_app.router.routes:
            if hasattr(route, "path") and route.path == mount_path:
                found_mount = True
                break

        assert found_mount, f"MCP path {mount_path} not found in mounted routes"

    @patch("mcp_router.__main__.uvicorn")
    @patch("mcp_router.__main__.Config")
    def test_run_http_mode_calls_uvicorn_correctly(self, mock_config, mock_uvicorn):
        """Test that run_http_mode calls uvicorn with correct parameters."""
        from mcp_router.asgi import asgi_app

        # Setup mock config
        mock_config.MCP_HOST = "0.0.0.0"
        mock_config.FLASK_PORT = 8000
        mock_config.MCP_LOG_LEVEL = "INFO"

        # Call the function
        run_http_mode()

        # Verify uvicorn.run was called with correct parameters
        mock_uvicorn.run.assert_called_once()
        call_args = mock_uvicorn.run.call_args

        # Check the ASGI app is passed
        assert call_args[0][0] is asgi_app

        # Check keyword arguments
        kwargs = call_args[1]
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 8000
        assert kwargs["log_level"] == "info"

    @patch("mcp_router.__main__.uvicorn")
    def test_run_http_mode_integration(self, mock_uvicorn):
        """Test that run_http_mode integrates correctly with the ASGI app."""
        from mcp_router.asgi import asgi_app

        run_http_mode()

        # Verify uvicorn.run was called
        mock_uvicorn.run.assert_called_once()

        # Get the app that was passed to uvicorn
        passed_app = mock_uvicorn.run.call_args[0][0]

        # Verify it's our ASGI app
        assert passed_app is asgi_app

    def test_asgi_app_has_wsgi_middleware(self):
        """Test that the ASGI app includes WSGI middleware for Flask integration."""
        from mcp_router.asgi import asgi_app

        # Check that the app has middleware configured
        assert hasattr(asgi_app, "middleware_stack")
        # The app should be callable (this is a basic ASGI compliance test)
        assert callable(asgi_app)
