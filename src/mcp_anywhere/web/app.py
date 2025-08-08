import asyncio
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
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
from mcp_anywhere.web.middleware import SessionAuthMiddleware, RedirectMiddleware, MCPAuthMiddleware

logger = get_logger(__name__)


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


async def _init_oauth_data():
    """Initialize OAuth data in the database."""
    try:
        admin_user, oauth_client = await initialize_oauth_data()
        logger.info(
            f"OAuth initialized - Admin: {admin_user.username}, Client: {oauth_client.client_id}"
        )
    except Exception as e:
        logger.error(f"Failed to initialize OAuth data: {e}")
        logger.exception("Full exception details:")
        raise


async def start_csrf_cleanup_bg(app):
    """Start background task to clean up expired CSRF states."""
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
    return csrf_cleanup_task


async def _init_mcp_manager(app):
    """Initialize the MCP manager and mount it to the app."""
    mcp_manager = await create_mcp_manager()
    app.state.mcp_manager = mcp_manager
    logger.info("Application initialized with MCP manager")
    return mcp_manager


async def _init_container_manager(app):
    """Initialize the container manager and load default servers."""
    container_manager = ContainerManager()
    await container_manager.initialize_and_build_servers()
    app.state.container_manager = container_manager
    logger.info("Container manager initialized and default servers loaded")
    return container_manager


async def _mount_mcp_app(app, mcp_manager):
    mcp_http_app = mcp_manager.router.http_app(path="/", transport="http")
    app.state.mcp_http_app = mcp_http_app
    app.mount(Config.MCP_PATH_MOUNT, mcp_http_app)
    logger.info(f"FastMCP HTTP app mounted at {Config.MCP_PATH_MOUNT}")


def create_lifespan(transport_mode: str):
    """Create a lifespan function with the given transport mode."""

    @asynccontextmanager
    async def lifespan(app: Starlette):
        """Application lifespan context to initialize resources on startup."""
        # Initialize database
        await init_db()

        # Initialize OAuth data
        await _init_oauth_data()

        # Initialize container manager and load default servers
        container_manager = await _init_container_manager(app)

        # Initialize MCP manager
        mcp_manager = await _init_mcp_manager(app)

        # Mount all built servers to MCP manager and discover tools
        await container_manager.mount_built_servers(mcp_manager)
        logger.info("Built servers mounted to MCP manager")

        # Create and mount FastMCP HTTP app for HTTP mode
        if transport_mode == "http":
            # Create the FastMCP HTTP app using path="/" to avoid double-mounting
            # Since it will be mounted at MCP path in the main Starlette app
            await _mount_mcp_app(app, mcp_manager)

        # Initialize CSRF protection if in HTTP mode
        csrf_cleanup_task = None
        if transport_mode == "http":
            csrf_cleanup_task = await start_csrf_cleanup_bg(app)

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


async def create_app(transport_mode: str = "http") -> Starlette:
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

   # Add database session function to app state
    app.state.get_async_session = get_async_session

    # Store transport mode and shared OAuth provider in app state
    app.state.transport_mode = transport_mode
    if shared_oauth_provider:
        app.state.oauth_provider = shared_oauth_provider

    return app


