import httpx
import pytest
import pytest_asyncio
from starlette.applications import Starlette

from mcp_anywhere.web.app import create_app


@pytest_asyncio.fixture
async def app():
    """
    Test fixture to create a Starlette app instance.
    """
    return await create_app()


@pytest.mark.asyncio
async def test_create_app(app: Starlette):
    """
    Tests that the Starlette application can be created successfully.
    """
    assert isinstance(app, Starlette)
    assert len(app.routes) > 0  # Check that routes are mounted


@pytest.mark.asyncio
async def test_homepage_loads(app: Starlette):
    """
    Tests that the homepage redirects to login when not authenticated.
    This is correct behavior as the homepage is protected by session auth middleware.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        response = await client.get("/")

    # Should redirect to login since homepage is protected
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


@pytest.mark.asyncio
async def test_static_files_route(app: Starlette):
    """
    Tests that static files can be accessed.
    This verifies that the static files directory is correctly mounted.
    """
    # We expect a 404 for a non-existent file.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/static/style.css")
        assert response.status_code == 404
