"""Tests for the Flask web application UI and routes."""

import pytest
from mcp_router.models import db, MCPServer

# --- Test Data ---

ANALYZER_SUCCESS_DATA = {
    'name': 'analyzed-server',
    'github_url': 'https://github.com/analyzed/repo',
    'description': 'An analyzed description.',
    'runtime_type': 'npx',
    'install_command': 'npm install',
    'start_command': 'npx start-server',
    'env_variables': [{'key': 'API_KEY', 'description': 'Required key', 'required': True}]
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
        'mcp_router.app.ClaudeAnalyzer.analyze_repository', 
        return_value=ANALYZER_SUCCESS_DATA
    )
    
    response = client.post("/servers/add", data={
        "github_url": "https://github.com/any/repo",
        "analyze": "true"
    })
    
    assert response.status_code == 200
    assert b"Step 2: Configure Server" in response.data
    assert b'value="analyzed-server"' in response.data
    assert b'value="npm install"' in response.data

def test_add_server_save_flow(client, mocker):
    """Test the full flow of adding and saving a server."""
    # Mock the analyzer for the first step
    mocker.patch(
        'mcp_router.app.ClaudeAnalyzer.analyze_repository', 
        return_value=ANALYZER_SUCCESS_DATA
    )
    
    # Step 1: Analyze
    client.post("/servers/add", data={
        "github_url": "https://github.com/any/repo",
        "analyze": "true"
    })
    
    # Step 2: Save
    response = client.post("/servers/add", data={
        **ANALYZER_SUCCESS_DATA,
        "save": "true"
    }, follow_redirects=True)
    
    assert response.status_code == 200
    # Check that the server name is on the resulting page, which is more robust
    assert b'analyzed-server' in response.data
    
    # Verify it's in the database
    with client.application.app_context():
        server = MCPServer.query.filter_by(name="analyzed-server").first()
        assert server is not None
        assert server.install_command == "npm install"

def test_server_detail_page(client):
    """Test that the server detail page loads."""
    with client.application.app_context():
        server = MCPServer(name="detail-test", github_url="http://a.b", runtime_type="docker", start_command="c")
        db.session.add(server)
        db.session.commit()
        server_id = server.id
    
    response = client.get(f"/servers/{server_id}")
    assert response.status_code == 200
    assert b"detail-test" in response.data
    assert b"Live Logs" in response.data

def test_delete_server(client):
    """Test deleting a server."""
    with client.application.app_context():
        server = MCPServer(name="delete-me", github_url="http://a.b", runtime_type="docker", start_command="c")
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
    mock_test = mocker.patch(
        'mcp_router.app.ContainerManager.test_server_spawn',
        return_value={"status": "success", "message": "Container spawned", "details": "ID: 123"}
    )
    
    with client.application.app_context():
        server = MCPServer(name="htmx-test", github_url="http://a.b", runtime_type="docker", start_command="c")
        db.session.add(server)
        db.session.commit()
        server_id = server.id
        
    response = client.post(f"/api/servers/{server_id}/test")
    
    assert response.status_code == 200
    assert b"Container spawned" in response.data
    mock_test.assert_called_once_with(server_id) 