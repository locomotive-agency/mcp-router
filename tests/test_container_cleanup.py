"""Test container cleanup functionality."""

import pytest
from unittest.mock import Mock, patch
from docker.errors import NotFound, APIError

from src.mcp_anywhere.container.manager import ContainerManager

# PAUSED: Tests that work with container operations
pytestmark = pytest.mark.skip(reason="Paused: Tests work with Docker container cleanup")


@patch('src.mcp_anywhere.container.manager.DockerClient')
def test_cleanup_existing_container_success(mock_docker_client_class):
    """Test successful cleanup of existing container."""
    # Mock Docker client and containers
    mock_client = Mock()
    mock_docker_client_class.from_env.return_value = mock_client
    
    mock_container = Mock()
    mock_client.containers.get.return_value = mock_container
    
    # Create manager (will use mocked client)
    manager = ContainerManager()
    
    # Test cleanup
    container_name = "mcp-test123"
    manager._cleanup_existing_container(container_name)
    
    # Verify container was found, stopped, and removed
    mock_client.containers.get.assert_called_once_with(container_name)
    mock_container.stop.assert_called_once_with(timeout=10)
    mock_container.remove.assert_called_once_with(force=True)


@patch('src.mcp_anywhere.container.manager.DockerClient')  
def test_cleanup_existing_container_not_found(mock_docker_client_class):
    """Test cleanup when container doesn't exist."""
    # Mock Docker client to raise NotFound
    mock_client = Mock()
    mock_docker_client_class.from_env.return_value = mock_client
    mock_client.containers.get.side_effect = NotFound("Container not found")
    
    # Create manager
    manager = ContainerManager()
    
    # Test cleanup - should not raise exception
    container_name = "mcp-test123"
    manager._cleanup_existing_container(container_name)
    
    # Verify get was called but no stop/remove
    mock_client.containers.get.assert_called_once_with(container_name)


@patch('src.mcp_anywhere.container.manager.DockerClient')
def test_cleanup_existing_container_api_error(mock_docker_client_class):
    """Test cleanup handles Docker API errors gracefully."""
    # Mock Docker client
    mock_client = Mock()
    mock_docker_client_class.from_env.return_value = mock_client
    
    mock_container = Mock()
    mock_container.stop.side_effect = APIError("Stop failed")
    mock_client.containers.get.return_value = mock_container
    
    # Create manager
    manager = ContainerManager()
    
    # Test cleanup - should handle error gracefully
    container_name = "mcp-test123"
    manager._cleanup_existing_container(container_name)
    
    # Verify attempt was made despite error
    mock_client.containers.get.assert_called_once_with(container_name)
    mock_container.stop.assert_called_once_with(timeout=10)


def test_get_container_name():
    """Test container name generation."""
    with patch('src.mcp_anywhere.container.manager.DockerClient'):
        manager = ContainerManager()
        
        server_id = "test123"
        container_name = manager._get_container_name(server_id)
        
        assert container_name == "mcp-test123"