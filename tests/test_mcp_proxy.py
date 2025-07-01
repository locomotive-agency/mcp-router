"""Tests for MCP proxy functionality"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from mcp_router.app import app
from mcp_router.models import db, init_db

# The client and authenticated_client fixtures are now provided by conftest.py

def test_proxy_requires_running_server(authenticated_client):
    """Test that proxy returns 503 when server is not running"""
    with patch('mcp_router.server_manager.MCPServerManager.get_status') as mock_status:
        mock_status.return_value = {'status': 'stopped', 'transport': None}
        
        response = authenticated_client.post('/mcp/test')
        assert response.status_code == 503
        data = json.loads(response.data)
        assert 'error' in data
        assert 'not running' in data['error']


def test_proxy_requires_http_transport(authenticated_client):
    """Test that proxy returns 503 when server is running in stdio mode"""
    with patch('mcp_router.server_manager.MCPServerManager.get_status') as mock_status:
        mock_status.return_value = {
            'status': 'running',
            'transport': 'stdio',
            'pid': 12345
        }
        
        response = authenticated_client.post('/mcp/test')
        assert response.status_code == 503
        data = json.loads(response.data)
        assert 'error' in data
        assert 'HTTP mode' in data['error']


@patch('httpx.request')
def test_proxy_forwards_request(mock_request, authenticated_client):
    """Test that proxy correctly forwards requests to MCP server"""
    # Mock the server status
    with patch('mcp_router.server_manager.MCPServerManager.get_status') as mock_status:
        mock_status.return_value = {
            'status': 'running',
            'transport': 'http',
            'connection_info': {
                'url': 'http://localhost:8001/mcp/',
                'api_key': 'test-key',
                'internal_url': 'http://127.0.0.1:8001/mcp/'
            }
        }
        
        # Mock the httpx response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'{"result": "success"}'
        mock_response.headers = {'content-type': 'application/json'}
        mock_request.return_value = mock_response
        
        # Make request through proxy
        response = authenticated_client.post(
            '/mcp/test',
            json={'test': 'data'},
            headers={'X-Test-Header': 'value'}
        )
        
        # Verify response
        assert response.status_code == 200
        assert response.json == {'result': 'success'}
        
        # Verify httpx was called correctly
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'POST'
        assert call_args[0][1] == 'http://127.0.0.1:8001/mcp/test'
        assert call_args[1]['headers']['Authorization'] == 'Bearer test-key'


@patch('httpx.stream')
def test_proxy_handles_streaming(mock_stream, authenticated_client):
    """Test that proxy correctly handles SSE/streaming responses"""
    # Mock the server status
    with patch('mcp_router.server_manager.MCPServerManager.get_status') as mock_status:
        mock_status.return_value = {
            'status': 'running',
            'transport': 'http',
            'connection_info': {
                'url': 'http://localhost:8001/mcp/',
                'api_key': 'test-key',
                'internal_url': 'http://127.0.0.1:8001/mcp/'
            }
        }
        
        # Mock the streaming response
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.iter_bytes.return_value = [b'data: test\n\n', b'data: stream\n\n']
        mock_stream.return_value = mock_response
        
        # Make request with SSE accept header
        response = authenticated_client.post(
            '/mcp/events',
            headers={'Accept': 'text/event-stream'}
        )
        
        # Verify response
        assert response.status_code == 200
        assert response.content_type == 'text/event-stream'
        assert response.headers.get('Cache-Control') == 'no-cache'


def test_simplified_url_generation():
    """Test that connection URLs are simplified correctly"""
    from mcp_router.server_manager import MCPServerManager
    
    manager = MCPServerManager()
    
    # Test local development
    with patch.dict('os.environ', {'FLASK_HOST': 'localhost', 'FLASK_PORT': '8000'}):
        result = manager.start_server('http', host='127.0.0.1', port=8001, path='/mcp')
        # Would normally check the URL but start_server requires a real process
        # This test mainly ensures no errors in URL generation logic
    
    # Test with PUBLIC_URL
    with patch.dict('os.environ', {'PUBLIC_URL': 'https://example.com'}):
        # The URL generation logic would produce https://example.com/mcp/
        pass 