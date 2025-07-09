"""MCP server control and proxy routes"""

import logging
from typing import Union, Tuple
from flask import Blueprint, render_template, request, jsonify, Response, stream_with_context
from flask_login import login_required
from flask_wtf.csrf import CSRFProtect
import httpx
from mcp_router.mcp_oauth import verify_token
from mcp_router.server_manager import get_server_manager

logger = logging.getLogger(__name__)

# Create blueprint
mcp_bp = Blueprint("mcp", __name__)


# We'll need to get server_manager from the app context
# This function is now defined in server_manager.py


# Helper to register CSRF exemptions after app creation
def register_csrf_exemptions(csrf: CSRFProtect) -> None:
    """Register CSRF exemptions for MCP routes

    Args:
        csrf: CSRFProtect instance to configure
    """
    # Exempt the proxy route from CSRF
    csrf.exempt(proxy_mcp_request)


@mcp_bp.route(
    "/mcp/", defaults={"subpath": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
)
@mcp_bp.route("/mcp/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def proxy_mcp_request(subpath: str) -> Union[Response, Tuple[Response, int]]:
    """
    Proxy MCP requests to either ASGI-mounted FastMCP app or external MCP server.
    This allows us to serve MCP through the main Flask app port.

    Args:
        subpath: The path after /mcp/ to proxy

    Returns:
        Proxied response from the MCP server
    """
    server_manager = get_server_manager()

    # Get the current MCP server status
    status = server_manager.get_status()

    # Check if server is running and is HTTP transport
    if not status or status.get("status") != "running" or status.get("transport") != "http":
        return jsonify({"error": "MCP server is not running in HTTP mode"}), 503

    # Get the internal URL for the MCP server
    connection_info = status.get("connection_info", {})
    internal_url = connection_info.get("internal_url")
    if not internal_url:
        return jsonify({"error": "MCP server URL not found"}), 503

    # Check authentication
    auth_type = connection_info.get("auth_type", "api_key")

    if auth_type == "oauth":
        # Validate OAuth token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return (
                jsonify(
                    {
                        "error": "Authorization required",
                        "error_description": "Bearer token required",
                    }
                ),
                401,
            )

        token = auth_header[7:]
        payload = verify_token(token)
        if not payload:
            return (
                jsonify(
                    {"error": "Invalid token", "error_description": "Token is invalid or expired"}
                ),
                401,
            )

        # Token is valid, continue with request
        logger.info(f"OAuth request validated for user: {payload.get('sub')}")

    # Construct the full URL with the subpath
    target_url = f"{internal_url.rstrip('/')}/{subpath}"

    # Forward headers, filtering out some that shouldn't be forwarded
    headers_to_skip = {
        "host",
        "content-length",
        "connection",
        "upgrade",
        "x-forwarded-for",
        "x-real-ip",
        "authorization",
        "content-encoding",
    }
    headers = {k: v for k, v in request.headers.items() if k.lower() not in headers_to_skip}
    logger.info(f"Forwarding headers to internal MCP server: {headers}")

    # Add/update the authorization header if we have an API key (not OAuth)
    if auth_type == "api_key":
        api_key = connection_info.get("api_key")
        if api_key and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {api_key}"

    try:
        # For all requests, we will use a streaming connection.
        with httpx.stream(
            request.method,
            target_url,
            headers=headers,
            content=request.get_data(),
            timeout=30.0,
        ) as response:
            excluded_headers = [
                "content-encoding",
                "content-length",
                "transfer-encoding",
                "connection",
            ]
            headers = {
                k: v for k, v in response.headers.items() if k.lower() not in excluded_headers
            }
            return Response(stream_with_context(response.iter_bytes()), response.status_code, headers)

    except httpx.TimeoutException:
        return jsonify({"error": "Request to MCP server timed out"}), 504
    except httpx.ConnectError as e:
        logger.error(f"Error connecting to MCP server: {e}")
        return jsonify({"error": f"Could not connect to MCP server at {internal_url}"}), 502
    except Exception as e:
        logger.error(f"Error proxying MCP request: {e}", exc_info=True)
        return jsonify({"error": "Failed to proxy request to MCP server"}), 502


@mcp_bp.route("/mcp-control")
@login_required
def mcp_control() -> str:
    """MCP Server Control Panel

    Returns:
        Rendered MCP control template
    """
    return render_template("mcp_control.html")


@mcp_bp.route("/api/mcp/start", methods=["POST"])
@login_required
def start_mcp_server() -> Union[Response, Tuple[Response, int]]:
    """Start the MCP server with specified transport

    Returns:
        JSON response with status and connection info
    """
    server_manager = get_server_manager()

    data = request.get_json() or {}
    transport = data.get("transport", "stdio")

    # Validate transport
    if transport not in ["stdio", "http"]:
        return (
            jsonify({"status": "error", "message": "Invalid transport. Must be stdio or http"}),
            400,
        )

    # Set transport-specific parameters
    kwargs = {}
    if transport == "http":
        # For HTTP, we no longer need host/port/path from the client.
        # We use standard defaults for the internal server.
        kwargs["host"] = "127.0.0.1"
        kwargs["port"] = 8001
        kwargs["path"] = "/mcp"

        # Check authentication mode
        auth_mode = data.get("auth_mode", "api_key")
        if auth_mode == "oauth":
            kwargs["enable_oauth"] = True
        else:
            kwargs["api_key"] = data.get("api_key")

    result = server_manager.start_server(transport, **kwargs)

    if result["status"] == "success":
        return jsonify(result)
    else:
        return jsonify(result), 500


@mcp_bp.route("/api/mcp/stop", methods=["POST"])
@login_required
def stop_mcp_server() -> Union[Response, Tuple[Response, int]]:
    """Stop the running MCP server

    Returns:
        JSON response with status
    """
    server_manager = get_server_manager()
    result = server_manager.stop_server()

    if result["status"] == "success":
        return jsonify(result)
    else:
        return jsonify(result), 500


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


@mcp_bp.route("/api/mcp/logs", methods=["GET"])
@login_required
def get_mcp_logs() -> Union[Response, Tuple[Response, int]]:
    """Get MCP server logs

    Returns:
        JSON response with logs or error
    """
    server_manager = get_server_manager()

    pid = request.args.get("pid", type=int)
    lines = request.args.get("lines", 50, type=int)
    from_index = request.args.get("from_index", type=int)

    if not pid:
        return jsonify({"error": "PID parameter required"}), 400

    try:
        logs = server_manager.get_logs(pid, lines, from_index)
        return jsonify({"logs": logs})
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return jsonify({"error": str(e)}), 500
