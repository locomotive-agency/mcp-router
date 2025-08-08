import asyncio
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from mcp_anywhere.auth.initialization import initialize_oauth_data
from mcp_anywhere.auth.provider import MCPAnywhereAuthProvider
from mcp_anywhere.auth.routes import create_oauth_http_routes
from mcp_anywhere.auth.csrf import CSRFProtection
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
    """Middleware to redirect MCP mount path to its trailing-slash variant."""

    async def dispatch(self, request: Request, call_next):
        mcp_mount_path = Config.MCP_PATH_MOUNT
        if request.url.path == mcp_mount_path:
            return RedirectResponse(url=f"{Config.MCP_PATH_PREFIX}")

        # If it's a .well-known path with /mcp, strip it for correct routing
        if ".well-known" in request.url.path and request.url.path.endswith(mcp_mount_path):
            new_path = request.url.path[: -len(mcp_mount_path)]
            request.scope["path"] = new_path

        return await call_next(request)


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that handles authentication for MCP endpoints"""

    async def dispatch(self, request: Request, call_next):
        # Only apply authentication to MCP endpoints (exact path or subpaths)
        path = request.url.path
        mcp_path = Config.MCP_PATH_MOUNT

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

        # Validate OAuth token via introspection
        access_token = await oauth_provider.introspect_token(token)
        if not access_token:
            return JSONResponse(
                {
                    "error": "Invalid token",
                    "error_description": "Token is invalid or expired",
                },
                status_code=401,
            )

        # Authentication successful, proceed with request
        return await call_next(request)
## Removed temporary MCP HTTP exception logger used for diagnostics


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

        # Initialize CSRF protection if in HTTP mode
        csrf_cleanup_task = None
        if transport_mode == "http":
            app.state.csrf_protection = CSRFProtection(expiration_seconds=600)
            logger.info("OAuth provider and CSRF protection initialized")
            
            # Start background task for CSRF state cleanup
            async def csrf_cleanup_worker():
                """Background task to periodically clean up expired CSRF states."""
                while True:
                    try:
                        await asyncio.sleep(300)  # Clean up every 5 minutes
                        app.state.csrf_protection.cleanup_expired()
                    except Exception as e:
                        logger.error(f"CSRF cleanup task error: {e}")
                        await asyncio.sleep(60)  # Retry after 1 minute on error
            
            csrf_cleanup_task = asyncio.create_task(csrf_cleanup_worker())
            logger.info("Started CSRF cleanup background task")

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
            # Since it will be mounted at MCP path in the main Starlette app
            mcp_http_app = mcp_manager.router.http_app(path="/")
            app.state.mcp_http_app = mcp_http_app

            # Mount the FastMCP app at the MCP path
            app.router.mount(Config.MCP_PATH_MOUNT, mcp_http_app)
            logger.info(f"FastMCP HTTP app mounted at {Config.MCP_PATH_MOUNT}")

        yield

        # Clean up resources on shutdown
        if csrf_cleanup_task:
            csrf_cleanup_task.cancel()
            try:
                await csrf_cleanup_task
            except asyncio.CancelledError:
                logger.info("CSRF cleanup task cancelled")
        
        await close_db()

    return lifespan


def create_app(transport_mode: str = "http") -> Starlette:
    """Creates and configures the main Starlette application.

    Args:
        transport_mode: The transport mode ("http" or "stdio")
    """
    # Create shared OAuth provider for HTTP mode
    shared_oauth_provider = None
    if transport_mode == "http":
        shared_oauth_provider = MCPAnywhereAuthProvider(get_async_session)
    
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
            # Create OAuth routes using shared provider instance
            oauth_routes = create_oauth_http_routes(get_async_session, shared_oauth_provider)
            app_routes.extend(oauth_routes)
            logger.info(f"Added {len(oauth_routes)} OAuth routes")
        except Exception as e:
            logger.error(f"Failed to create OAuth routes: {e}")
            logger.exception("OAuth route creation error:")

    # Add other routes
    app_routes.extend(
        [
            # Static assets
            #Mount(
            #    "/static",
            #    app=StaticFiles(directory="src/mcp_anywhere/web/static"),
            #    name="static",
            #),
            # Add config routes (for Claude Desktop integration)
            *config_routes,
            # Add web routes explicitly so they don't shadow the /mcp mount
            *routes.routes,
        ]
    )

    # Create the main app with lifespan
    app = Starlette(
        debug=True,
        lifespan=create_lifespan(transport_mode),
        middleware=middleware,
        routes=app_routes,
    )

    # Store transport mode and shared OAuth provider in app state
    app.state.transport_mode = transport_mode
    if shared_oauth_provider:
        app.state.oauth_provider = shared_oauth_provider

    return app


