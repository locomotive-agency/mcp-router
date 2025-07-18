"""Test source building functionality"""

import pytest
from unittest.mock import Mock, MagicMock
from mcp_router.models import MCPServer, db
from mcp_router.container_manager import ContainerManager
from mcp_router.claude_analyzer import ClaudeAnalyzer


@pytest.fixture
def mock_server_with_source_building():
    """Create a mock MCPServer instance with source building enabled"""
    server = Mock(spec=MCPServer)
    server.id = "test-server-id"
    server.name = "Test Source Server"
    server.runtime_type = "npx"
    server.start_command = "npm start"
    server.build_from_source = True
    server.build_command = "npm run build"
    server.install_command = "npm install"
    server.github_url = "https://github.com/test/repo"
    server.env_variables = [
        {"key": "API_KEY", "value": "test-key"},
    ]
    return server


@pytest.fixture
def mock_server_without_source_building():
    """Create a mock MCPServer instance without source building"""
    server = Mock(spec=MCPServer)
    server.id = "test-server-id"
    server.name = "Test Registry Server"
    server.runtime_type = "npx"
    server.start_command = "@test/mcp-server"
    server.build_from_source = False
    server.build_command = ""
    server.install_command = ""
    server.github_url = "https://github.com/test/repo"
    server.env_variables = []
    return server


