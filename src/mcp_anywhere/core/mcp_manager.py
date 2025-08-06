"""MCP Manager for handling dynamic server mounting and unmounting"""

from typing import Any

from fastmcp import FastMCP

from mcp_anywhere.container.manager import ContainerManager
from mcp_anywhere.database import MCPServer
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


def create_mcp_config(servers: list["MCPServer"]) -> dict[str, Any]:
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


def create_gateway_config(servers: list["MCPServer"]) -> dict[str, Any]:
    """Create MCP proxy configuration for the lightweight gateway.

    This connects to existing running containers instead of creating new ones.
    Containers should already be created and running by the management server.

    Args:
        servers: List of MCPServer instances from database

    Returns:
        Dict containing MCP server configurations for existing containers
    """
    config = {"mcpServers": {}}
    container_manager = ContainerManager()

    for server in servers:
        # Check if container is already running
        container_name = f"mcp-{server.id}"

        # Use docker exec to connect to existing container instead of docker run
        run_command = container_manager._parse_start_command(server)

        if not run_command:
            logger.warning(f"No start command for server {server.name}, skipping")
            continue

        # Connect to existing container via docker exec
        config["mcpServers"][server.name] = {
            "command": "docker",
            "args": [
                "exec",
                "-i",  # Interactive (for stdio)
                container_name,  # Existing container name
                *run_command,  # The actual MCP command
            ],
            "env": {},
            "transport": "stdio",
        }

    return config


class MCPManager:
    """Manages the MCP Anywhere router and handles runtime server mounting/unmounting.

    This class encapsulates the FastMCP router and provides methods to dynamically
    add and remove MCP servers at runtime using FastMCP's mount() capability.
    """

    def __init__(self, router: FastMCP):
        """Initialize the MCP manager with a router."""
        self.router = router
        self.mounted_servers: dict[str, FastMCP] = {}
        logger.info("Initialized MCPManager")

    async def add_server(self, server_config: "MCPServer") -> list[dict[str, Any]]:
        """Add a new MCP server dynamically using FastMCP's mount capability.

        Args:
            server_config: The MCPServer database model

        Returns:
            List of discovered tools from the server
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

            logger.info(
                f"Successfully mounted server '{server_config.name}' with prefix '{prefix}'"
            )

            # Discover and return tools for this newly added server
            return await self._discover_server_tools(server_config.id)

        except (RuntimeError, ValueError, ConnectionError, OSError) as e:
            logger.error(f"Failed to add server '{server_config.name}': {e}")
            raise

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

            # Remove from our tracking
            del self.mounted_servers[server_id]

            logger.info(f"Successfully unmounted server '{server_id}' from all managers")

        except (RuntimeError, ValueError, KeyError) as e:
            logger.error(f"Failed to remove server '{server_id}': {e}")
            raise

    async def _discover_server_tools(self, server_id: str) -> list[dict[str, Any]]:
        """Discover tools from a mounted server.

        Args:
            server_id: The ID of the server to discover tools from

        Returns:
            List of discovered tools with name and description
        """
        if server_id not in self.mounted_servers:
            return []

        try:
            tools = await self.mounted_servers[server_id]._tool_manager.get_tools()

            # Convert tools to the format expected by the database
            discovered_tools = []
            for key, tool in tools.items():
                discovered_tools.append({"name": key, "description": tool.description or ""})

            logger.info(f"Discovered {len(discovered_tools)} tools for server '{server_id}'")
            return discovered_tools

        except (RuntimeError, ValueError, ConnectionError, AttributeError) as e:
            logger.error(f"Failed to discover tools for server '{server_id}': {e}")
            return []
