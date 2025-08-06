import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch

from mcp_anywhere.core.mcp_manager import MCPManager
from mcp_anywhere.database import MCPServer

# PAUSED: Tests that mount and manage MCP servers
pytestmark = pytest.mark.skip(reason="Paused: Tests mount and manage MCP servers")


@pytest_asyncio.fixture
async def mock_fastmcp_anywhere():
    """Mock FastMCP router for testing"""
    router = Mock()
    router.mount = Mock()
    router._tool_manager = Mock()
    router._resource_manager = Mock()
    router._prompt_manager = Mock()
    router._cache = Mock()
    router._cache.clear = Mock()
    return router


@pytest_asyncio.fixture
async def sample_server():
    """Sample server for testing"""
    return MCPServer(
        id="test123",
        name="Test Server",
        runtime_type="docker",
        start_command="echo hello",
        github_url="https://github.com/test/repo",
        env_variables=[]  # Add empty list for env_variables
    )


@pytest_asyncio.fixture
async def mcp_manager(mock_fastmcp_anywhere):
    """MCPManager instance for testing"""
    return MCPManager(mock_fastmcp_anywhere)


@pytest.mark.asyncio
async def test_mcp_manager_initialization(mock_fastmcp_anywhere):
    """Test that MCPManager initializes correctly"""
    manager = MCPManager(mock_fastmcp_anywhere)
    
    assert manager.router == mock_fastmcp_anywhere
    assert manager.mounted_servers == {}


@pytest.mark.asyncio
async def test_add_server_success(mcp_manager: MCPManager, sample_server: MCPServer):
    """Test successfully adding a server to the MCP manager"""
    with patch('mcp_anywhere.core.mcp_manager.FastMCP') as mock_fastmcp, \
         patch('mcp_anywhere.core.mcp_manager.ContainerManager') as mock_container_manager:
        
        # Mock the proxy creation
        mock_proxy = Mock()
        mock_fastmcp.as_proxy.return_value = mock_proxy
        
        # Mock container manager
        mock_cm_instance = Mock()
        mock_cm_instance.get_image_tag.return_value = "test-image:latest"
        mock_cm_instance._parse_start_command.return_value = ["echo", "hello"]
        mock_container_manager.return_value = mock_cm_instance
        
        # Mock tools discovery
        mock_proxy._tool_manager = Mock()
        mock_proxy._tool_manager.get_tools = AsyncMock(return_value={
            "test_tool": Mock(description="A test tool")
        })
        
        # Execute
        tools = await mcp_manager.add_server(sample_server)
        
        # Verify router.mount was called
        mcp_manager.router.mount.assert_called_once_with(mock_proxy, prefix="test123")
        
        # Verify server was tracked
        assert sample_server.id in mcp_manager.mounted_servers
        assert mcp_manager.mounted_servers[sample_server.id] == mock_proxy
        
        # Verify tools were returned
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"
        assert tools[0]["description"] == "A test tool"


@pytest.mark.asyncio
async def test_remove_server_success(mcp_manager: MCPManager, sample_server: MCPServer):
    """Test successfully removing a server from the MCP manager"""
    # Setup - add a server first
    mock_proxy = Mock()
    mock_proxy._tool_manager = Mock()
    mock_proxy._resource_manager = Mock()
    mock_proxy._prompt_manager = Mock()
    
    mcp_manager.mounted_servers[sample_server.id] = mock_proxy
    
    # Mock the mounted servers lists for each manager
    for manager in [mcp_manager.router._tool_manager, 
                   mcp_manager.router._resource_manager, 
                   mcp_manager.router._prompt_manager]:
        mount_mock = Mock()
        mount_mock.server = mock_proxy
        manager._mounted_servers = [mount_mock]
    
    # Execute
    mcp_manager.remove_server(sample_server.id)
    
    # Verify server was removed from tracking
    assert sample_server.id not in mcp_manager.mounted_servers
    
    # Verify cache was cleared
    mcp_manager.router._cache.clear.assert_called_once()


@pytest.mark.asyncio 
async def test_remove_server_not_found(mcp_manager: MCPManager):
    """Test removing a server that doesn't exist"""
    # Should not raise an exception, just log a warning
    mcp_manager.remove_server("nonexistent")
    
    # Verify no changes
    assert len(mcp_manager.mounted_servers) == 0