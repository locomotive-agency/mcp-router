"""
Test container management and GitHub integration.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from mcp_router.config.settings import Settings
from mcp_router.services.container_manager import (
    ContainerManager, 
    RuntimeType, 
    ContainerRuntimeDetector,
    RuntimeInfo
)
from mcp_router.services.github_service import GitHubService
from mcp_router.models.database import MCPServer


@pytest.fixture
def test_settings():
    """Create test settings."""
    return Settings(
        anthropic_api_key="test-key",
        secret_key="test-secret",
        enable_metrics=False,
        container_backend="docker"
    )


@pytest.fixture
def container_manager(test_settings):
    """Create container manager instance."""
    return ContainerManager(test_settings)


@pytest.fixture
def github_service(test_settings):
    """Create GitHub service instance."""
    return GitHubService(test_settings)


@pytest.fixture
def sample_mcp_server():
    """Create a sample MCP server for testing."""
    return MCPServer(
        id="test-server-1",
        name="test-mcp-server",
        display_name="Test MCP Server",
        description="A test MCP server",
        github_url="https://github.com/test/mcp-server",
        runtime_type="python",
        install_command="pip install -e .",
        start_command="python main.py",
        transport_type="stdio",
        transport_config={},
        capabilities={
            "tools": ["test_tool"],
            "resources": [],
            "prompts": []
        }
    )


class TestContainerRuntimeDetector:
    """Test container runtime detection."""
    
    def test_detect_python_project(self):
        """Test Python project detection."""
        detector = ContainerRuntimeDetector()
        
        python_files = [
            "requirements.txt",
            "main.py",
            "src/server.py",
            "pyproject.toml"
        ]
        
        # This is a sync version for testing
        runtime_info = asyncio.run(detector.detect_runtime(python_files))
        
        assert runtime_info.type == RuntimeType.PYTHON
        assert "pip install" in runtime_info.install_command
        assert runtime_info.base_image == "python:3.11-slim"
    
    def test_detect_nodejs_project(self):
        """Test Node.js project detection."""
        detector = ContainerRuntimeDetector()
        
        node_files = [
            "package.json",
            "package-lock.json",
            "src/index.js",
            "node_modules/test"
        ]
        
        runtime_info = asyncio.run(detector.detect_runtime(node_files))
        
        assert runtime_info.type == RuntimeType.NODEJS
        assert runtime_info.install_command == "npm install"
        assert runtime_info.base_image == "node:18-alpine"
    
    def test_detect_docker_project(self):
        """Test Docker project detection."""
        detector = ContainerRuntimeDetector()
        
        docker_files = [
            "Dockerfile",
            "docker-compose.yml",
            "src/app.py"
        ]
        
        runtime_info = asyncio.run(detector.detect_runtime(docker_files))
        
        assert runtime_info.type == RuntimeType.DOCKER
        assert "docker build" in runtime_info.install_command
    
    def test_extract_python_dependencies(self):
        """Test Python dependency extraction."""
        detector = ContainerRuntimeDetector()
        
        file_contents = {
            "requirements.txt": "requests==2.28.0\nnumpy>=1.20.0\npandas~=1.4.0"
        }
        
        deps = detector._extract_python_dependencies(["requirements.txt"], file_contents)
        
        assert "requests" in deps
        assert "numpy" in deps
        assert "pandas" in deps


class TestContainerManager:
    """Test container manager functionality."""
    
    @pytest.mark.asyncio
    async def test_detect_runtime(self, container_manager):
        """Test runtime detection through container manager."""
        python_files = ["requirements.txt", "main.py"]
        
        runtime_info = await container_manager.detect_runtime(python_files)
        
        assert isinstance(runtime_info, RuntimeInfo)
        assert runtime_info.type == RuntimeType.PYTHON
    
    @pytest.mark.asyncio
    async def test_create_session(self, container_manager, sample_mcp_server):
        """Test container session creation."""
        with patch.object(container_manager, '_prepare_sandbox_config') as mock_config:
            mock_config.return_value = {
                "lang": "python",
                "image": "python:3.11-slim"
            }
            
            # Mock the SandboxSession
            with patch('mcp_router.services.container_manager.SandboxSession'):
                session_id = await container_manager.create_session(sample_mcp_server)
                
                assert session_id is not None
                assert session_id.startswith("test-server-1_")
                assert session_id in container_manager.active_sessions


class TestGitHubService:
    """Test GitHub service functionality."""
    
    @pytest.mark.asyncio
    async def test_parse_github_url(self, github_service):
        """Test GitHub URL parsing."""
        test_cases = [
            ("https://github.com/owner/repo", ("owner", "repo")),
            ("https://github.com/owner/repo.git", ("owner", "repo")),
            ("https://github.com/owner/repo/", ("owner", "repo")),
        ]
        
        for url, expected in test_cases:
            owner, repo = await github_service.parse_github_url(url)
            assert (owner, repo) == expected
    
    @pytest.mark.asyncio
    async def test_parse_invalid_url(self, github_service):
        """Test parsing invalid URLs."""
        with pytest.raises(ValueError):
            await github_service.parse_github_url("https://gitlab.com/owner/repo")
        
        with pytest.raises(ValueError):
            await github_service.parse_github_url("https://github.com/invalid")
    
    @pytest.mark.asyncio
    async def test_generate_server_name(self, github_service):
        """Test server name generation."""
        test_cases = [
            ("my-awesome-mcp", "my-awesome-mcp"),
            ("My_Awesome_MCP", "my_awesome_mcp"),  # Underscores replace uppercase/special chars
            ("mcp@server!", "mcp-server"),
            ("---test---", "test"),
            ("", "mcp-server")
        ]
        
        for input_name, expected in test_cases:
            result = github_service._generate_server_name(input_name)
            assert result == expected
    
    @pytest.mark.asyncio
    async def test_generate_env_description(self, github_service):
        """Test environment variable description generation."""
        test_cases = [
            ("API_KEY", "API key for"),
            ("DATABASE_URL", "URL endpoint for"),
            ("SECRET_TOKEN", "Authentication token for"),  # The method prioritizes token over secret
            ("SERVER_PORT", "Port number for")
        ]
        
        for var_name, expected_start in test_cases:
            description = github_service._generate_env_description(var_name)
            assert description.startswith(expected_start)


@pytest.mark.asyncio
async def test_integration_workflow(container_manager, github_service, sample_mcp_server):
    """Test the complete integration workflow."""
    
    # 1. Test runtime detection
    repo_files = ["requirements.txt", "main.py", "src/server.py"]
    runtime_info = await container_manager.detect_runtime(repo_files)
    
    assert runtime_info.type == RuntimeType.PYTHON
    
    # 2. Test GitHub URL parsing
    owner, repo = await github_service.parse_github_url(sample_mcp_server.github_url)
    assert owner == "test"
    assert repo == "mcp-server"
    
    # 3. Test container session creation (mocked)
    with patch.object(container_manager, '_prepare_sandbox_config') as mock_config:
        mock_config.return_value = {"lang": "python", "image": "python:3.11-slim"}
        
        with patch('mcp_router.services.container_manager.SandboxSession'):
            session_id = await container_manager.create_session(sample_mcp_server)
            assert session_id is not None
    
    # 4. Clean up
    await github_service.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 