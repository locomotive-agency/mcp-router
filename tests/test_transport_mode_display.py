"""
Test that the transport mode is correctly displayed in the web UI.

This test ensures that when the server is started in STDIO or HTTP mode,
the web UI correctly displays the transport mode in the dashboard.
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.testclient import TestClient
from starlette.applications import Starlette

from mcp_anywhere.web.app import create_app


@asynccontextmanager
async def mock_lifespan(app):
    """Mock lifespan context manager."""
    # Minimal setup
    app.state.mcp_manager = MagicMock()
    app.state.container_manager = MagicMock()
    app.state.get_async_session = MagicMock()
    yield
    # No cleanup needed for tests


@pytest.fixture
def app_stdio_with_mode():
    """Create app instance for STDIO mode with transport mode in state."""
    with patch("mcp_anywhere.web.app.lifespan", mock_lifespan):
        app = create_app(transport_mode="stdio")
        return app


@pytest.fixture
def app_http_with_mode():
    """Create app instance for HTTP mode with transport mode in state."""
    with patch("mcp_anywhere.web.app.lifespan", mock_lifespan):
        app = create_app(transport_mode="http")
        return app


def test_stdio_mode_displays_correctly(app_stdio_with_mode):
    """
    Test that STDIO mode is correctly stored in app state.
    """
    # Check that transport mode is correctly set in app state
    assert hasattr(app_stdio_with_mode.state, 'transport_mode'), (
        "App state should have transport_mode attribute"
    )
    assert app_stdio_with_mode.state.transport_mode == "stdio", (
        f"Expected transport_mode to be 'stdio', got {app_stdio_with_mode.state.transport_mode}"
    )


def test_http_mode_displays_correctly(app_http_with_mode):
    """
    Test that HTTP mode is correctly stored in app state.
    """
    # Check that transport mode is correctly set in app state
    assert hasattr(app_http_with_mode.state, 'transport_mode'), (
        "App state should have transport_mode attribute"
    )
    assert app_http_with_mode.state.transport_mode == "http", (
        f"Expected transport_mode to be 'http', got {app_http_with_mode.state.transport_mode}"
    )


def test_transport_mode_passed_to_template_context():
    """
    Test that transport mode is included in the template context.
    """
    from starlette.requests import Request
    from mcp_anywhere.web.routes import get_template_context
    
    # Create a mock request with app state
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.transport_mode = "stdio"
    mock_request.session = {}
    
    # Get the template context
    context = get_template_context(mock_request)
    
    # Check that transport_mode is in the context
    assert "transport_mode" in context, (
        "transport_mode should be included in template context"
    )
    assert context["transport_mode"] == "stdio", (
        f"Expected transport_mode to be 'stdio', got {context.get('transport_mode')}"
    )