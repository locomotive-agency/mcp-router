"""Tests for the DynamicServerManager functionality"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from mcp_router.server import DynamicServerManager, create_router
from mcp_router.models import MCPServer


class TestDynamicServerManager:
    """Test cases for DynamicServerManager"""
    
    def test_init(self):
        """Test DynamicServerManager initialization"""
        mock_router = Mock()
        manager = DynamicServerManager(mock_router)
        
        assert manager.router == mock_router
        assert manager.mounted_servers == {}
        assert manager.server_descriptions == {}
    
    def test_add_server(self):
        """Test adding a server dynamically"""
        mock_router = Mock()
        manager = DynamicServerManager(mock_router)

        # Create a mock server
        mock_server = Mock(spec=MCPServer)
        mock_server.name = "test-server"
        mock_server.description = "Test server description"
        mock_server.runtime_type = "npx"
        mock_server.start_command = "test-command"
        mock_server.env_variables = []

        # Mock the FastMCP.as_proxy method
        with patch('mcp_router.server.FastMCP.as_proxy') as mock_as_proxy, \
             patch('mcp_router.server.create_mcp_config') as mock_create_config:

            mock_proxy = Mock()
            mock_as_proxy.return_value = mock_proxy
            mock_create_config.return_value = {"mcpServers": {"test-server": {}}}

            # Add the server
            manager.add_server(mock_server)

            # Verify the server was added
            assert "test-server" in manager.mounted_servers
            assert manager.mounted_servers["test-server"] == mock_proxy
            assert manager.server_descriptions["test-server"] == "Test server description"

            # Verify mount was called
            mock_router.mount.assert_called_once_with(mock_proxy, prefix="test-server")

    def test_add_server_no_description(self):
        """Test adding a server with no description"""
        mock_router = Mock()
        manager = DynamicServerManager(mock_router)

        # Create a mock server without description
        mock_server = Mock(spec=MCPServer)
        mock_server.name = "test-server"
        mock_server.description = None
        mock_server.runtime_type = "npx"
        mock_server.start_command = "test-command"
        mock_server.env_variables = []

        # Mock the FastMCP.as_proxy method
        with patch('mcp_router.server.FastMCP.as_proxy') as mock_as_proxy, \
             patch('mcp_router.server.create_mcp_config') as mock_create_config:

            mock_proxy = Mock()
            mock_as_proxy.return_value = mock_proxy
            mock_create_config.return_value = {"mcpServers": {"test-server": {}}}

            # Add the server
            manager.add_server(mock_server)

            # Verify the server was added with default description
            assert "test-server" in manager.mounted_servers
            assert manager.server_descriptions["test-server"] == "No description provided"

    def test_remove_server(self):
        """Test removing a server dynamically"""
        mock_router = Mock()
        # Mock the internal managers
        mock_tool_manager = Mock()
        mock_resource_manager = Mock()
        mock_prompt_manager = Mock()
        
        mock_router._tool_manager = mock_tool_manager
        mock_router._resource_manager = mock_resource_manager
        mock_router._prompt_manager = mock_prompt_manager
        mock_router._cache = Mock()
        
        # Mock the mounted_servers lists
        mock_tool_manager._mounted_servers = []
        mock_resource_manager._mounted_servers = []
        mock_prompt_manager._mounted_servers = []
        
        manager = DynamicServerManager(mock_router)

        # Add a server first
        mock_server = Mock()
        manager.mounted_servers["test-server"] = mock_server
        manager.server_descriptions["test-server"] = "Test description"

        # Remove the server
        manager.remove_server("test-server")

        # Verify the server was removed
        assert "test-server" not in manager.mounted_servers
        assert "test-server" not in manager.server_descriptions
        
        # Verify cache was cleared
        mock_router._cache.clear.assert_called_once()

    def test_remove_nonexistent_server(self):
        """Test removing a server that doesn't exist"""
        mock_router = Mock()
        manager = DynamicServerManager(mock_router)

        # Try to remove a server that doesn't exist
        manager.remove_server("nonexistent-server")

        # Should not raise an exception, just log a warning
    
    def test_get_providers(self):
        """Test getting providers list"""
        mock_router = Mock()
        manager = DynamicServerManager(mock_router)
        
        # Add some servers
        manager.server_descriptions["server1"] = "Description 1"
        manager.server_descriptions["server2"] = "Description 2"
        
        providers = manager.get_providers()
        
        assert len(providers) == 2
        assert {"name": "server1", "description": "Description 1"} in providers
        assert {"name": "server2", "description": "Description 2"} in providers
    
    def test_get_provider_names(self):
        """Test getting provider names only"""
        mock_router = Mock()
        manager = DynamicServerManager(mock_router)
        
        # Add some servers
        manager.server_descriptions["server1"] = "Description 1"
        manager.server_descriptions["server2"] = "Description 2"
        
        names = manager.get_provider_names()
        
        assert len(names) == 2
        assert "server1" in names
        assert "server2" in names


class TestCreateRouter:
    """Test cases for create_router function"""
    
    def test_create_router_empty_servers(self):
        """Test creating router with no servers"""
        with patch('mcp_router.server.DynamicServerManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            
            router = create_router([])
            
            assert router is not None
            assert hasattr(router, '_dynamic_manager')
            mock_manager_class.assert_called_once_with(router)
    
    def test_create_router_with_servers(self):
        """Test creating router with servers"""
        mock_server = Mock(spec=MCPServer)
        mock_server.name = "test-server"
        mock_server.description = "Test description"
        mock_server.runtime_type = "npx"
        mock_server.start_command = "test-command"
        mock_server.env_variables = []

        with patch('mcp_router.server.DynamicServerManager') as mock_manager_class, \
             patch('mcp_router.server.FastMCP.as_proxy') as mock_as_proxy, \
             patch('mcp_router.server.create_mcp_config') as mock_create_config:

            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            mock_proxy = Mock()
            mock_as_proxy.return_value = mock_proxy
            mock_create_config.return_value = {"mcpServers": {"test-server": {}}}

            router = create_router([mock_server])

            assert router is not None
            assert hasattr(router, '_dynamic_manager')
            # Verify the manager was created and server was mounted
            mock_manager_class.assert_called_once()
            mock_as_proxy.assert_called_once()
            mock_create_config.assert_called_once_with([mock_server]) 