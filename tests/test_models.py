"""Tests for MCP Router models"""
import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_router.models import MCPServer


class TestMCPServer(unittest.TestCase):
    """Test cases for MCPServer model"""
    
    def test_env_variables_json_conversion(self):
        """Test that environment variables are properly serialized/deserialized"""
        server = MCPServer()
        test_env = [
            {'key': 'API_KEY', 'value': 'test123', 'description': 'Test API key'},
            {'key': 'SECRET', 'value': 'secret456', 'description': 'Secret value'}
        ]
        
        server.env_variables = test_env
        self.assertEqual(server.env_variables, test_env)
        
    def test_server_representation(self):
        """Test string representation of server"""
        server = MCPServer()
        server.name = "test-server"
        self.assertEqual(str(server), "<MCPServer test-server>")


if __name__ == '__main__':
    unittest.main() 