"""MCP server control and proxy routes"""

import logging
from typing import Union
from flask import Blueprint, render_template, request, jsonify, Response
from flask_login import login_required
from flask_wtf.csrf import CSRFProtect
from mcp_router.server_manager import get_server_manager

logger = logging.getLogger(__name__)

# Create blueprint
mcp_bp = Blueprint("mcp", __name__)


# Helper to register CSRF exemptions after app creation
def register_csrf_exemptions(csrf: CSRFProtect) -> None:
    """Register CSRF exemptions for MCP routes

    Args:
        csrf: CSRFProtect instance to configure
    """
    # No CSRF exemptions needed - MCP routes are handled by ASGI layer
    pass


# Note: MCP requests are now handled directly by the mounted FastMCP app in the ASGI layer
# No proxy route needed since the MCP app is mounted at /mcp in the ASGI application


@mcp_bp.route("/mcp-control")
@login_required
def mcp_control() -> str:
    """MCP Server Control Panel

    Returns:
        Rendered MCP control template
    """
    return render_template("mcp_control.html")


@mcp_bp.route("/api/mcp/status", methods=["GET"])
@login_required
def get_mcp_status() -> Union[str, Response]:
    """Get current MCP server status

    Returns:
        HTML template for htmx requests or JSON for API requests
    """
    server_manager = get_server_manager()
    status = server_manager.get_status()

    # Return HTML for htmx requests
    if request.headers.get("HX-Request"):
        return render_template("partials/mcp_status.html", status=status)

    # Return JSON for API requests
    return jsonify(status)
