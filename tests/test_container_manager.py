"""Tests for ContainerManager class"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from mcp_router.container_manager import ContainerManager
from mcp_router.models import MCPServer


@pytest.fixture
def mock_server():
    """Create a mock MCPServer instance"""
    server = Mock(spec=MCPServer)
    server.id = "test-server-id"
    server.name = "Test Server"
    server.runtime_type = "npx"
    server.start_command = "@test/mcp-server"
    server.env_variables = [
        {"key": "API_KEY", "value": "test-key"},
        {"key": "ENV_VAR", "value": "test-value"},
    ]
    return server


@pytest.fixture
def container_manager():
    """Create a ContainerManager instance for testing"""
    with patch("mcp_router.container_manager.DockerClient"):
        manager = ContainerManager()
        manager.docker_client = Mock()
        return manager


class TestContainerManager:
    """Test suite for ContainerManager"""

    def test_init(self):
        """Test ContainerManager initialization"""
        with patch("mcp_router.container_manager.DockerClient"):
            manager = ContainerManager()
            assert manager.docker_host is not None
            assert manager.python_image is not None
            assert manager.node_image is not None
            assert isinstance(manager._containers, dict)

    def test_get_env_vars(self, container_manager, mock_server):
        """Test environment variable extraction"""
        env_vars = container_manager._get_env_vars(mock_server)
        assert env_vars == {"API_KEY": "test-key", "ENV_VAR": "test-value"}

    def test_get_env_vars_empty(self, container_manager):
        """Test environment variable extraction with no env vars"""
        server = Mock(spec=MCPServer)
        server.env_variables = []
        env_vars = container_manager._get_env_vars(server)
        assert env_vars == {}

    @patch("mcp_router.container_manager.SandboxSession")
    def test_create_sandbox_session_npx(self, mock_sandbox, container_manager, mock_server):
        """Test creating sandbox session for npx runtime"""
        mock_server.runtime_type = "npx"

        container_manager._create_sandbox_session(mock_server)

        mock_sandbox.assert_called_once()
        call_args = mock_sandbox.call_args[1]
        assert call_args["lang"] == "javascript"
        assert call_args["backend"] == "docker"
        assert call_args["keep_template"] is True
        assert call_args["template_name"] == "mcp-router-node-template"
        assert call_args["default_timeout"] == 60.0
        assert "runtime_config" in call_args
        assert call_args["runtime_config"]["environment"] == {
            "API_KEY": "test-key",
            "ENV_VAR": "test-value",
        }

    @patch("mcp_router.container_manager.SandboxSession")
    def test_create_sandbox_session_uvx(self, mock_sandbox, container_manager, mock_server):
        """Test creating sandbox session for uvx runtime"""
        mock_server.runtime_type = "uvx"

        container_manager._create_sandbox_session(mock_server)

        mock_sandbox.assert_called_once()
        call_args = mock_sandbox.call_args[1]
        assert call_args["lang"] == "python"
        assert call_args["backend"] == "docker"
        assert call_args["keep_template"] is True
        assert call_args["template_name"] == "mcp-router-python-template"
        assert call_args["runtime_config"]["environment"] == {
            "API_KEY": "test-key",
            "ENV_VAR": "test-value",
        }

    @patch("mcp_router.container_manager.SandboxSession")
    def test_create_sandbox_session_custom(self, mock_sandbox, container_manager, mock_server):
        """Test creating sandbox session for custom runtime"""
        mock_server.runtime_type = "custom"
        mock_server.start_command = "custom-image:latest"

        container_manager._create_sandbox_session(mock_server)

        mock_sandbox.assert_called_once()
        call_args = mock_sandbox.call_args[1]
        assert call_args["lang"] == "python"  # Defaults to python
        assert call_args["image"] == "custom-image:latest"
        assert call_args["runtime_config"]["environment"] == {
            "API_KEY": "test-key",
            "ENV_VAR": "test-value",
        }

    @patch("mcp_router.container_manager.SandboxSession")
    def test_create_sandbox_session_no_template(
        self, mock_sandbox, container_manager, mock_server
    ):
        """Test creating sandbox session without template (for tests)"""
        mock_server.runtime_type = "npx"

        container_manager._create_sandbox_session(mock_server, use_template=False)

        mock_sandbox.assert_called_once()
        call_args = mock_sandbox.call_args[1]
        assert call_args["lang"] == "javascript"
        assert call_args["backend"] == "docker"

    @patch("mcp_router.container_manager.SandboxSession")
    def test_test_server_npx_success(self, mock_sandbox_class, container_manager, mock_server):
        """Test successful npx server test"""
        mock_server.runtime_type = "npx"

        # Mock the sandbox session
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.exit_code = 0
        mock_result.stdout = (
            'Version: 1.0.0\n{"status": "success", "version": "1.0.0", "tools": ["tool1", "tool2"]}'
        )
        mock_result.stderr = ""
        mock_session.run.return_value = mock_result
        mock_session.__enter__.return_value = mock_session
        mock_sandbox_class.return_value = mock_session

        result = container_manager.test_server(mock_server)

        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert result["version"] == "1.0.0"
        assert result["tools"] == ["tool1", "tool2"]
        mock_session.run.assert_called_once()

    @patch("mcp_router.container_manager.SandboxSession")
    def test_test_server_failure(self, mock_sandbox_class, container_manager, mock_server):
        """Test failed server test"""
        # Mock the sandbox session to raise an exception
        mock_sandbox_class.side_effect = Exception("Connection failed")

        result = container_manager.test_server(mock_server)

        assert result["status"] == "error"
        assert result["message"] == "Connection failed"

    @patch("mcp_router.container_manager.get_server_by_id")
    def test_pull_server_image_npx(self, mock_get_server, container_manager, mock_server):
        """Test pulling image for npx server"""
        mock_server.runtime_type = "npx"
        mock_get_server.return_value = mock_server

        result = container_manager.pull_server_image("test-server-id")

        assert result["status"] == "success"
        assert result["image"] == container_manager.node_image
        container_manager.docker_client.images.pull.assert_called_once_with(
            container_manager.node_image
        )

    @patch("mcp_router.container_manager.get_server_by_id")
    def test_pull_server_image_not_found(self, mock_get_server, container_manager):
        """Test pulling image for non-existent server"""
        mock_get_server.return_value = None

        result = container_manager.pull_server_image("non-existent-id")

        assert result["status"] == "error"
        assert "not found" in result["message"]

    @patch("mcp_router.container_manager.SandboxSession")
    def test_run_server_in_sandbox_success(
        self, mock_sandbox_class, container_manager, mock_server
    ):
        """Test successfully running server in sandbox"""
        # Mock the sandbox session
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.exit_code = 0
        mock_result.stdout = "Server started successfully"
        mock_result.stderr = ""
        mock_session.run.return_value = mock_result
        mock_session.__enter__.return_value = mock_session
        mock_sandbox_class.return_value = mock_session

        result = container_manager.run_server_in_sandbox(mock_server)

        assert result["success"] is True
        assert result["output"] == "Server started successfully"
        assert result["error"] is None
        assert result["exit_code"] == 0

    @patch("mcp_router.container_manager.SandboxSession")
    def test_initialize_templates(self, mock_sandbox, container_manager):
        """Test that initialize_templates creates templates for all runtime types"""
        # Mock the sandbox session
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)
        mock_sandbox.return_value = mock_session

        # Run initialization
        container_manager.initialize_templates()

        # Should create 2 sessions (npx and uvx)
        assert mock_sandbox.call_count == 2

        # Check first call (npx template)
        first_call = mock_sandbox.call_args_list[0][1]
        assert first_call["lang"] == "javascript"
        assert first_call["template_name"] == "mcp-router-node-template"
        assert first_call["keep_template"] is True

        # Check second call (uvx template)
        second_call = mock_sandbox.call_args_list[1][1]
        assert second_call["lang"] == "python"
        assert second_call["template_name"] == "mcp-router-python-template"
        assert second_call["keep_template"] is True

        # Check version commands were run
        assert mock_session.run.call_count == 2
        mock_session.run.assert_any_call("node --version", timeout=10.0)
        mock_session.run.assert_any_call("python --version", timeout=10.0)
