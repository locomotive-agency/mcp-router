import pytest
from unittest.mock import patch
from mcp_anywhere.container.manager import ContainerManager
from mcp_anywhere.database import MCPServer

# PAUSED: Tests that work with container manager and Docker operations  
pytestmark = pytest.mark.skip(reason="Paused: Tests work with Docker container manager")

@pytest.fixture
def manager():
    """Pytest fixture to provide a ContainerManager instance."""
    return ContainerManager(app=None)

def test_get_image_tag(manager: ContainerManager):
    """Test the generation of a Docker image tag."""
    server = MCPServer(id="server123")
    assert manager.get_image_tag(server) == "mcp-anywhere/server-server123"

def test_parse_start_command(manager: ContainerManager):
    """Test the parsing of start commands."""
    # Simple command
    server1 = MCPServer(runtime_type="docker", start_command="node index.js")
    assert manager._parse_start_command(server1) == ["node", "index.js"]

    # Command with quotes and extra space
    server2 = MCPServer(
        runtime_type="docker", start_command='uvx run --port 8000 "my_module:app"  '
    )
    assert manager._parse_start_command(server2) == [
        "uvx", "run", "--port", "8000", "my_module:app"
    ]

    # npx command should get 'stdio' appended
    server3 = MCPServer(
        runtime_type="npx", start_command="npx @my-scope/my-package --arg value"
    )
    assert manager._parse_start_command(server3) == [
        "npx", "@my-scope/my-package", "--arg", "value", "stdio"
    ]

def test_parse_install_command(manager: ContainerManager):
    """Test the parsing of install commands."""
    # npx package name
    server_npx = MCPServer(
        runtime_type="npx", install_command="@my-scope/my-package"
    )
    assert (
        manager._parse_install_command(server_npx)
        == "npm install -g --no-audit @my-scope/my-package"
    )

    # Full npx command
    server_npx_full = MCPServer(
        runtime_type="npx", install_command="npx @another/package"
    )
    assert (
        manager._parse_install_command(server_npx_full)
        == "npm install -g --no-audit @another/package"
    )

    # Python pip command
    server_uvx = MCPServer(
        runtime_type="uvx", install_command="pip install -r requirements.txt"
    )
    assert (
        manager._parse_install_command(server_uvx)
        == "pip install -r requirements.txt"
    )

@patch("mcp_anywhere.container.manager.DockerClient")
def test_check_docker_running_success(mock_docker_client):
    """Test the Docker health check succeeds."""
    mock_client_instance = mock_docker_client.from_env.return_value
    mock_client_instance.ping.return_value = True
    manager = ContainerManager()
    assert manager._check_docker_running() is True

@patch("mcp_anywhere.container.manager.DockerClient")
def test_check_docker_running_failure(mock_docker_client):
    """Test the Docker health check fails."""
    mock_client_instance = mock_docker_client.from_env.return_value
    mock_client_instance.ping.side_effect = Exception("Docker daemon not running")
    manager = ContainerManager()
    assert manager._check_docker_running() is False
