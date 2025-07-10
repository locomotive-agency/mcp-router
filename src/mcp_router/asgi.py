
from starlette.applications import Starlette
from a2wsgi import WSGIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp_router.app import app as flask_app
from mcp_router.server import get_mcp_app
from mcp_router.config import Config
from mcp_router.mcp_oauth import verify_token


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that handles authentication for MCP endpoints"""

    async def dispatch(self, request: Request, call_next):
        # Only apply authentication to MCP endpoints
        if not request.url.path.startswith(Config.MCP_PATH):
            return await call_next(request)

        # Check if authentication is required
        if not Config.MCP_OAUTH_ENABLED and not Config.MCP_API_KEY:
            # No authentication configured, allow access
            return await call_next(request)

        # Get authorization header
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Authorization required", "error_description": "Bearer token required"},
                status_code=401,
            )

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Validate token based on configuration
        if Config.MCP_OAUTH_ENABLED:
            # Validate OAuth token
            payload = verify_token(token)
            if not payload:
                return JSONResponse(
                    {"error": "Invalid token", "error_description": "Token is invalid or expired"},
                    status_code=401,
                )
        elif Config.MCP_API_KEY:
            # Validate API key
            if token != Config.MCP_API_KEY:
                return JSONResponse({"error": "Invalid API key"}, status_code=401)

        # Authentication successful, proceed with request
        return await call_next(request)


def create_asgi_app():
    """Create the ASGI application with proper authentication middleware"""
    from starlette.middleware import Middleware

    # Create a WSGIMiddleware-wrapped Flask app
    wsgi_app = WSGIMiddleware(flask_app)
    
    # Create the Starlette application with authentication middleware
    app = Starlette(
        middleware=[Middleware(MCPAuthMiddleware)]
    )

    # Mount the Flask WSGI app at root
    app.mount("/", wsgi_app)

    # Mount the FastMCP ASGI app (without authentication since middleware handles it)
    with flask_app.app_context():
        mcp_app = get_mcp_app()
        app.mount(Config.MCP_PATH, mcp_app)

    return app


# Create the ASGI app instance
asgi_app = create_asgi_app()
