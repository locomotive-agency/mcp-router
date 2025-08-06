import pytest
import pytest_asyncio
import httpx
from starlette.applications import Starlette
import uuid

from mcp_anywhere.web.app import create_app
from mcp_anywhere.database import MCPServer, MCPServerTool, init_db, close_db, get_async_session
from sqlalchemy import select

# PAUSED: Tests that access server details from database
pytestmark = pytest.mark.skip(reason="Paused: Tests access server details from database")


@pytest_asyncio.fixture
async def app():
    """Test fixture to create a Starlette app instance with database."""
    await init_db()
    app = create_app()
    yield app
    await close_db()


@pytest_asyncio.fixture
async def sample_server_with_tools():
    """Sample server with tools for testing"""
    unique_id = str(uuid.uuid4())[:8]
    server = MCPServer(
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
    
    # Create some tools for this server
    tools = [
        MCPServerTool(
            server_id=unique_id,
            tool_name="test_tool_1",
            tool_description="First test tool",
            is_enabled=True
        ),
        MCPServerTool(
            server_id=unique_id,
            tool_name="test_tool_2", 
            tool_description="Second test tool",
            is_enabled=False
        )
    ]
    
    return server, tools


@pytest.mark.asyncio
async def test_server_detail_endpoint_exists(app: Starlette):
    """Test that the server detail endpoint is reachable (basic smoke test)."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/servers/test123")
        
        # Should get 404 (not found) since the server doesn't exist in the empty test database
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_server_detail_not_found_returns_404(app: Starlette):
    """Test that non-existent server returns 404."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/servers/nonexistent123")
        
        # Should return 404 for non-existent server
        assert response.status_code == 404
        assert "not found" in response.text.lower() or "404" in response.text


@pytest.mark.asyncio
async def test_server_detail_shows_server_and_tools(app: Starlette, sample_server_with_tools):
    """Test that server detail page shows server info and associated tools."""
    server, tools = sample_server_with_tools
    
    # Create server and tools in database
    async with get_async_session() as db_session:
        db_session.add(server)
        for tool in tools:
            db_session.add(tool)
        await db_session.commit()
    
    # Test the detail page
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/servers/{server.id}")
    
    assert response.status_code == 200
    
    # Check server information is displayed
    assert server.name in response.text
    assert "docker" in response.text
    assert "A test server for demonstration" in response.text
    assert "built" in response.text
    assert "test-image:latest" in response.text
    assert "https://github.com/test/repo" in response.text
    
    # Check tools are displayed
    assert "test_tool_1" in response.text
    assert "test_tool_2" in response.text
    assert "First test tool" in response.text
    assert "Second test tool" in response.text
    
    # Check tool status indicators
    assert "Enabled" in response.text  # For test_tool_1
    assert "Disabled" in response.text  # For test_tool_2


@pytest.mark.asyncio
async def test_server_detail_shows_no_tools_message(app: Starlette):
    """Test that server detail page shows appropriate message when no tools are available."""
    unique_id = str(uuid.uuid4())[:8]
    server = MCPServer(
        id=unique_id,
        name=f"Empty Server {unique_id}",
        runtime_type="docker", 
        start_command="echo hello",
        github_url="https://github.com/test/empty",
        description="A server with no tools",
        env_variables=[],
        build_status="built"
    )
    
    # Create server without tools
    async with get_async_session() as db_session:
        db_session.add(server)
        await db_session.commit()
    
    # Test the detail page
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/servers/{server.id}")
    
    assert response.status_code == 200
    assert server.name in response.text
    assert "No tools discovered" in response.text