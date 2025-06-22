"""
Test suite for MCP Router implementation.

Tests the core router functionality, transport management, and client management.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from mcp_router.core.router import MCPRouterServer
from mcp_router.core.transport import TransportManager, TransportType, TransportConfig
from mcp_router.core.client import MCPClientManager, MCPTool, MCPResource, MCPPrompt
from mcp_router.config.settings import Settings
from mcp_router.services.container_manager import ContainerManager


class TestMCPRouterServer:
    """Test cases for MCPRouterServer."""
    
    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(
            database_url="sqlite+aiosqlite:///test.db",
            mcp_mode="server",
            is_development=True
        )
    
    @pytest.fixture
    def router(self, settings):
        """Create test router instance."""
        return MCPRouterServer(settings)
    
    def test_router_initialization(self, router):
        """Test router initializes correctly."""
        assert router.mcp is not None
        assert router.container_manager is not None
        assert router.transport_manager is not None
        assert router.client_manager is not None
        assert "python_sandbox" in router.mcp.tools
        assert "list_available_servers" in router.mcp.tools
        assert "refresh_server_tools" in router.mcp.tools
    
    @pytest.mark.asyncio
    async def test_handle_initialize_request(self, router):
        """Test MCP initialize request handling."""
        result = await router.handle_mcp_request("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })
        
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "mcp-router"
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]
        assert "prompts" in result["capabilities"]
    
    @pytest.mark.asyncio
    async def test_handle_tools_list_request(self, router):
        """Test tools/list request handling."""
        # Mock the client manager to return no external tools
        router.client_manager.list_all_tools = AsyncMock(return_value=[])
        
        result = await router.handle_mcp_request("tools/list", {})
        
        assert "tools" in result
        tools = result["tools"]
        
        # Should include default tools
        tool_names = [tool["name"] for tool in tools]
        assert "python_sandbox" in tool_names
        assert "list_available_servers" in tool_names
        assert "refresh_server_tools" in tool_names
    
    @pytest.mark.asyncio
    async def test_handle_tools_call_default_tool(self, router):
        """Test calling a default tool."""
        result = await router.handle_mcp_request("tools/call", {
            "name": "python_sandbox",
            "arguments": {"code": "print('Hello, World!')"}
        })
        
        assert "content" in result
        content = json.loads(result["content"][0]["text"])
        assert "output" in content
        assert "error" in content
        assert "exit_code" in content
    
    @pytest.mark.asyncio
    async def test_handle_resources_list_request(self, router):
        """Test resources/list request handling."""
        # Mock the client manager to return no resources
        router.client_manager.list_all_resources = AsyncMock(return_value=[])
        
        result = await router.handle_mcp_request("resources/list", {})
        
        assert "resources" in result
        assert isinstance(result["resources"], list)
    
    @pytest.mark.asyncio
    async def test_handle_prompts_list_request(self, router):
        """Test prompts/list request handling."""
        # Mock the client manager to return no prompts
        router.client_manager.list_all_prompts = AsyncMock(return_value=[])
        
        result = await router.handle_mcp_request("prompts/list", {})
        
        assert "prompts" in result
        assert isinstance(result["prompts"], list)
    
    @pytest.mark.asyncio
    async def test_handle_unknown_method(self, router):
        """Test handling of unknown method."""
        with pytest.raises(ValueError, match="Unknown method"):
            await router.handle_mcp_request("unknown/method", {})


class TestTransportManager:
    """Test cases for TransportManager."""
    
    @pytest.fixture
    def transport_manager(self):
        """Create test transport manager."""
        return TransportManager()
    
    @pytest.mark.asyncio
    async def test_create_http_transport(self, transport_manager):
        """Test creating HTTP transport."""
        config = TransportConfig(
            type=TransportType.HTTP,
            endpoint="http://localhost:8080",
            timeout=30
        )
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()
            
            # Mock the transport creation to avoid actual HTTP calls
            with patch('mcp_router.core.transport.HTTPTransport.connect', return_value=True):
                transport = await transport_manager.create_transport("test-server", config)
                
                assert transport is not None
                assert "test-server" in transport_manager.transports
    
    @pytest.mark.asyncio
    async def test_remove_transport(self, transport_manager):
        """Test removing a transport."""
        # Create a mock transport
        mock_transport = Mock()
        mock_transport.disconnect = AsyncMock()
        transport_manager.transports["test-server"] = mock_transport
        
        await transport_manager.remove_transport("test-server")
        
        assert "test-server" not in transport_manager.transports
        mock_transport.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup_all_transports(self, transport_manager):
        """Test cleaning up all transports."""
        # Create mock transports
        mock_transport1 = Mock()
        mock_transport1.disconnect = AsyncMock()
        mock_transport2 = Mock()
        mock_transport2.disconnect = AsyncMock()
        
        transport_manager.transports["server1"] = mock_transport1
        transport_manager.transports["server2"] = mock_transport2
        
        await transport_manager.cleanup_all()
        
        assert len(transport_manager.transports) == 0
        mock_transport1.disconnect.assert_called_once()
        mock_transport2.disconnect.assert_called_once()


class TestMCPClientManager:
    """Test cases for MCPClientManager."""
    
    @pytest.fixture
    def container_manager(self):
        """Create mock container manager."""
        mock_manager = Mock(spec=ContainerManager)
        mock_manager.create_session = AsyncMock(return_value="session-123")
        mock_manager.start_session = AsyncMock(return_value=True)
        mock_manager.execute_command = AsyncMock()
        mock_manager.stop_session = AsyncMock()
        return mock_manager
    
    @pytest.fixture
    def transport_manager(self):
        """Create mock transport manager."""
        mock_manager = Mock(spec=TransportManager)
        mock_manager.create_transport = AsyncMock()
        mock_manager.get_transport = AsyncMock()
        mock_manager.remove_transport = AsyncMock()
        return mock_manager
    
    @pytest.fixture
    def client_manager(self, container_manager, transport_manager):
        """Create test client manager."""
        return MCPClientManager(container_manager, transport_manager)
    
    @pytest.mark.asyncio
    async def test_list_all_tools_empty(self, client_manager):
        """Test listing tools when no servers are active."""
        # Mock database to return no servers
        with patch('mcp_router.core.client.get_database') as mock_get_db:
            mock_db = Mock()
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()
            mock_get_db.return_value = mock_db
            
            tools = await client_manager.list_all_tools()
            
            assert isinstance(tools, list)
            assert len(tools) == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_all_clients(self, client_manager):
        """Test cleaning up all clients."""
        # Add mock clients
        mock_client1 = Mock()
        mock_client1.server_id = "server1"
        mock_client1.container_session_id = "session1"
        mock_client1.process = None
        
        mock_client2 = Mock()
        mock_client2.server_id = "server2"
        mock_client2.container_session_id = "session2"
        mock_client2.process = None
        
        client_manager.clients["server1"] = mock_client1
        client_manager.clients["server2"] = mock_client2
        
        await client_manager.cleanup_all()
        
        assert len(client_manager.clients) == 0


class TestMCPDataModels:
    """Test cases for MCP data models."""
    
    def test_mcp_tool_to_dict(self):
        """Test MCPTool to_dict method."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            server_id="server-123"
        )
        
        result = tool.to_dict()
        
        assert result["name"] == "test_tool"
        assert result["description"] == "A test tool"
        assert result["inputSchema"]["type"] == "object"
    
    def test_mcp_resource_to_dict(self):
        """Test MCPResource to_dict method."""
        resource = MCPResource(
            uri="file://test.txt",
            name="Test File",
            description="A test file",
            mime_type="text/plain",
            server_id="server-123"
        )
        
        result = resource.to_dict()
        
        assert result["uri"] == "file://test.txt"
        assert result["name"] == "Test File"
        assert result["description"] == "A test file"
        assert result["mimeType"] == "text/plain"
    
    def test_mcp_prompt_to_dict(self):
        """Test MCPPrompt to_dict method."""
        prompt = MCPPrompt(
            name="test_prompt",
            description="A test prompt",
            arguments=[{"name": "input", "type": "string"}],
            server_id="server-123"
        )
        
        result = prompt.to_dict()
        
        assert result["name"] == "test_prompt"
        assert result["description"] == "A test prompt"
        assert len(result["arguments"]) == 1
        assert result["arguments"][0]["name"] == "input"


@pytest.mark.asyncio
async def test_router_integration_flow():
    """Integration test for the complete router flow."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///test.db",
        mcp_mode="server",
        is_development=True
    )
    
    router = MCPRouterServer(settings)
    
    try:
        # Test initialization
        await router.initialize()
        
        # Test MCP protocol flow
        init_result = await router.handle_mcp_request("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test", "version": "1.0"}
        })
        assert init_result["protocolVersion"] == "2024-11-05"
        
        # Test initialized notification
        init_ack = await router.handle_mcp_request("initialized", {})
        assert init_ack["acknowledged"] == True
        
        # Test tools listing
        tools_result = await router.handle_mcp_request("tools/list", {})
        assert "tools" in tools_result
        assert len(tools_result["tools"]) >= 3  # At least our default tools
        
        # Test calling a tool
        tool_result = await router.handle_mcp_request("tools/call", {
            "name": "list_available_servers",
            "arguments": {}
        })
        assert "content" in tool_result
        
    finally:
        # Cleanup
        await router.cleanup()


if __name__ == "__main__":
    # Run the integration test
    asyncio.run(test_router_integration_flow())