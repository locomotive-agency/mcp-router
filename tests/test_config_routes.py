"""
Test suite for Claude Desktop configuration routes.

Tests the generation and serving of configuration files for STDIO mode
integration with Claude Desktop.
"""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from mcp_anywhere.web.app import create_app


@asynccontextmanager
async def mock_lifespan(app):
    """Mock lifespan context manager."""
    app.state.mcp_manager = MagicMock()
    app.state.container_manager = MagicMock()
    app.state.get_async_session = MagicMock()
    yield


@pytest.fixture
def app_stdio():
    """Create app instance for STDIO mode."""
    with patch("mcp_anywhere.web.app.create_lifespan", return_value=mock_lifespan):
        app = create_app(transport_mode="stdio")
        return app


@pytest.fixture
def app_http():
    """Create app instance for HTTP mode."""
    with patch("mcp_anywhere.web.app.create_lifespan", return_value=mock_lifespan):
        app = create_app(transport_mode="http")
        return app


def test_config_download_stdio_mode(app_stdio):
    """
    Test that config download works in STDIO mode.
    """
    with TestClient(app_stdio) as client:
        response = client.get("/config/download")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "content-disposition" in response.headers
        assert "claude_desktop_config.json" in response.headers["content-disposition"]

        # Parse the JSON response
        config = response.json()

        # Check required fields
        assert "mcpServers" in config
        assert "mcp-anywhere" in config["mcpServers"]

        # Check the server configuration
        server_config = config["mcpServers"]["mcp-anywhere"]
        assert "command" in server_config
        assert "args" in server_config

        # Should use python command for STDIO
        assert "python" in server_config["command"] or "python3" in server_config["command"]
        assert "mcp_anywhere" in " ".join(server_config["args"])
        assert "serve" in server_config["args"]
        assert "stdio" in server_config["args"]


def test_config_view_stdio_mode(app_stdio):
    """
    Test that config view endpoint returns proper JSON in STDIO mode.
    """
    with TestClient(app_stdio) as client:
        response = client.get("/config/view")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        config = response.json()
        assert "mcpServers" in config
        assert "mcp-anywhere" in config["mcpServers"]


def test_config_instructions_stdio_mode(app_stdio):
    """
    Test that setup instructions are provided in STDIO mode.
    """
    with TestClient(app_stdio) as client:
        response = client.get("/config/instructions")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        html = response.text

        # Check for key instruction elements
        assert "Claude Desktop" in html
        assert "configuration" in html.lower()
        assert "stdio" in html.lower() or "STDIO" in html


def test_config_routes_not_available_http_mode(app_http):
    """
    Test that config routes return appropriate message in HTTP mode.
    """
    with TestClient(app_http) as client:
        response = client.get("/config/download")

        # Should either redirect or return an error message
        assert response.status_code in [200, 400, 404]

        if response.status_code == 200:
            # If it returns 200, it should indicate HTTP mode doesn't need this
            if response.headers.get("content-type") == "application/json":
                config = response.json()
                # Could have different config for HTTP mode or error message
                assert "mcpServers" in config or "error" in config


def test_config_json_structure():
    """
    Test that the generated config JSON has the correct structure for Claude Desktop.
    """
    from mcp_anywhere.web.config_routes import generate_claude_config

    config = generate_claude_config()

    # Validate structure
    assert isinstance(config, dict)
    assert "mcpServers" in config
    assert isinstance(config["mcpServers"], dict)

    # Check MCP Anywhere server entry
    assert "mcp-anywhere" in config["mcpServers"]
    server = config["mcpServers"]["mcp-anywhere"]

    assert "command" in server
    assert "args" in server
    assert isinstance(server["args"], list)

    # Optional fields that might be present
    optional_fields = ["env", "cwd"]
    for field in optional_fields:
        if field in server:
            assert isinstance(server.get(field), dict) or isinstance(server.get(field), str)
