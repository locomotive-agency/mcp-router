"""FastMCP server implementation for MCP Router using proxy pattern"""

from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from sqlalchemy.exc import SQLAlchemyError, DatabaseError
from mcp_router.middleware import ToolFilterMiddleware
from mcp_router.models import MCPServer, MCPServerTool, db
from mcp_router.app import app, run_web_ui_in_background
from mcp_router.container_manager import ContainerManager
from mcp_router.logging_config import get_logger

logger = get_logger(__name__)


def create_mcp_config(servers: List[MCPServer]) -> Dict[str, Any]:
    """Convert database servers to MCP proxy configuration format."""
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
    """Store discovered tools in the database."""
    try:
        with app.app_context():

            # Update database to match the discovered tools while perserving other model fields
            existing_tools = {
                tool.tool_name: tool.to_dict()
                for tool in MCPServerTool.query.filter_by(server_id=server_config.id).all()
            }

            discovered_tools_dict = {tool["name"]: tool for tool in discovered_tools}

            # set of tools to add
            tools_to_add = discovered_tools_dict.keys() - existing_tools.keys()

            # set of tools to remove
            tools_to_remove = existing_tools.keys() - discovered_tools_dict.keys()

            # add new tools
            for tool_name in tools_to_add:
                db.session.add(
                    MCPServerTool(
                        server_id=server_config.id,
                        tool_name=tool_name,
                        tool_description=discovered_tools_dict[tool_name]["description"],
                        is_enabled=True,
                    )
                )
            logger.info(f"Added {len(tools_to_add)} tools for server '{server_config.name}'")

            # remove tools
            for tool_name in tools_to_remove:
                tool = MCPServerTool.query.filter_by(
                    server_id=server_config.id, tool_name=tool_name
                ).first()
                db.session.delete(tool)
            logger.info(f"Removed {len(tools_to_remove)} tools for server '{server_config.name}'")

            db.session.commit()
            logger.info(
                f"Stored {len(discovered_tools_dict)} tools for server '{server_config.name}'"
            )

    except (SQLAlchemyError, DatabaseError) as e:
        logger.error(f"Database error storing tools for {server_config.name}: {e}")
        # Don't raise here to avoid breaking server mounting
    except (KeyError, TypeError) as e:
        logger.error(f"Data format error storing tools for {server_config.name}: {e}")
        # Don't raise here to avoid breaking server mounting


class MCPManager:
    """
    Manages the MCP router and handles runtime server mounting/unmounting.

    This class encapsulates the FastMCP router and provides methods to dynamically
    add and remove MCP servers at runtime using FastMCP's mount() capability.
    """

    def __init__(self, router: FastMCP):
        """Initialize the MCP manager with a router."""
        self.router = router
        self.mounted_servers: Dict[str, FastMCP] = {}
        logger.info("Initialized MCPManager")

    async def add_server(self, server_config: MCPServer) -> None:
        """Add a new MCP server dynamically using FastMCP's mount capability."""
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

            logger.info(
                f"Successfully mounted server '{server_config.name}' with prefix '{prefix}'"
            )

            # Discover and store tools for this newly added server
            await self._update_server_tools(server_config)

        except Exception as e:
            logger.error(f"Failed to add server '{server_config.name}': {e}")
            # Continue with other servers rather than raising

    def remove_server(self, server_id: str) -> None:
        """Remove an MCP server dynamically by unmounting it from all managers."""
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

            logger.info(f"Successfully unmounted server '{server_id}' from all managers")

        except Exception as e:
            logger.error(f"Failed to remove server '{server_id}': {e}")
            raise

    async def _update_server_tools(self, server_config: MCPServer) -> None:
        """Update the tools for a server."""
        tools = await self.mounted_servers[server_config.id]._tool_manager.get_tools()

        # Find tools that belong to this server
        discovered_tools = []
        for key, tool in tools.items():
            discovered_tools.append({"name": key, "description": tool.description or ""})

        store_server_tools(server_config, discovered_tools)

        logger.info(f"Updated tools for server '{server_config.name}'")

    def _remove_server_tools(self, server_id: str) -> None:
        """Remove the tools for a server."""
        with app.app_context():
            MCPServerTool.query.filter_by(server_id=server_id).delete()
            db.session.commit()

            logger.info(f"Removed tools for server '{server_id}'")


async def create_mcp_manager(
    api_key: Optional[str] = None, enable_oauth: bool = False
) -> MCPManager:
    """Create the MCP manager with router and dynamic server management capabilities."""

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

    # Add the middleware for tool filtering based on database settings
    router.add_middleware(ToolFilterMiddleware())

    # Create and return the MCP manager
    mcp_manager = MCPManager(router)
    return mcp_manager


async def get_http_app():
    """Configure and retrieve the MCP ASGI application."""
    logger.info("Configuring MCP ASGI app...")

    with app.app_context():
        # Create the MCP manager with router
        mcp_manager = await create_mcp_manager()

        # Store MCP manager reference in Flask app for access from routes
        app.mcp_manager = mcp_manager

    logger.info("MCP ASGI app configured.")

    # Since this app is already mounted at /mcp in the ASGI configuration,
    # we use the root path "/" to avoid double-mounting (which would cause /mcp/mcp)
    return mcp_manager.router.http_app(path="/")


async def run_stdio_mode():
    """Main function to run the MCP server in STDIO mode."""
    logger.info("Starting MCP Router in STDIO mode...")

    # Run the Flask web UI in a background thread
    run_web_ui_in_background()

    # Create the MCP manager - servers are mounted by initialize_mcp_router()
    with app.app_context():
        # In STDIO mode, authentication is not handled by the router itself
        mcp_manager = await create_mcp_manager()

        # Store MCP manager reference in Flask app for access from routes
        app.mcp_manager = mcp_manager

    # Run the stdio transport in the main thread
    logger.info("Running with stdio transport for local clients (e.g., Claude Desktop)")
    mcp_manager.router.run(transport="stdio")
