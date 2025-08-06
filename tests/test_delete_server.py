import pytest
import pytest_asyncio
import httpx
from unittest.mock import patch, AsyncMock
from starlette.applications import Starlette
import uuid

from mcp_anywhere.web.app import create_app
from mcp_anywhere.database import MCPServer, init_db, close_db, get_async_session
from sqlalchemy import select

# PAUSED: Tests that delete servers from database
pytestmark = pytest.mark.skip(reason="Paused: Tests delete servers from database")


@pytest_asyncio.fixture
async def app():
    """Test fixture to create a Starlette app instance with database."""
    await init_db()
    app = create_app()
    yield app
    await close_db()


@pytest_asyncio.fixture
async def sample_server():
    """Sample server for testing with unique name"""
    unique_id = str(uuid.uuid4())[:8]
    return MCPServer(
        id=unique_id,
        name=f"Test Server {unique_id}",
        runtime_type="docker",
        start_command="echo hello",
        github_url="https://github.com/test/repo",
        description="A test server for demonstration",
        env_variables=[],
        build_status="built",
        image_tag="test-image:latest"
    )


@pytest.mark.asyncio
async def test_delete_server_success(app: Starlette, sample_server: MCPServer):
    """Test that DELETE /servers/{id} successfully deletes a server."""
    
    # First, create a server in the database
    async with get_async_session() as db_session:
        db_session.add(sample_server)
        await db_session.commit()
        
        # Verify it exists
        stmt = select(MCPServer).where(MCPServer.id == sample_server.id)
        result = await db_session.execute(stmt)
        server_before = result.scalar_one_or_none()
        assert server_before is not None
    
    # Mock the MCP manager removal
    with patch('mcp_anywhere.web.routes.get_mcp_manager') as mock_get_manager:
        mock_mcp_manager = AsyncMock()
        mock_get_manager.return_value = mock_mcp_manager
        
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/servers/{sample_server.id}/delete")
    
    # Should redirect after successful deletion
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    
    # Verify server was deleted from database
    async with get_async_session() as db_session:
        stmt = select(MCPServer).where(MCPServer.id == sample_server.id)
        result = await db_session.execute(stmt)
        server_after = result.scalar_one_or_none()
        assert server_after is None
    
    # Verify MCP manager was called to remove server
    mock_mcp_manager.remove_server.assert_called_once_with(sample_server.id)


@pytest.mark.asyncio
async def test_delete_server_not_found(app: Starlette):
    """Test that DELETE /servers/{id} returns 404 for non-existent server."""
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/servers/nonexistent123/delete")
    
    # Should return 404 for non-existent server
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_server_get_method_not_allowed(app: Starlette):
    """Test that GET /servers/{id}/delete is not allowed."""
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/servers/test123/delete")
    
    # Should return 405 Method Not Allowed or 404 if route doesn't exist for GET
    assert response.status_code in [404, 405]