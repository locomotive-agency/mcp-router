import time
from starlette.applications import Starlette
from a2wsgi import WSGIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp_router.app import app as flask_app
from mcp_router.server import get_http_app
from mcp_router.config import Config
from mcp_router.mcp_oauth import verify_token


# Simple cache with TTL for auth type lookups
auth_type_cache = {"value": None, "expires": 0}


def get_cached_auth_type() -> str:
    """Get auth type with 30-second cache to minimize database hits

    Returns:
        Current auth type ('oauth' or 'api_key')
    """
    current_time = time.time()

    # Check if cache is valid
    if auth_type_cache["expires"] > current_time and auth_type_cache["value"]:
        return auth_type_cache["value"]

    # Cache miss or expired, get from database
    try:
        with flask_app.app_context():
            from mcp_router.models import get_auth_type

            auth_type = get_auth_type()

            # Update cache with 30-second TTL
            auth_type_cache["value"] = auth_type
            auth_type_cache["expires"] = current_time + 30

            return auth_type
    except Exception:
        # Fallback to environment variable if database unavailable
        return Config.MCP_AUTH_TYPE


def clear_auth_type_cache() -> None:
    """Clear the auth type cache to force refresh on next request"""
    auth_type_cache["value"] = None
    auth_type_cache["expires"] = 0


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that handles authentication for MCP endpoints"""

    async def dispatch(self, request: Request, call_next):
        # Only apply authentication to MCP endpoints (exact path or subpaths)
        path = request.url.path
        mcp_path = Config.MCP_PATH

        # Get out early if not an MCP endpoint
        if not path.startswith(mcp_path):
            return await call_next(request)

        # Get authorization header
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Authorization required", "error_description": "Bearer token required"},
                status_code=401,
            )

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Get current auth type preference from database (with caching)
        auth_type = get_cached_auth_type()

        # Validate token based on current auth type preference
        if auth_type == "oauth":
            # Validate OAuth token
            payload = verify_token(token)
            if not payload:
                return JSONResponse(
                    {"error": "Invalid token", "error_description": "Token is invalid or expired"},
                    status_code=401,
                )
        elif auth_type == "api_key":
            # Validate API key
            if token != Config.MCP_API_KEY:
                return JSONResponse({"error": "Invalid API key"}, status_code=401)
        else:
            # Fallback error for invalid auth type
            return JSONResponse(
                {
                    "error": "Authentication configuration error",
                    "error_description": "Invalid auth type",
                },
                status_code=500,
            )

        # Authentication successful, proceed with request
        return await call_next(request)


def create_asgi_app():
    """Create the ASGI application with proper authentication middleware"""
    from starlette.middleware import Middleware

    # Create a WSGIMiddleware-wrapped Flask app
    wsgi_app = WSGIMiddleware(flask_app)

    # Create the FastMCP ASGI app with authentication
    with flask_app.app_context():
        mcp_app = get_http_app()

    # Create the Starlette application with authentication middleware AND lifespan
    app = Starlette(
        middleware=[Middleware(MCPAuthMiddleware)],
        lifespan=mcp_app.lifespan,  # CRITICAL: Pass FastMCP's lifespan to Starlette
    )

    # Mount the FastMCP app at /mcp
    app.mount(Config.MCP_PATH, mcp_app)

    # Mount the Flask WSGI app at root
    app.mount("/", wsgi_app)  # This is the Flask web UI

    return app


# Create the ASGI app instance
asgi_app = create_asgi_app()