class TestSourceBuilding:
    """Test suite for source building functionality"""

    def test_mcp_server_model_with_source_building(self, app):
        """Test MCPServer model with source building fields"""
        with app.app_context():
            server = MCPServer(
                name='test-source-server',
                github_url='https://github.com/test/mcp-server',
                description='Test server built from source',
                runtime_type='npx',
                start_command='npm start',
                build_from_source=True,
                build_command='npm run build',
                install_command='npm install'
            )
            
            db.session.add(server)
            db.session.commit()
            
            # Verify the server was created correctly
            retrieved = MCPServer.query.filter_by(name='test-source-server').first()
            assert retrieved is not None
            assert retrieved.build_from_source is True
            assert retrieved.build_command == 'npm run build'
            
            # Test to_dict method
            server_dict = retrieved.to_dict()
            assert 'build_from_source' in server_dict
            assert 'build_command' in server_dict
            assert server_dict['build_from_source'] is True
            assert server_dict['build_command'] == 'npm run build'

    def test_claude_analyzer_parsing_with_source_building(self):
        """Test ClaudeAnalyzer parsing with source building fields"""
        analyzer = ClaudeAnalyzer.__new__(ClaudeAnalyzer)  # Create without __init__
        
        # Test with source building response
        mock_response = '''
RUNTIME: npx
INSTALL: npm install
START: npm start
BUILD_FROM_SOURCE: true
BUILD_COMMAND: npm run build
NAME: test-mcp-server
DESCRIPTION: A test MCP server requiring source building
ENV_VARS:
- KEY: API_KEY, DESC: API key for service, REQUIRED: true
'''
        
        result = analyzer._parse_claude_response(mock_response)
        assert result['build_from_source'] is True
        assert result['build_command'] == 'npm run build'
        assert result['runtime_type'] == 'npx'
        assert result['install_command'] == 'npm install'

    def test_claude_analyzer_parsing_without_source_building(self):
        """Test ClaudeAnalyzer parsing without source building"""
        analyzer = ClaudeAnalyzer.__new__(ClaudeAnalyzer)  # Create without __init__
        
        # Test with non-source building response
        mock_response = '''
RUNTIME: npx
INSTALL: none
START: @test/mcp-server
BUILD_FROM_SOURCE: false
BUILD_COMMAND: none
NAME: test-registry-server
DESCRIPTION: A test MCP server from registry
ENV_VARS:
'''
        
        result = analyzer._parse_claude_response(mock_response)
        assert result['build_from_source'] is False
        assert result['build_command'] == ''
        assert result['runtime_type'] == 'npx'
        assert result['start_command'] == '@test/mcp-server'

    def test_container_manager_source_building_success(self, mock_server_with_source_building):
        """Test ContainerManager with successful source building"""
        container_manager = ContainerManager.__new__(ContainerManager)
        container_manager.docker_client = Mock()
        container_manager.docker_host = "unix:///var/run/docker.sock"
        container_manager.python_image = "python:3.11-slim"
        container_manager.node_image = "node:20-slim"
        container_manager._containers = {}
        
        # Create mock sandbox
        mock_sandbox = Mock()
        mock_clone_result = Mock()
        mock_clone_result.exit_code = 0
        mock_clone_result.stdout = "Cloning into '/tmp/source'..."
        mock_clone_result.stderr = ""
        
        mock_build_result = Mock()
        mock_build_result.exit_code = 0
        mock_build_result.stdout = "Build completed successfully"
        mock_build_result.stderr = ""
        
        mock_install_result = Mock()
        mock_install_result.exit_code = 0
        mock_install_result.stdout = "Dependencies installed"
        mock_install_result.stderr = ""
        
        def mock_run(cmd, timeout=None):
            if "git clone" in cmd:
                return mock_clone_result
            elif "npm run build" in cmd:
                return mock_build_result
            elif "npm install" in cmd:
                return mock_install_result
            else:
                result = Mock()
                result.exit_code = 0
                result.stdout = "Command executed"
                result.stderr = ""
                return result
        
        mock_sandbox.run = mock_run
        
        # Test successful build
        result = container_manager._clone_and_build_from_source(mock_server_with_source_building, mock_sandbox)
        assert result["success"] is True
        assert result["message"] == "Source built successfully"

    def test_container_manager_source_building_failure(self, mock_server_with_source_building):
        """Test ContainerManager with failed source building"""
        container_manager = ContainerManager.__new__(ContainerManager)
        container_manager.docker_client = Mock()
        container_manager.docker_host = "unix:///var/run/docker.sock"
        container_manager.python_image = "python:3.11-slim"
        container_manager.node_image = "node:20-slim"
        container_manager._containers = {}
        
        # Create mock sandbox
        mock_sandbox = Mock()
        mock_clone_result = Mock()
        mock_clone_result.exit_code = 1
        mock_clone_result.stdout = ""
        mock_clone_result.stderr = "Repository not found"
        
        def mock_run(cmd, timeout=None):
            if "git clone" in cmd:
                return mock_clone_result
            else:
                result = Mock()
                result.exit_code = 0
                result.stdout = "Command executed"
                result.stderr = ""
                return result
        
        mock_sandbox.run = mock_run
        
        # Test failed build
        result = container_manager._clone_and_build_from_source(mock_server_with_source_building, mock_sandbox)
        assert result["success"] is False
        assert "Failed to clone repository" in result["error"]

    def test_container_manager_backwards_compatibility(self, mock_server_without_source_building):
        """Test that ContainerManager still works with non-source building servers"""
        container_manager = ContainerManager.__new__(ContainerManager)
        container_manager.docker_client = Mock()
        container_manager.docker_host = "unix:///var/run/docker.sock"
        container_manager.python_image = "python:3.11-slim"
        container_manager.node_image = "node:20-slim"
        container_manager._containers = {}
        
        # Create mock sandbox session
        mock_sandbox = Mock()
        mock_sandbox_session = Mock()
        mock_sandbox_session.__enter__ = Mock(return_value=mock_sandbox)
        mock_sandbox_session.__exit__ = Mock(return_value=None)
        
        container_manager._create_sandbox_session = Mock(return_value=mock_sandbox_session)
        
        # Mock the run result for the server start
        mock_result = Mock()
        mock_result.exit_code = 0
        mock_result.stdout = "Server started from registry"
        mock_result.stderr = ""
        
        def mock_run(cmd, timeout=None):
            if "npx -y @test/mcp-server" in cmd:
                return mock_result
            else:
                result = Mock()
                result.exit_code = 0
                result.stdout = "Command executed"
                result.stderr = ""
                return result
        
        mock_sandbox.run = mock_run
        
        # Test running server without source building
        result = container_manager.run_server_in_sandbox(mock_server_without_source_building)
        assert result["success"] is True
        assert result["output"] == "Server started from registry"