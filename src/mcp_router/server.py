"""FastMCP server implementation for MCP Router using proxy pattern"""

import asyncio


from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from sqlalchemy.exc import SQLAlchemyError, DatabaseError
from mcp_router.middleware import ToolFilterMiddleware
from mcp_router.models import get_active_servers, MCPServer, MCPServerTool, db
from mcp_router.app import app, run_web_ui_in_background
from mcp_router.container_manager import ContainerManager
from mcp_router.logging_config import get_logger

logger = get_logger(__name__)


def create_mcp_config(servers: List[MCPServer]) -> Dict[str, Any]:
    """
    Convert database servers to MCP proxy configuration format.

    Each server runs in its own Docker container built by Container Manager.
    Environment variables are passed at runtime.
    """
    config = {"mcpServers": {}}
    container_manager = ContainerManager()

    for server in servers:
        # Docker image tag built by container_manager
        image_tag = container_manager.get_image_tag(server)

        # Extract environment variables
        env_args = []
        for env_var in server.env_variables:
            if env_var.get("value"):
                key = env_var["key"]
                value = env_var["value"]
                env_args.extend(["-e", f"{key}={value}"])

        # Use container manager's parsing logic for commands
        run_command = container_manager._parse_start_command(server)

        if not run_command:
            logger.warning(f"No start command for server {server.name}, skipping")
            continue

        # Docker command that FastMCP will execute
        config["mcpServers"][server.name] = {
            "command": "docker",
            "args": [
                "run",
                "--rm",  # Remove container after exit
                "-i",  # Interactive (for stdio)
                "--name",
                f"mcp-{server.id}",  # Container name
                "--memory",
                "512m",  # Memory limit
                "--cpus",
                "0.5",  # CPU limit
                *env_args,  # Environment variables
                image_tag,  # Our pre-built image
                *run_command,  # The actual MCP command
            ],
            "env": {},  # Already passed via docker -e
            "transport": "stdio",
        }

    return config



def store_server_tools(server_config: MCPServer, discovered_tools: List[Dict[str, Any]]) -> None:
    """
    Store discovered tools in the database.
    
    Args:
        server_config: The MCPServer configuration
        discovered_tools: List of tool definitions
    """
    try:
        with app.app_context():
            

            # Update database to match the discovered tools while perserving other model fields
            existing_tools = {tool.tool_name: tool.to_dict() for tool in MCPServerTool.query.filter_by(server_id=server_config.id).all()}

            discovered_tools_dict = {tool['name']: tool for tool in discovered_tools}

            #set of tools to add
            tools_to_add = discovered_tools_dict.keys() - existing_tools.keys()

            #set of tools to remove
            tools_to_remove = existing_tools.keys() - discovered_tools_dict.keys()

            #add new tools
            for tool_name in tools_to_add:
                db.session.add(MCPServerTool(server_id=server_config.id, tool_name=tool_name, tool_description=discovered_tools_dict[tool_name]['description'], is_enabled=True))
            logger.info(f"Added {len(tools_to_add)} tools for server '{server_config.name}'")
            
            #remove tools
            for tool_name in tools_to_remove:
                tool = MCPServerTool.query.filter_by(server_id=server_config.id, tool_name=tool_name).first()
                db.session.delete(tool)
            logger.info(f"Removed {len(tools_to_remove)} tools for server '{server_config.name}'")


            db.session.commit()
            logger.info(f"Stored {len(discovered_tools_dict)} tools for server '{server_config.name}'")


    except (SQLAlchemyError, DatabaseError) as e:
        logger.error(f"Database error storing tools for {server_config.name}: {e}")
        # Don't raise here to avoid breaking server mounting
    except (KeyError, TypeError) as e:
        logger.error(f"Data format error storing tools for {server_config.name}: {e}")
        # Don't raise here to avoid breaking server mounting



