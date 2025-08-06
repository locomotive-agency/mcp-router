import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from starlette.applications import Starlette
import httpx

from mcp_anywhere.web.app import create_app
from mcp_anywhere.database import MCPServer

# PAUSED: Tests that create servers in database
pytestmark = pytest.mark.skip(reason="Paused: Tests create servers in database")


@pytest_asyncio.fixture
async def app():
    """Create app instance for testing."""
    return create_app()


@pytest_asyncio.fixture
async def sample_server():
    """Sample server for testing."""
    return MCPServer(
        id="test123",
        name="test-server",
        github_url="https://github.com/test/repo",
        description="Test server",
        runtime_type="npx",
        install_command="npm install -g test-package",
        start_command="npx test-package",
        env_variables=[],
        is_active=True
    )


@pytest.mark.asyncio
async def test_add_server_get_loads(app: Starlette):
    """Test that the add server form loads."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/servers/add")
    
    assert response.status_code == 200
    assert "Add New Server" in response.text
    assert "GitHub URL" in response.text


@pytest.mark.asyncio
async def test_add_server_post_valid_data(app: Starlette):
    """Test adding a server with valid data."""
    form_data = {
        "save": "Save Server",
        "name": "test-server-post",
        "github_url": "https://github.com/test/repo",
        "description": "Test server",
        "runtime_type": "npx",
        "install_command": "npm install -g test-package",
        "start_command": "npx test-package"
    }
    
    with patch('mcp_anywhere.web.routes.ContainerManager') as mock_container:
        mock_container.return_value.build_server_image.return_value = "test-image:latest"
        
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/servers/add", data=form_data)
    
    # Should redirect after successful save
    assert response.status_code == 302
    assert response.headers.get("location") == "/"


@pytest.mark.asyncio
async def test_add_server_post_invalid_data(app: Starlette):
    """Test adding a server with invalid data."""
    form_data = {
        "save": "Save Server",
        "name": "",  # Invalid: empty name
        "github_url": "not-a-github-url",  # Invalid URL
        "description": "Test server",
        "runtime_type": "npx",
        "install_command": "npm install -g test-package",
        "start_command": "npx test-package"
    }
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/servers/add", data=form_data)
    
    # Should return form with errors
    assert response.status_code == 200
    assert "Add New Server" in response.text


@pytest.mark.asyncio
async def test_add_server_duplicate_name(app: Starlette):
    """Test adding a server with a duplicate name."""
    form_data = {
        "save": "Save Server",
        "name": "duplicate-server",
        "github_url": "https://github.com/test/repo",
        "description": "Test server",
        "runtime_type": "npx",
        "install_command": "npm install -g test-package",
        "start_command": "npx test-package"
    }
    
    with patch('mcp_anywhere.web.routes.ContainerManager') as mock_container:
        mock_container.return_value.build_server_image.return_value = "test-image:latest"
        
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Add first server
            response = await client.post("/servers/add", data=form_data)
            assert response.status_code == 302
            
            # Try to add the same server again
            response = await client.post("/servers/add", data=form_data)
            assert response.status_code == 200
            assert "already exists" in response.text


@pytest.mark.asyncio
async def test_add_server_analyze_functionality(app: Starlette):
    """Test that the analyze button works with Claude analyzer."""
    form_data = {
        "analyze": "true",
        "github_url": "https://github.com/test/repo"
    }
    
    # Mock the Claude analyzer to return successful analysis
    mock_analysis = {
        "name": "analyzed-server",
        "description": "A test MCP server for data analysis",
        "runtime_type": "npx",
        "install_command": "npm install -g @test/mcp-server",
        "start_command": "npx @test/mcp-server"
    }
    
    with patch('mcp_anywhere.web.routes.AsyncClaudeAnalyzer') as mock_analyzer_class:
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze_repository.return_value = mock_analysis
        mock_analyzer_class.return_value = mock_analyzer
        
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/servers/add", data=form_data)
    
    # Should return form with analysis results
    assert response.status_code == 200
    assert "Add New Server" in response.text
    assert "Repository Analysis Complete!" in response.text
    assert "A test MCP server for data analysis" in response.text


@pytest.mark.asyncio
async def test_add_server_analyze_failure(app: Starlette):
    """Test analyze functionality when Claude analyzer fails."""
    form_data = {
        "analyze": "true",
        "github_url": "https://github.com/test/repo"
    }
    
    # Mock the Claude analyzer to raise an exception
    with patch('mcp_anywhere.web.routes.AsyncClaudeAnalyzer') as mock_analyzer_class:
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze_repository.side_effect = ConnectionError("API Error")
        mock_analyzer_class.return_value = mock_analyzer
        
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/servers/add", data=form_data)
    
    # Should return form with fallback analysis and warning
    assert response.status_code == 200
    assert "Add New Server" in response.text
    # Should show fallback message
    assert "Claude analysis unavailable" in response.text or "analysis failed" in response.text


@pytest.mark.asyncio
async def test_add_server_analyze_invalid_url(app: Starlette):
    """Test analyze functionality with invalid GitHub URL."""
    form_data = {
        "analyze": "true",
        "github_url": "not-a-github-url"
    }
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/servers/add", data=form_data)
    
    # Should return form with error
    assert response.status_code == 200
    assert "Add New Server" in response.text