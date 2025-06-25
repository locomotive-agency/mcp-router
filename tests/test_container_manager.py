"""Tests for the ContainerManager."""

import pytest
from mcp_router.container_manager import ContainerManager
from mcp_router.models import MCPServer, db

# --- Mocks and Test Data ---

@pytest.fixture
def mock_sandbox_session(mocker):
    """Fixture to mock the SandboxSession."""
    # Create the mock instance that will be returned when SandboxSession is called
    mock_instance = mocker.MagicMock()
    
    # Configure the context manager behavior
    mock_instance.__enter__.return_value = mock_instance
    mock_instance.__exit__.return_value = None
    
    # Set up default return values for execute_command
    mock_instance.execute_command.return_value = mocker.MagicMock(
        exit_code=0,
        stdout="Success",
        stderr=""
    )
    
    # Patch the SandboxSession class to return our mock instance
    mock_class = mocker.patch(
        'mcp_router.container_manager.SandboxSession',
        return_value=mock_instance
    )
    
    # Return both the class and instance for flexibility in tests
    mock_class.instance = mock_instance
    return mock_class

@pytest.fixture
def sample_server():
    """Fixture to provide a sample server object."""
    return MCPServer(
        id="test-server-id",
        name="test-server",
        runtime_type="npx",
        install_command="npm install",
        start_command="npm start",
        env_variables=[
            {"key": "API_KEY", "value": "123"},
            {"key": "UNUSED_KEY", "value": ""}
        ]
    )

# --- Tests ---

def test_get_env_vars(sample_server):
    """Test the helper method for extracting environment variables."""
    manager = ContainerManager()
    env_vars = manager._get_env_vars(sample_server)
    
    assert "API_KEY" in env_vars
    assert env_vars["API_KEY"] == "123"
    assert "UNUSED_KEY" not in env_vars

@pytest.mark.asyncio
async def test_execute_server_tool_npx(mock_sandbox_session, sample_server, mocker):
    """Test executing a tool for an npx server."""
    manager = ContainerManager()
    
    # Mock the database query function
    mocker.patch('mcp_router.container_manager.get_server_by_id', return_value=sample_server)
    
    await manager.execute_server_tool("test-server-id", {"param": "value"})
    
    # Verify SandboxSession was called correctly
    mock_sandbox_session.assert_called_once()
    call_args = mock_sandbox_session.call_args[1]
    
    assert call_args['lang'] == 'javascript'
    assert call_args['runtime'] == 'node'
    assert call_args['env_vars']['API_KEY'] == '123'
    
    # Verify commands were executed
    session_instance = mock_sandbox_session.instance
    assert session_instance.__enter__.called
    session_instance.execute_command.assert_any_call("npm install")
    session_instance.execute_command.assert_any_call("npm start --param 'value'")

@pytest.mark.asyncio
async def test_execute_with_install_failure(mock_sandbox_session, sample_server, mocker):
    """Test that execution stops if the install command fails."""
    # Get the mock instance
    session_instance = mock_sandbox_session.instance
    
    # Configure mock to simulate install failure
    session_instance.execute_command.return_value = mocker.MagicMock(
        exit_code=1,
        stdout="",
        stderr="Install failed"
    )
    
    manager = ContainerManager()
    
    # Mock the database query function
    mocker.patch('mcp_router.container_manager.get_server_by_id', return_value=sample_server)
    
    result = await manager.execute_server_tool("test-server-id", {})
    
    assert result["status"] == "error"
    assert result["message"] == "Installation command failed"
    assert "Install failed" in result["details"]
    
    # Ensure start command was NOT called
    session_instance.execute_command.assert_called_once_with("npm install") 