from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount

from mcp_anywhere.auth.initialization import initialize_oauth_data
from mcp_anywhere.auth.provider import MCPAnywhereAuthProvider
from mcp_anywhere.auth.routes import create_oauth_routes
from mcp_anywhere.config import Config
from mcp_anywhere.container.manager import ContainerManager
from mcp_anywhere.core.mcp_manager import MCPManager
from mcp_anywhere.core.middleware import ToolFilterMiddleware
from mcp_anywhere.database import close_db, get_async_session, init_db
from mcp_anywhere.logging_config import get_logger
from mcp_anywhere.web import routes
from mcp_anywhere.web.config_routes import config_routes
from mcp_anywhere.web.middleware import SessionAuthMiddleware

logger = get_logger(__name__)


class RedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to redirect /mcp to /mcp/"""

    async def dispatch(self, request: Request, call_next):
        mcp_path = Config.MCP_PATH
        if request.url.path == mcp_path:
            return RedirectResponse(url=f"{mcp_path}/")

        # If it's a .well-known path with /mcp, strip it for correct routing
        if ".well-known" in request.url.path and request.url.path.endswith(mcp_path):
            new_path = request.url.path[: -len(mcp_path)]
            request.scope["path"] = new_path

        return await call_next(request)


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that handles authentication for MCP endpoints"""

    async def dispatch(self, request: Request, call_next):
        # Only apply authentication to MCP endpoints (exact path or subpaths)
        path = request.url.path
        mcp_path = Config.MCP_PATH.rstrip("/")

        # Get out early if not an MCP endpoint or if it's a .well-known path
        if not path.startswith(mcp_path) or ".well-known" in path:
            return await call_next(request)

        # Get authorization header
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {
                    "error": "Authorization required",
                    "error_description": "Bearer token required",
                },
                status_code=401,
            )

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Get OAuth provider from app state
        oauth_provider = getattr(request.app.state, "oauth_provider", None)
        if not oauth_provider:
            return JSONResponse(
                {
                    "error": "Authentication configuration error",
                    "error_description": "OAuth provider not initialized",
                },
                status_code=500,
            )

        # Validate OAuth token
        payload = await oauth_provider.verify_token(token)
        if not payload:
            return JSONResponse(
                {
                    "error": "Invalid token",
                    "error_description": "Token is invalid or expired",
                },
                status_code=401,
            )

        # Authentication successful, proceed with request
        return await call_next(request)


async def create_mcp_manager() -> MCPManager:
    """Create the MCP manager with router."""
    # Create base router
    router = FastMCP(
        name="MCP-Anywhere",
        instructions="""This router provides access to multiple MCP servers.
        
All tools from mounted servers are available directly with prefixed names.

You can use tools/list to see all available tools from all mounted servers.
""",
    )

    router.add_middleware(ToolFilterMiddleware())

    return MCPManager(router)


def create_lifespan(transport_mode: str):
    """Create a lifespan function with the given transport mode."""

    @asynccontextmanager
    async def lifespan(app: Starlette):
        """Application lifespan context to initialize resources on startup."""
        # Initialize database
        await init_db()

        # Initialize OAuth data (admin user and default client)
        try:
            admin_user, oauth_client = await initialize_oauth_data()
            logger.info(
                f"OAuth initialized - Admin: {admin_user.username}, Client: {oauth_client.client_id}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize OAuth data: {e}")
            logger.exception("Full exception details:")
            raise

        # Add database session function to app state
        app.state.get_async_session = get_async_session

        # Initialize OAuth provider if in HTTP mode
        if transport_mode == "http":
            app.state.oauth_provider = MCPAnywhereAuthProvider(get_async_session)

        # Initialize container manager and load default servers
        container_manager = ContainerManager()
        await container_manager.initialize_and_build_servers()
        app.state.container_manager = container_manager
        logger.info("Container manager initialized and default servers loaded")

        # Initialize MCP manager
        mcp_manager = await create_mcp_manager()
        app.state.mcp_manager = mcp_manager
        logger.info("Application initialized with MCP manager")

        # Mount all built servers to MCP manager and discover tools
        await container_manager.mount_built_servers(mcp_manager)
        logger.info("Built servers mounted to MCP manager")

        # Create and mount FastMCP HTTP app for HTTP mode
        if transport_mode == "http":
            # Create the FastMCP HTTP app using path="/" to avoid double-mounting
            # Since it will be mounted at /mcp in the main Starlette app
            mcp_http_app = mcp_manager.router.http_app(path="/")
            app.state.mcp_http_app = mcp_http_app

            # Mount the FastMCP app at the MCP path
            app.router.mount(Config.MCP_PATH, mcp_http_app)
            logger.info(f"FastMCP HTTP app mounted at {Config.MCP_PATH}")

        yield

        # Clean up resources on shutdown
        await close_db()

    return lifespan


def create_app(transport_mode: str = "http") -> Starlette:
    """Creates and configures the main Starlette application.

    Args:
        transport_mode: The transport mode ("http" or "stdio")
    """
    # Configure middleware
    middleware = [
        # Session middleware for login state
        Middleware(SessionMiddleware, secret_key=Config.SECRET_KEY),
        # Session-based auth middleware for web UI
        Middleware(SessionAuthMiddleware),
    ]

    # Add MCP-specific middleware for HTTP mode
    if transport_mode == "http":
        middleware.extend(
            [
                Middleware(RedirectMiddleware),
                Middleware(MCPAuthMiddleware),
            ]
        )

    # Create routes - ORDER MATTERS!
    app_routes = []

    # Add OAuth routes FIRST for HTTP mode (before catch-all web mount)
    if transport_mode == "http":
        try:
            # Create OAuth routes using MCP SDK - simple approach
            oauth_routes = create_oauth_routes(get_async_session)
            app_routes.extend(oauth_routes)
            logger.info(f"Added {len(oauth_routes)} OAuth routes")
        except Exception as e:
            logger.error(f"Failed to create OAuth routes: {e}")
            logger.exception("OAuth route creation error:")

    # Add other routes
    app_routes.extend(
        [
            # Mount("/static", app=StaticFiles(directory="src/mcp_anywhere/web/static"), name="static"),
            # Add config routes (for Claude Desktop integration)
            *config_routes,
            # Add web routes LAST (catch-all mount)
            Mount("/", routes=routes.routes, name="web"),
        ]
    )

    # Create the main app with lifespan
    app = Starlette(
        debug=True,
        lifespan=create_lifespan(transport_mode),
        middleware=middleware,
        routes=app_routes,
    )

    # Store transport mode in app state for UI display
    app.state.transport_mode = transport_mode

    return app


async def create_asgi_app(transport_mode: str = "http") -> Starlette:
    """Create the ASGI application with FastMCP mounting for HTTP mode."""
    return create_app(transport_mode)
