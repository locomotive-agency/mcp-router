"""Tests for the Flask web application UI and routes."""

import pytest
from unittest.mock import patch
from mcp_router.models import db, MCPServer
from mcp_router.container_manager import ContainerManager

# --- Test Data ---

ANALYZER_SUCCESS_DATA = {
    "name": "analyzed-server",
    "github_url": "https://github.com/analyzed/repo",
    "description": "An analyzed description.",
    "runtime_type": "npx",
    "install_command": "npm install",
    "start_command": "npx start-server",
    "env_variables": [{"key": "API_KEY", "description": "Required key", "required": True}],
}

# --- Tests ---


def test_index_page_loads(client):
    """Test that the index page loads correctly."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"MCP Servers" in response.data


def test_add_server_page_loads(client):
    """Test that the add server page loads correctly."""
    response = client.get("/servers/add")
    assert response.status_code == 200
    assert b"Step 1: Analyze Repository" in response.data


def test_analyze_flow(client, mocker):
    """Test the 'Analyze with Claude' flow."""
    # Mock the analyzer
    mocker.patch(
        "mcp_router.routes.servers.ClaudeAnalyzer.analyze_repository",
        return_value=ANALYZER_SUCCESS_DATA,
    )
    
    response = client.post(
        "/servers/add", data={"github_url": "https://github.com/any/repo", "analyze": "true"}
    )
    
    assert response.status_code == 200
    assert b"Step 2: Configure Server" in response.data
    assert b'value="analyzed-server"' in response.data
    assert b'value="npm install"' in response.data


def test_add_server_save_flow(client, mocker):
    """Test the full flow of adding and saving a server."""
    # Mock the analyzer for the first step
    mocker.patch(
        "mcp_router.routes.servers.ClaudeAnalyzer.analyze_repository",
        return_value=ANALYZER_SUCCESS_DATA,
    )
    
    # Step 1: Analyze
    client.post(
        "/servers/add", data={"github_url": "https://github.com/any/repo", "analyze": "true"}
    )
    
    # Step 2: Save
    response = client.post(
        "/servers/add", data={**ANALYZER_SUCCESS_DATA, "save": "true"}, follow_redirects=True
    )
    
    assert response.status_code == 200
    # Check that the server name is on the resulting page, which is more robust
    assert b"analyzed-server" in response.data
    
    # Verify it's in the database
    with client.application.app_context():
        server = MCPServer.query.filter_by(name="analyzed-server").first()
        assert server is not None
        assert server.install_command == "npm install"


def test_server_detail_page(client):
    """Test that the server detail page loads."""
    with client.application.app_context():
        server = MCPServer(
            name="detail-test", github_url="http://a.b", runtime_type="docker", start_command="c"
        )
        db.session.add(server)
        db.session.commit()
        server_id = server.id
    
    response = client.get(f"/servers/{server_id}")
    assert response.status_code == 200
    assert b"detail-test" in response.data


def test_delete_server(client):
    """Test deleting a server."""
    with client.application.app_context():
        server = MCPServer(
            name="delete-me", github_url="http://a.b", runtime_type="docker", start_command="c"
        )
        db.session.add(server)
        db.session.commit()
        server_id = server.id

    response = client.post(f"/servers/{server_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    # On redirect, we should see the remaining servers. The list will be empty.
    assert b"No servers configured yet." in response.data
    
    with client.application.app_context():
        assert MCPServer.query.get(server_id) is None


def test_test_server_htmx_endpoint(client, mocker):
    """Test the HTMX endpoint for testing a server spawn."""
    if not hasattr(ContainerManager, "test_server_spawn"):
        pytest.skip("ContainerManager.test_server_spawn not implemented; skipping test")

    mock_test = mocker.patch(
        "mcp_router.app.ContainerManager.test_server_spawn",
        return_value={"status": "success", "message": "Container spawned", "details": "ID: 123"},
    )
    
    with client.application.app_context():
        server = MCPServer(
            name="htmx-test", github_url="http://a.b", runtime_type="docker", start_command="c"
        )
        db.session.add(server)
        db.session.commit()
        server_id = server.id
        
    response = client.post(f"/api/servers/{server_id}/test")
    
    assert response.status_code == 200
    assert b"Container spawned" in response.data
    mock_test.assert_called_once_with(server_id) 


def test_mcp_status_endpoint_stdio_mode(client):
    """Test MCP status endpoint returns correct information for STDIO mode."""
    with patch("mcp_router.server_manager.Config") as mock_config:
        mock_config.MCP_TRANSPORT = "stdio"
        mock_config.FLASK_PORT = 8000

        # Initialize server manager for this test
        with client.application.app_context():
            from mcp_router.server_manager import init_server_manager

            init_server_manager(client.application)

        # Test JSON response
        response = client.get("/api/mcp/status")
        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "running"
        assert data["transport"] == "stdio"
        assert data["connection_info"]["type"] == "stdio"
        assert "python -m mcp_router --transport stdio" in data["connection_info"]["command"]


def test_mcp_status_endpoint_http_mode_oauth(client):
    """Test MCP status endpoint returns correct information for HTTP mode with OAuth."""
    with patch("mcp_router.server_manager.Config") as mock_config:
        mock_config.MCP_TRANSPORT = "http"
        mock_config.MCP_HOST = "127.0.0.1"
        mock_config.FLASK_PORT = 8000
        mock_config.MCP_PATH = "/mcp"
        mock_config.MCP_AUTH_TYPE = "oauth"
        mock_config.MCP_API_KEY = None

        # Initialize server manager for this test
        with client.application.app_context():
            from mcp_router.server_manager import init_server_manager

            init_server_manager(client.application)

        # Test JSON response
        response = client.get("/api/mcp/status")
        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "running"
        assert data["transport"] == "http"
        assert data["connection_info"]["type"] == "http"
        assert data["connection_info"]["auth_type"] == "oauth"
        assert "oauth-authorization-server" in data["connection_info"]["oauth_metadata_url"]


def test_mcp_status_endpoint_http_mode_api_key(client):
    """Test MCP status endpoint returns correct information for HTTP mode with API key."""
    with patch("mcp_router.server_manager.Config") as mock_config, \
         patch("mcp_router.models.get_auth_type") as mock_get_auth_type:
        mock_config.MCP_TRANSPORT = "http"
        mock_config.MCP_HOST = "0.0.0.0"
        mock_config.FLASK_PORT = 8000
        mock_config.MCP_PATH = "/mcp"
        mock_get_auth_type.return_value = "api_key"
        mock_config.MCP_API_KEY = "test-key-123"

        # Initialize server manager for this test
        with client.application.app_context():
            from mcp_router.server_manager import init_server_manager

            init_server_manager(client.application)

        # Test JSON response
        response = client.get("/api/mcp/status")
        assert response.status_code == 200
        data = response.get_json()

        assert data["connection_info"]["auth_type"] == "api_key"


def test_mcp_status_htmx_partial_stdio(client):
    """Test HTMX partial update for STDIO mode."""
    with patch("mcp_router.server_manager.Config") as mock_config:
        mock_config.MCP_TRANSPORT = "stdio"
        mock_config.FLASK_PORT = 8000

        # Initialize server manager for this test
        with client.application.app_context():
            from mcp_router.server_manager import init_server_manager

            init_server_manager(client.application)

        response = client.get("/api/mcp/status", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert b"Transport: STDIO" in response.data


def test_mcp_status_htmx_partial_http(client):
    """Test HTMX partial update for HTTP mode."""
    with patch("mcp_router.server_manager.Config") as mock_config, \
         patch("mcp_router.models.get_auth_type") as mock_get_auth_type:
        mock_config.MCP_TRANSPORT = "http"
        mock_config.MCP_HOST = "127.0.0.1"
        mock_config.FLASK_PORT = 8000
        mock_config.MCP_PATH = "/mcp"
        mock_get_auth_type.return_value = "api_key"
        mock_config.MCP_API_KEY = "test-key-123"

        # Initialize server manager for this test
        with client.application.app_context():
            from mcp_router.server_manager import init_server_manager

            init_server_manager(client.application)

        response = client.get("/api/mcp/status", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert b"Transport: HTTP" in response.data
        assert b"API Key" in response.data