class DynamicServerManager:
    """
    Manages dynamic addition and removal of MCP servers using FastMCP's mount() capability.

    This class provides the ability to add and remove MCP servers at runtime without
    requiring a full router reconstruction, leveraging FastMCP's built-in server composition.
    """

    def __init__(self, router: FastMCP):
        """
        Initialize the dynamic server manager.

        Args:
            router: The FastMCP router instance to manage
        """
        self.router = router
        self.mounted_servers: Dict[str, FastMCP] = {}
        self.server_descriptions: Dict[str, str] = {}
        logger.info("Initialized DynamicServerManager")


    async def add_server(self, server_config: MCPServer) -> None:
        """
        Add a new MCP server dynamically using FastMCP's mount capability.

        Args:
            server_config: MCPServer instance
        """
        try:
            # Create proxy configuration for this single server
            proxy_config = create_mcp_config([server_config])

            if not proxy_config["mcpServers"]:
                raise RuntimeError(f"Failed to create proxy config for {server_config.name}")

            # Create FastMCP proxy for the server
            proxy = FastMCP.as_proxy(proxy_config)

            # Mount with 8-character prefix
            prefix = server_config.id
            self.router.mount(proxy, prefix=prefix)

            # Track the mounted server
            self.mounted_servers[server_config.id] = proxy
            self.server_descriptions[server_config.id] = server_config.description or ""

            logger.info(
                f"Successfully mounted server '{server_config.name}' with prefix '{prefix}'"
            )

            # Discover and store tools for this newly added server
            logger.info(f"Updating tools for server '{server_config.name}'")
            await self._update_server_tools(server_config)
            logger.info(f"Updated tools for server '{server_config.name}'")

        except Exception as e:
            logger.error(f"Failed to add server '{server_config.name}': {e}")
            # Continue with other servers rather than raising


    def remove_server(self, server_id: str) -> None:
        """
        Remove an MCP server dynamically by unmounting it from all managers.

        This uses the internal FastMCP managers to properly remove a mounted server,
        as FastMCP doesn't provide a public unmount() method.

        Args:
            server_name: Name of the server to remove
        """
        if server_id not in self.mounted_servers:
            logger.warning(f"Server '{server_id}' not found in mounted servers")
            return

        try:
            # Get the mounted server proxy
            mounted_server = self.mounted_servers[server_id]

            # Remove from all FastMCP internal managers
            # Based on FastMCP developer's example in issue #934
            for manager in [
                self.router._tool_manager,
                self.router._resource_manager,
                self.router._prompt_manager,
            ]:
                # Find and remove the mount for this server
                mounts_to_remove = [
                    m for m in manager._mounted_servers if m.server is mounted_server
                ]
                for mount in mounts_to_remove:
                    manager._mounted_servers.remove(mount)
                    logger.debug(f"Removed mount from {manager.__class__.__name__}")

            # Clear the router cache to ensure changes take effect
            self.router._cache.clear()

            # Remove the tools for the server
            self._remove_server_tools(server_id)

            # Remove from our tracking
            del self.mounted_servers[server_id]
            del self.server_descriptions[server_id]

            logger.info(f"Successfully unmounted server '{server_id}' from all managers")

        except Exception as e:
            logger.error(f"Failed to remove server '{server_id}': {e}")
            raise

    
    async def _update_server_tools(self, server_config: MCPServer) -> None:
        """
        Update the tools for a server.

        Args:
            server_config: The MCPServer configuration

        """
        tools = await self.mounted_servers[server_config.id]._tool_manager.get_tools()
        logger.info(f"Discovered tools: {tools}")

        # Find tools that belong to this server
        discovered_tools = []
        for key, tool in tools.items():
            discovered_tools.append({
                'name': key,
                'description': tool.description or ''
            })


        store_server_tools(server_config, discovered_tools)

        logger.info(f"Updated tools for server '{server_config.name}'")


    def _remove_server_tools(self, server_id: str) -> None:
        """
        Remove the tools for a server.

        Args:
            server_name: The name of the server to remove
        """
        with app.app_context():
            MCPServerTool.query.filter_by(server_id=server_id).delete()
            db.session.commit()

            logger.info(f"Removed tools for server '{server_id}'")






# Global reference to the dynamic manager for access from routes
_dynamic_manager: Optional[DynamicServerManager] = None


