"""
Test that STDIO transport mode doesn't apply JWT authentication to MCP endpoints.

This test ensures that when running in STDIO mode, the MCPProtectionMiddleware
is not applied since MCP communication happens over STDIO, not HTTP.
"""

import pytest
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient
from starlette.applications import Starlette

from mcp_anywhere.web.app import create_app


@asynccontextmanager
async def mock_lifespan(app: Starlette):
    """Mock lifespan context manager for testing."""
    # Setup mock state
    app.state.mcp_manager = MagicMock()
    app.state.container_manager = MagicMock()
    app.state.get_async_session = AsyncMock()
    yield
    # Cleanup (nothing needed for tests)


@pytest.fixture
def mock_env_stdio():
    """Mock environment for STDIO mode."""
    with patch.dict(os.environ, {"MCP_TRANSPORT_MODE": "stdio"}):
        yield


@pytest.fixture
def app_stdio(mock_env_stdio):
    """Create app instance for STDIO mode."""
    # Mock the lifespan to avoid actual database initialization
    with patch("mcp_anywhere.web.app.create_lifespan", return_value=mock_lifespan):
        # Create app with transport mode context
        app = create_app(transport_mode="stdio")
        return app


@pytest.fixture
def app_http():
    """Create app instance for HTTP mode."""
    # Mock the lifespan to avoid actual database initialization
    with patch("mcp_anywhere.web.app.create_lifespan", return_value=mock_lifespan):
        # Create app with transport mode context
        app = create_app(transport_mode="http")
        return app


def test_stdio_mode_no_jwt_on_mcp_endpoints(app_stdio):
    """
    Test that in STDIO mode, /mcp endpoints don't require JWT authentication.
    
    In STDIO mode, MCP communication happens through standard input/output,
    not HTTP, so JWT authentication on /mcp endpoints is not needed.
    """
    with TestClient(app_stdio) as client:
        # Try to access an MCP endpoint without authentication
        # In STDIO mode, this should NOT return 401
        response = client.get("/mcp/tools/list")
        
        # Since there's no actual MCP handler mounted at /mcp in STDIO mode,
        # we should get a 404, not a 401 (which would indicate auth requirement)
        assert response.status_code == 404, (
            f"Expected 404 (not found) in STDIO mode, got {response.status_code}. "
            "This indicates JWT auth is incorrectly applied to /mcp endpoints."
        )




def test_stdio_mode_web_ui_still_protected(app_stdio):
    """
    Test that in STDIO mode, web UI endpoints still require session authentication.
    
    Even in STDIO mode, the web UI should be protected by session-based auth.
    """
    with TestClient(app_stdio, follow_redirects=False) as client:
        # Try to access protected web UI endpoint without session
        response = client.get("/servers")
        
        # Should redirect to login
        assert response.status_code in [302, 303], (
            f"Expected redirect to login, got {response.status_code}"
        )
        
        # Check redirect location
        assert "location" in response.headers
        assert "/auth/login" in response.headers["location"]