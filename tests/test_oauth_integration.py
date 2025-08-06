import os
import tempfile

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from mcp_anywhere.web.app import create_app


@pytest_asyncio.fixture
async def temp_db_app():
    """Create app with temporary database for testing."""
    # Create temporary database
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_fd)

    # Patch database configuration
    import mcp_anywhere.config

    original_db_uri = mcp_anywhere.config.Config.SQLALCHEMY_DATABASE_URI
    mcp_anywhere.config.Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{temp_path}"

    try:
        # Create app
        app = create_app()
        yield app
    finally:
        # Restore original config
        mcp_anywhere.config.Config.SQLALCHEMY_DATABASE_URI = original_db_uri

        # Clean up temp file
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@pytest.mark.asyncio
async def test_app_initialization_with_oauth(temp_db_app):
    """Test that the app initializes correctly with OAuth components."""
    app = temp_db_app

    # Test that app has the required state
    async with app.router.lifespan_context(app):
        # Check that MCP manager is initialized
        assert hasattr(app.state, "mcp_manager")
        assert app.state.mcp_manager is not None

        # Check that database session function is available
        assert hasattr(app.state, "get_async_session")
        assert callable(app.state.get_async_session)


@pytest.mark.asyncio
async def test_auth_routes_are_available(temp_db_app):
    """Test that auth routes are available in the app."""
    app = temp_db_app

    with TestClient(app) as client:
        # Test login page loads
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert "login" in response.text.lower()


@pytest.mark.asyncio
async def test_oauth_default_data_creation(temp_db_app):
    """Test that default OAuth data is created during app startup."""
    app = temp_db_app

    # Start the app lifecycle to trigger OAuth initialization
    async with app.router.lifespan_context(app):
        # Get database session
        async with app.state.get_async_session() as db_session:
            from sqlalchemy import select

            from mcp_anywhere.auth.models import OAuth2Client, User

            # Check that admin user was created
            stmt = select(User).where(User.username == "admin")
            result = await db_session.execute(stmt)
            admin_user = result.scalar_one_or_none()

            assert admin_user is not None
            assert admin_user.username == "admin"

            # Check that OAuth client was created
            stmt = select(OAuth2Client)
            result = await db_session.execute(stmt)
            oauth_client = result.scalar_one_or_none()

            assert oauth_client is not None
            assert oauth_client.client_id is not None
            assert oauth_client.client_secret is not None


@pytest.mark.asyncio
async def test_mcp_endpoint_requires_auth(temp_db_app):
    """Test that MCP endpoints are protected by JWT middleware."""
    app = temp_db_app

    with TestClient(app) as client:
        # Try to access MCP endpoint without authentication
        response = client.get("/mcp/tools/list")
        assert response.status_code == 401
        assert "error" in response.json()
        assert response.json()["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_web_routes_are_public(temp_db_app):
    """Test that web UI routes are accessible without authentication."""
    app = temp_db_app

    with TestClient(app) as client:
        # Test homepage loads without auth
        response = client.get("/")
        # Might be 404 if no root route is defined, but shouldn't be 401
        assert response.status_code != 401
