
import unittest
from unittest.mock import patch
from mcp_router.container_manager import ContainerManager
from mcp_router.models import MCPServer

class TestContainerManager(unittest.TestCase):
    """Test cases for the ContainerManager."""

    def setUp(self):
        """Set up the ContainerManager instance."""
        self.manager = ContainerManager(app=None)

    def test_get_image_tag(self):
        """Test the generation of a Docker image tag."""
        server = MCPServer(id="server123")
        self.assertEqual(
            self.manager.get_image_tag(server), "mcp-router/server-server123"
        )

    def test_parse_start_command(self):
        """Test the parsing of start commands."""
        # Simple command
        server1 = MCPServer(runtime_type="docker", start_command="node index.js")
        self.assertEqual(
            self.manager._parse_start_command(server1), ["node", "index.js"]
        )

        # Command with quotes and extra space
        server2 = MCPServer(
            runtime_type="docker", start_command='uvx run --port 8000 "my_module:app"  '
        )
        self.assertEqual(
            self.manager._parse_start_command(server2),
            ["uvx", "run", "--port", "8000", "my_module:app"],
        )

        # npx command should get 'stdio' appended
        server3 = MCPServer(
            runtime_type="npx", start_command="npx @my-scope/my-package --arg value"
        )
        self.assertEqual(
            self.manager._parse_start_command(server3),
            ["npx", "@my-scope/my-package", "--arg", "value", "stdio"],
        )

    def test_parse_install_command(self):
        """Test the parsing of install commands."""
        # npx package name
        server_npx = MCPServer(
            runtime_type="npx", install_command="@my-scope/my-package"
        )
        self.assertEqual(
            self.manager._parse_install_command(server_npx),
            "npm install -g --no-audit @my-scope/my-package",
        )

        # Full npx command
        server_npx_full = MCPServer(
            runtime_type="npx", install_command="npx @another/package"
        )
        self.assertEqual(
            self.manager._parse_install_command(server_npx_full),
            "npm install -g --no-audit @another/package",
        )

        # Python pip command - uv is installed separately now
        server_uvx = MCPServer(
            runtime_type="uvx", install_command="pip install -r requirements.txt"
        )
        self.assertEqual(
            self.manager._parse_install_command(server_uvx),
            "pip install -r requirements.txt",
        )

    @patch("mcp_router.container_manager.DockerClient")
    def test_check_docker_running(self, mock_docker_client):
        """Test the Docker health check."""
        # Mock a successful ping
        mock_client_instance = mock_docker_client.from_env.return_value
        mock_client_instance.ping.return_value = True
        manager = ContainerManager()
        self.assertTrue(manager._check_docker_running())

        # Mock a failed ping
        mock_client_instance.ping.side_effect = Exception("Docker daemon not running")
        self.assertFalse(manager._check_docker_running())


if __name__ == "__main__":
    unittest.main() 