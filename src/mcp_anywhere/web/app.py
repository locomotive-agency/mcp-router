from contextlib import asynccontextmanager
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from fastmcp import FastMCP

from mcp_anywhere.web import routes
from mcp_anywhere.web.middleware import SessionAuthMiddleware
from mcp_anywhere.web.config_routes import config_routes
from mcp_anywhere.database import init_db, close_db, get_async_session
from mcp_anywhere.core.mcp_manager import MCPManager
from mcp_anywhere.container.manager import ContainerManager
from mcp_anywhere.auth.routes import auth_routes
from mcp_anywhere.auth.middleware import MCPProtectionMiddleware
from mcp_anywhere.auth.initialization import initialize_oauth_data
from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import get_logger

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
    
    return MCPManager(router)


@asynccontextmanager
async def lifespan(app: Starlette):
    """
    Application lifespan context to initialize resources on startup.
    """
    # Initialize database
    await init_db()
    
    # Initialize OAuth data (admin user and default client)
    try:
        admin_user, oauth_client = await initialize_oauth_data()
        logger.info(f"OAuth initialized - Admin: {admin_user.username}, Client: {oauth_client.client_id}")
    except Exception as e:
        logger.error(f"Failed to initialize OAuth data: {e}")
        raise
    
    # Add database session function to app state
    app.state.get_async_session = get_async_session
    
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
    
    yield
    
    # Clean up resources on shutdown
    await close_db()


def create_app(transport_mode: str = "http") -> Starlette:
    """
    Creates and configures the main Starlette application.
    
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
    
    # Only add JWT middleware for MCP endpoints in HTTP mode
    # In STDIO mode, MCP communication happens over standard I/O, not HTTP
    if transport_mode == "http":
        middleware.append(
            Middleware(
                MCPProtectionMiddleware,
                secret_key=Config.JWT_SECRET_KEY,
                mcp_path="/mcp",
                required_scopes=["read"]
            )
        )
    
    # Get auth routes
    auth_route_list = auth_routes()
    
    app = Starlette(
        debug=True,
        lifespan=lifespan,
        middleware=middleware,
        routes=[
            Mount('/static', app=StaticFiles(directory='src/mcp_anywhere/web/static'), name='static'),
            # Add auth routes
            *auth_route_list,
            # Add config routes (for Claude Desktop integration)
            *config_routes,
            # Add web routes
            Mount('/', routes=routes.routes, name='web'),
        ],
    )
    
    # Store transport mode in app state for UI display
    app.state.transport_mode = transport_mode
    
    return app