"""
Unit tests for MCP Router HTTP transport functionality.

These tests verify that the MCP server can be started with HTTP transport
and responds correctly to client requests.
"""
import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock
from mcp_router.server_manager import MCPServerManager
from mcp_router.models import MCPServerStatus


class TestMCPHTTPTransport:
    """Test cases for MCP HTTP transport"""
    
    def test_server_manager_initialization(self):
        """Test that server manager initializes correctly"""
        manager = MCPServerManager()
        assert manager.process is None
        assert manager.thread is None
        assert manager.api_key is None
    
    @patch('mcp_router.server_manager.subprocess.Popen')
    @patch('mcp_router.server_manager.update_server_status')
    @patch('mcp_router.server_manager.get_server_status')
    def test_start_server_http(self, mock_get_status, mock_update_status, mock_popen):
        """Test starting server with HTTP transport"""
        # Setup mocks
        mock_get_status.return_value = None  # No server running
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        manager = MCPServerManager()
        result = manager.start_server('http', host='127.0.0.1', port=8001, path='/mcp')
        
        # Verify subprocess was called correctly
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        
        # Check environment variables
        env = call_args[1]['env']
        assert env['MCP_TRANSPORT'] == 'http'
        assert env['MCP_HOST'] == '127.0.0.1'
        assert env['MCP_PORT'] == '8001'
        assert env['MCP_PATH'] == '/mcp'
        assert 'MCP_API_KEY' in env
        
        # Check response
        assert result['status'] == 'success'
        assert result['transport'] == 'http'
        assert result['pid'] == 12345
        assert 'connection_info' in result
        assert result['connection_info']['type'] == 'http'
        assert result['connection_info']['url'] == 'http://127.0.0.1:8001/mcp'
    
    @patch('mcp_router.server_manager.subprocess.Popen')
    @patch('mcp_router.server_manager.update_server_status')
    @patch('mcp_router.server_manager.get_server_status')
    def test_start_server_stdio(self, mock_get_status, mock_update_status, mock_popen):
        """Test starting server with stdio transport"""
        # Setup mocks
        mock_get_status.return_value = None  # No server running
        mock_process = MagicMock()
        mock_process.pid = 12346
        mock_popen.return_value = mock_process
        
        manager = MCPServerManager()
        result = manager.start_server('stdio')
        
        # Verify subprocess was called correctly
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        
        # Check environment variables
        env = call_args[1]['env']
        assert env['MCP_TRANSPORT'] == 'stdio'
        assert 'MCP_API_KEY' not in env  # No API key for stdio
        
        # Check response
        assert result['status'] == 'success'
        assert result['transport'] == 'stdio'
        assert result['connection_info']['type'] == 'stdio'
        assert result['connection_info']['command'] == 'python -m mcp_router'
    
    @patch('mcp_router.server_manager.get_server_status')
    def test_start_server_already_running(self, mock_get_status):
        """Test starting server when one is already running"""
        # Mock existing running server
        mock_status = MagicMock()
        mock_status.status = 'running'
        mock_status.to_dict.return_value = {'status': 'running', 'transport': 'http'}
        mock_get_status.return_value = mock_status
        
        manager = MCPServerManager()
        result = manager.start_server('http')
        
        assert result['status'] == 'error'
        assert 'already running' in result['message']
        assert result['current'] == {'status': 'running', 'transport': 'http'}
    
    @patch('mcp_router.server_manager.update_server_status')
    @patch('mcp_router.server_manager.get_server_status')
    def test_stop_server(self, mock_get_status, mock_update_status):
        """Test stopping a running server"""
        # Mock running server
        mock_status = MagicMock()
        mock_status.status = 'running'
        mock_status.transport = 'http'
        mock_get_status.return_value = mock_status
        
        # Create manager with mock process
        manager = MCPServerManager()
        manager.process = MagicMock()
        
        result = manager.stop_server()
        
        # Verify process was terminated
        manager.process.terminate.assert_called_once()
        
        # Check response
        assert result['status'] == 'success'
        assert 'stopped successfully' in result['message']
    
    @patch('mcp_router.server_manager.get_server_status')
    def test_stop_server_not_running(self, mock_get_status):
        """Test stopping server when none is running"""
        mock_get_status.return_value = None
        
        manager = MCPServerManager()
        result = manager.stop_server()
        
        assert result['status'] == 'error'
        assert 'No server is running' in result['message']
    
    @patch('mcp_router.server_manager.get_server_status')
    def test_get_status_with_http_server(self, mock_get_status):
        """Test getting status of running HTTP server"""
        # Mock HTTP server status
        mock_status = MagicMock()
        mock_status.status = 'running'
        mock_status.transport = 'http'
        mock_status.host = '127.0.0.1'
        mock_status.port = 8001
        mock_status.path = '/mcp'
        mock_status.api_key = 'test-key'
        mock_status.to_dict.return_value = {
            'status': 'running',
            'transport': 'http'
        }
        mock_get_status.return_value = mock_status
        
        manager = MCPServerManager()
        result = manager.get_status()
        
        assert result['status'] == 'running'
        assert result['transport'] == 'http'
        assert 'connection_info' in result
        assert result['connection_info']['type'] == 'http'
        assert result['connection_info']['url'] == 'http://127.0.0.1:8001/mcp'
        assert result['connection_info']['api_key'] == 'test-key'


# Integration test that can be run manually
@pytest.mark.integration
async def test_real_http_connection():
    """
    Integration test for real HTTP connection.
    
    This test requires a running MCP server with HTTP transport.
    Mark with @pytest.mark.integration and run with: pytest -m integration
    """
    from fastmcp import Client
    
    host = os.environ.get('MCP_HOST', '127.0.0.1')
    port = os.environ.get('MCP_PORT', '8001')
    path = os.environ.get('MCP_PATH', '/mcp')
    api_key = os.environ.get('MCP_API_KEY')
    
    url = f"http://{host}:{port}{path}"
    client_args = {"api_key": api_key} if api_key else {}
    
    try:
        async with Client(url, **client_args) as client:
            # Test listing tools
            tools = await client.list_tools()
            assert len(tools) >= 2  # Should have at least python_sandbox and list_providers
            
            # Test list_providers
            tool_names = [tool.name for tool in tools]
            assert 'list_providers' in tool_names
            assert 'python_sandbox' in tool_names
            
            # Test calling python_sandbox
            result = await client.call_tool(
                "python_sandbox",
                {"code": "print(1 + 1)"}
            )
            assert result.content
            assert "2" in result.content[0].text
            
    except Exception as e:
        pytest.fail(f"HTTP connection test failed: {e}") 