def get_dynamic_manager() -> Optional[DynamicServerManager]:
    """
    Get the current dynamic server manager instance.

    Returns:
        DynamicServerManager instance if available, None otherwise
    """
    # Try to get from Flask app context first
    try:
        if hasattr(app, "mcp_router") and hasattr(app.mcp_router, "_dynamic_manager"):
            return app.mcp_router._dynamic_manager
    except RuntimeError:
        # No Flask app context available
        pass

    # Fall back to global reference
    return _dynamic_manager


async def create_router(
    servers: List[MCPServer], api_key: Optional[str] = None, enable_oauth: bool = False
) -> FastMCP:
    """
    Create the MCP router with dynamic server management capabilities.

    Args:
        servers: List of active MCP servers to mount initially
        api_key: Optional API key for simple authentication
        enable_oauth: Enable OAuth authentication for Claude web
    """
    global _dynamic_manager

    # Prepare authentication
    auth = None
    if enable_oauth:
        # Proxy layer validates OAuth; FastMCP doesn't need to re-validate
        logger.info(
            "OAuth validated at proxy layer; FastMCP running without additional auth provider"
        )
    elif api_key:
        # For API key auth, FastMCP expects the key to be validated at the transport layer
        # The Flask proxy handles this validation
        logger.info("API key authentication will be handled by the HTTP proxy layer")

    # Create base router (always create a standalone router for dynamic mounting)
    router = FastMCP(
        name="MCP-Router",
        auth=auth,
        instructions="""This router provides access to multiple MCP servers and a Python sandbox.

All tools from mounted servers are available directly with prefixed names.

You can use tools/list to see all available tools from all mounted servers.
""",
    )

    # Initialize dynamic server manager
    _dynamic_manager = DynamicServerManager(router)

    # Store reference in router for access from routes
    router._dynamic_manager = _dynamic_manager

    # Mount all existing servers dynamically
    for server in servers:
        try:
            # Mount servers synchronously during initialization
            # Create proxy configuration for the single server
            proxy_config = create_mcp_config([server])

            if not proxy_config["mcpServers"]:
                logger.warning(f"Skipping server '{server.name}' - no valid configuration")
                continue

            # Create FastMCP proxy for the server
            proxy = FastMCP.as_proxy(proxy_config)

            # Mount it with the server ID as prefix
            router.mount(proxy, prefix=server.id)

            # Track the server and its description in the dynamic manager
            _dynamic_manager.mounted_servers[server.id] = proxy
            _dynamic_manager.server_descriptions[server.id] = (
                server.description or "No description provided"
            )

            await _dynamic_manager._update_server_tools(server)

            logger.info(f"Successfully mounted server '{server.name}' with prefix '{server.id}'")

            # Tool discovery will be handled after all servers are mounted

        except Exception as e:
            logger.error(f"Failed to mount server '{server.name}' during initialization: {e}")
            continue


    # Add the middleware for tool filtering based on database settings
    router.add_middleware(ToolFilterMiddleware())

    return router


def get_http_app():
    """
    Configure and retrieve the MCP ASGI application.

    Returns:
        Callable: The MCP ASGI application.
    """
    logger.info("Configuring MCP ASGI app...")

    # Fetch active servers from the database
    with app.app_context():
        # Create the router with no servers initially.
        # Servers will be mounted dynamically after initialization.
        router = create_router([])

        # Store router reference in Flask app for access from routes
        app.mcp_router = router

    logger.info("MCP ASGI app configured.")

    # Since this app is already mounted at /mcp in the ASGI configuration,
    # we use the root path "/" to avoid double-mounting (which would cause /mcp/mcp)
    return router.http_app(path="/")


async def run_stdio_mode():
    """Main function to run the MCP server in STDIO mode."""
    logger.info("Starting MCP Router in STDIO mode...")

    # Run the Flask web UI in a background thread
    run_web_ui_in_background()

    # Fetch active servers from the database
    with app.app_context():
        active_servers = get_active_servers()
        logger.info(f"Loaded {len(active_servers)} active servers from database")

        # Create the router
        # In STDIO mode, authentication is not handled by the router itself
        router = await create_router(active_servers)

        # Store router reference in Flask app for access from routes
        app.mcp_router = router

    # Run the stdio transport in the main thread
    logger.info("Running with stdio transport for local clients (e.g., Claude Desktop)")
    router.run(transport="stdio")
