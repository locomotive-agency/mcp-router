"""Configuration export routes"""

import os
from flask import Blueprint, jsonify, Response
from flask_login import login_required

# Create blueprint
config_bp = Blueprint("config", __name__)


@config_bp.route("/config/claude-desktop")
@login_required
def claude_desktop_config() -> Response:
    """Generate Claude Desktop configuration

    Returns:
        JSON response with Claude Desktop configuration
    """
    config = {
        "mcpServers": {
            "mcp-router": {
                "command": "python",
                "args": ["-m", "mcp_router", "--transport", "stdio"],
            }
        }
    }

    # Return as downloadable JSON
    response = jsonify(config)
    response.headers["Content-Disposition"] = "attachment; filename=claude_desktop_config.json"
    return response


@config_bp.route("/config/local-inspector")
@login_required
def local_inspector_config() -> Response:
    """Generate a configuration file for the local MCP Inspector.

    Returns:
        JSON response with MCP Inspector configuration
    """
    config = {
        "mcpServers": {
            "mcp-router-dev": {
                "command": "python",
                "args": ["-m", "mcp_router", "--transport", "stdio"],
                "env": {"PYTHONPATH": os.getcwd()},
            }
        }
    }
    response = jsonify(config)
    response.headers["Content-Disposition"] = "attachment; filename=inspector_config.json"
    return response
