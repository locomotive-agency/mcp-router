"""
Test the web UI endpoints.

This module tests the web interface routes as specified in Phase 4
of the engineering documentation.
"""

import pytest
import httpx
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette

from mcp_anywhere.database import MCPServer, MCPServerTool

# PAUSED: Tests that interact with servers via web routes
pytestmark = pytest.mark.skip(reason="Paused: Tests interact with servers via web routes")


async def test_server_list(client: httpx.AsyncClient, db_session: AsyncSession):
    """
    Asserts that the main page loads and displays server data seeded into the test db_session.
    
    Args:
        client: HTTP test client
        db_session: Database session with test data
    """
    # Seed test data into database session
    test_server = MCPServer(
        id="test123",
        name="Test Server",
        type="container",
        command=["python", "-m", "test_server"],
        environment_vars={"TEST_VAR": "test_value"},
        is_active=True
    )
    
    # Add a tool for the server
    test_tool = MCPServerTool(
        id="tool123",
        server_id="test123",
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}}
    )
    
    # Add to session and commit
    db_session.add(test_server)
    db_session.add(test_tool)
    await db_session.commit()
    
    # Mock the database session in the route handler
    with patch('mcp_anywhere.web.routes.get_async_session') as mock_session:
        mock_session.return_value.__aenter__.return_value = db_session
        
        # Make request to homepage
        response = await client.get("/")
        
        # Assertions
        assert response.status_code == 200
        assert "MCP Anywhere" in response.text
        assert "Configured Servers" in response.text
        assert "Test Server" in response.text


async def test_add_server_flow(client: httpx.AsyncClient, db_session: AsyncSession):
    """
    Mocks the MCPManager.add_server call and tests the full form submission flow.
    
    Args:
        client: HTTP test client  
        db_session: Database session
    """
    # Mock the MCP Manager's add_server method
    mock_tools = [
        {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {"type": "object", "properties": {}}
        }
    ]
    
    with patch('mcp_anywhere.web.routes.get_async_session') as mock_session, \
         patch('mcp_anywhere.core.mcp_manager.store_server_tools') as mock_store_tools, \
         patch('mcp_anywhere.web.routes.get_mcp_manager') as mock_get_manager:
        
        # Setup mocks
        mock_session.return_value.__aenter__.return_value = db_session
        mock_store_tools.return_value = mock_tools
        
        mock_manager = Mock()
        mock_manager.add_server = AsyncMock(return_value=mock_tools)
        mock_get_manager.return_value = mock_manager
        
        # Test GET request to add server form
        response = await client.get("/servers/add")
        assert response.status_code == 200
        assert "Add New Server" in response.text
        
        # Test POST request with valid server data
        form_data = {
            "name": "New Test Server",
            "type": "container",
            "command": "python -m new_test_server",
            "environment_vars": '{"NEW_VAR": "new_value"}',
            "is_active": "true"
        }
        
        response = await client.post("/servers/add", data=form_data)
        
        # Should redirect to homepage on success
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        
        # Verify that the mocked add_server method was called
        mock_manager.add_server.assert_called_once()
        
        # Verify server was stored in database
        stored_server = await db_session.get(MCPServer, mock_manager.add_server.call_args[0][0].id)
        assert stored_server is not None
        assert stored_server.name == "New Test Server"
        assert stored_server.type == "container"
        assert stored_server.is_active == True