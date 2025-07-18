"""Integration tests for dynamic server management"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from mcp_router.models import MCPServer, db
from mcp_router.server import get_dynamic_manager
from mcp_router.config import Config


class TestDynamicIntegration:
    """Integration tests for dynamic server management"""
    
    @pytest.fixture
    def app(self):
        """Create test Flask app"""
        from mcp_router.app import app
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    def test_dynamic_manager_available_after_server_creation(self, app):
        """Test that dynamic manager is available after server creation"""
        with app.app_context():
            from mcp_router.server import create_router
            
            # Create router with empty servers
            router = create_router([])
            
            # Verify dynamic manager is available
            assert hasattr(router, '_dynamic_manager')
            assert router._dynamic_manager is not None
    
    def test_list_providers_tool_returns_correct_format(self, app):
        """Test that list_providers tool returns the correct format"""
        with app.app_context():
            from mcp_router.server import create_router
            
            # Create a mock server
            mock_server = Mock(spec=MCPServer)
            mock_server.name = "test-server"
            mock_server.description = "Test server description"
            mock_server.runtime_type = "npx"
            mock_server.start_command = "test-command"
            mock_server.env_variables = []
            
            # Create router with mock server
            with patch('mcp_router.server.create_mcp_config') as mock_create_config, \
                 patch('mcp_router.server.FastMCP.as_proxy') as mock_as_proxy, \
                 patch('asyncio.create_task') as mock_create_task:
                
                mock_create_config.return_value = {"mcpServers": {"test-server": {}}}
                mock_as_proxy.return_value = Mock()
                
                router = create_router([mock_server])
                
                # Get the list_providers tool
                tools = router._tool_manager._tools
                list_providers_tool = None
                for tool in tools.values():
                    if tool.name == "list_providers":
                        list_providers_tool = tool
                        break
                
                assert list_providers_tool is not None
                
                # Execute the tool (this will be empty since we mocked the async task)
                result = list_providers_tool.fn()
                
                # Should return a list of dictionaries
                assert isinstance(result, list)
    
    def test_handle_dynamic_server_update_http_mode(self, app):
        """Test dynamic server update handling in HTTP mode"""
        with app.app_context():
            from mcp_router.routes.servers import handle_dynamic_server_update

            # Set HTTP mode
            original_transport = Config.MCP_TRANSPORT
            Config.MCP_TRANSPORT = "http"

            try:
                # Create a mock server
                mock_server = Mock(spec=MCPServer)
                mock_server.name = "test-server"
                mock_server.description = "Test description"

                # Mock the dynamic manager
                with patch('mcp_router.server.get_dynamic_manager') as mock_get_manager:

                    mock_manager = Mock()
                    mock_get_manager.return_value = mock_manager

                    # Test add operation
                    handle_dynamic_server_update(mock_server, "add")

                    # Verify the manager method was called directly
                    mock_manager.add_server.assert_called_once_with(mock_server)

                    # Test delete operation
                    handle_dynamic_server_update(mock_server, "delete")
                    mock_manager.remove_server.assert_called_once_with("test-server")

                    # Test update operation
                    handle_dynamic_server_update(mock_server, "update")
                    # Should call remove and add
                    assert mock_manager.remove_server.call_count == 2
                    assert mock_manager.add_server.call_count == 2

            finally:
                # Restore original transport
                Config.MCP_TRANSPORT = original_transport
    
    def test_handle_dynamic_server_update_stdio_mode(self, app):
        """Test dynamic server update handling in STDIO mode"""
        with app.app_context():
            from mcp_router.routes.servers import handle_dynamic_server_update
            
            # Set STDIO mode
            original_transport = Config.MCP_TRANSPORT
            Config.MCP_TRANSPORT = "stdio"
            
            try:
                # Create a mock server
                mock_server = Mock(spec=MCPServer)
                mock_server.name = "test-server"
                
                with patch('asyncio.create_task') as mock_create_task:
                    # Test add operation
                    handle_dynamic_server_update(mock_server, "add")
                    
                    # Verify create_task was NOT called in STDIO mode
                    mock_create_task.assert_not_called()
                    
            finally:
                # Restore original transport
                Config.MCP_TRANSPORT = original_transport
    
    def test_dynamic_server_update_direct_call(self, app):
        """Test that dynamic server update function works correctly"""
        with app.app_context():
            from mcp_router.routes.servers import handle_dynamic_server_update
            from mcp_router.models import MCPServer

            # Set HTTP mode
            original_transport = Config.MCP_TRANSPORT
            Config.MCP_TRANSPORT = "http"

            try:
                # Create a real server instance
                server = MCPServer(
                    name='test-server',
                    github_url='https://github.com/test/repo',
                    description='Test server',
                    runtime_type='npx',
                    start_command='test-command',
                    env_variables=[]
                )

                # Mock the dynamic manager
                with patch('mcp_router.server.get_dynamic_manager') as mock_get_manager:

                    mock_manager = Mock()
                    mock_get_manager.return_value = mock_manager

                    # Test add operation
                    handle_dynamic_server_update(server, "add")

                    # Verify the manager method was called directly
                    mock_manager.add_server.assert_called_once_with(server)

            finally:
                # Restore original transport
                Config.MCP_TRANSPORT = original_transport 