
import asyncio
import unittest
import pytest
from unittest.mock import MagicMock, patch
from mcp_router.server import create_mcp_config, MCPManager
from mcp_router.models import MCPServer
from fastmcp import FastMCP


class TestServer(unittest.TestCase):
    """Test cases for the MCP server and router creation."""

    def test_create_mcp_config(self):
        """Test the creation of the MCP proxy configuration."""
        server1 = MCPServer(
            id="server01",
            name="TestServer1",
            github_url="http://test.com/repo1",
            runtime_type="docker",
            start_command="node start.js",
            env_variables=[{"key": "PORT", "value": "8080"}],
        )
        server2 = MCPServer(
            id="server02",
            name="TestServer2",
            github_url="http://test.com/repo2",
            runtime_type="uvx",
            start_command="uvx run my_app:app",
            env_variables=[],
        )

        config = create_mcp_config([server1, server2])
        self.assertIn("TestServer1", config["mcpServers"])
        self.assertIn("TestServer2", config["mcpServers"])

        server1_config = config["mcpServers"]["TestServer1"]
        self.assertEqual(server1_config["transport"], "stdio")
        self.assertIn("docker", server1_config["command"])
        self.assertIn("-e", server1_config["args"])
        self.assertIn("PORT=8080", server1_config["args"])
        self.assertIn("mcp-router/server-server01", server1_config["args"])
        self.assertIn("node", server1_config["args"])
        self.assertIn("start.js", server1_config["args"])

        server2_config = config["mcpServers"]["TestServer2"]
        self.assertIn("uvx", server2_config["args"])
        self.assertIn("stdio", server2_config["args"])

    def test_dynamic_server_manager_add_server(self):
        """Test adding a server with the MCPManager."""
        mock_router = MagicMock(spec=FastMCP)
        manager = MCPManager(router=mock_router)

        server_config = MCPServer(
            id="dyn_serv",
            name="DynamicServer",
            github_url="http://test.com/dynamic",
            runtime_type="npx",
            start_command="npx @my-co/dynamic-server",
            description="A dynamic server.",
        )

        with patch("mcp_router.server.create_mcp_config") as mock_create_config:
            with patch("mcp_router.server.store_server_tools"):
                mock_create_config.return_value = {
                    "mcpServers": {
                        "DynamicServer": {
                            "command": "docker",
                            "args": ["run", "mcp-router/server-dyn_serv", "npx", "...", "stdio"],
                            "transport": "stdio",
                        }
                    }
                }

                asyncio.run(manager.add_server(server_config))

            mock_router.mount.assert_called_once()
            args, kwargs = mock_router.mount.call_args
            self.assertIsInstance(args[0], FastMCP)  # The mounted proxy
            self.assertEqual(kwargs["prefix"], "dyn_serv")

            self.assertIn("dyn_serv", manager.mounted_servers)

    def test_dynamic_server_manager_remove_server(self):
        """Test removing a server with the MCPManager."""
        mock_router = MagicMock(spec=FastMCP)
        mock_router._tool_manager = MagicMock()
        mock_router._resource_manager = MagicMock()
        mock_router._prompt_manager = MagicMock()
        mock_router._cache = MagicMock()

        manager = MCPManager(router=mock_router)

        mock_mounted_proxy = MagicMock(spec=FastMCP)
        manager.mounted_servers["server_to_remove"] = mock_mounted_proxy

        mount_obj = MagicMock()
        mount_obj.server = mock_mounted_proxy
        
        mock_tool_list = MagicMock()
        mock_resource_list = MagicMock()
        mock_prompt_list = MagicMock()
        
        mock_tool_list.__iter__ = lambda self: iter([mount_obj])
        mock_resource_list.__iter__ = lambda self: iter([mount_obj])
        mock_prompt_list.__iter__ = lambda self: iter([mount_obj])
        
        mock_router._tool_manager._mounted_servers = mock_tool_list
        mock_router._resource_manager._mounted_servers = mock_resource_list
        mock_router._prompt_manager._mounted_servers = mock_prompt_list

        manager.remove_server("server_to_remove")

        self.assertNotIn("server_to_remove", manager.mounted_servers)

        mock_tool_list.remove.assert_called_with(mount_obj)
        mock_resource_list.remove.assert_called_with(mount_obj)
        mock_prompt_list.remove.assert_called_with(mount_obj)

        mock_router._cache.clear.assert_called_once()


if __name__ == "__main__":
    unittest.main() 