"""Test for container restart conflict resolution."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from docker.errors import NotFound

from src.mcp_anywhere.core.mcp_manager import MCPManager
from src.mcp_anywhere.container.manager import ContainerManager

# PAUSED: Tests that work with container deployment and cleanup
pytestmark = pytest.mark.skip(reason="Paused: Tests work with Docker containers")


@pytest.mark.asyncio
async def test_add_server_cleans_existing_container():
    """Test that add_server cleans up existing containers before mounting."""
    # Mock FastMCP router
    mock_router = Mock()
    mcp_manager = MCPManager(mock_router)
    
    # Mock server config
    mock_server = Mock()
    mock_server.id = "test123"
    mock_server.name = "Test Server"
    
    # Mock container manager
    mock_container_manager = Mock(spec=ContainerManager)
    
    # Mock the cleanup method
    mock_container_manager._cleanup_existing_container = Mock()
    
    # Mock the proxy creation to avoid actual Docker operations
    with patch('src.mcp_anywhere.core.mcp_manager.create_mcp_config') as mock_config, \
         patch('src.mcp_anywhere.core.mcp_manager.FastMCP') as mock_fast_mcp:
        
        # Setup mocks
        mock_config.return_value = {"mcpServers": {"Test Server": {}}}
        mock_proxy = Mock()
        mock_fast_mcp.as_proxy.return_value = mock_proxy
        
        # Mock the discovery method to return empty tools
        mcp_manager._discover_server_tools = AsyncMock(return_value=[])
        
        # Call add_server with container manager
        await mcp_manager.add_server(mock_server, container_manager=mock_container_manager)
        
        # Verify cleanup was called with correct container name
        mock_container_manager._cleanup_existing_container.assert_called_once_with("mcp-test123")
        
        # Verify server was mounted
        mock_router.mount.assert_called_once_with(mock_proxy, prefix="test123")


def test_container_cleanup_logic():
    """Test the container cleanup logic directly."""
    container_manager = ContainerManager()
    
    # Mock Docker client
    mock_docker_client = Mock()
    container_manager.docker_client = mock_docker_client
    
    # Mock running container
    mock_container = Mock()
    mock_container.status = "running"
    mock_docker_client.containers.get.return_value = mock_container
    
    # Call cleanup
    container_manager._cleanup_existing_container("mcp-test")
    
    # Verify stop and remove were called
    mock_container.stop.assert_called_once_with(timeout=5)
    mock_container.remove.assert_called_once()


def test_container_cleanup_handles_missing_container():
    """Test that cleanup gracefully handles missing containers."""
    container_manager = ContainerManager()
    
    # Mock Docker client to raise NotFound
    mock_docker_client = Mock()
    container_manager.docker_client = mock_docker_client
    mock_docker_client.containers.get.side_effect = NotFound("Container not found")
    
    # Should not raise an exception
    container_manager._cleanup_existing_container("mcp-nonexistent")
    
    # Verify get was called but no stop/remove operations
    mock_docker_client.containers.get.assert_called_once_with("mcp-nonexistent")