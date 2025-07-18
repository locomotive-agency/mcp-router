"""FastMCP server implementation for MCP Router using proxy pattern"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from llm_sandbox import SandboxSession
from mcp_router.middleware import ProviderFilterMiddleware
from mcp_router.models import get_active_servers, MCPServer
from mcp_router.app import app, run_web_ui_in_background
from mcp_router.config import Config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def create_mcp_config(servers: List[MCPServer]) -> Dict[str, Any]:
    """
    Convert database servers to MCP proxy configuration format.

    Each server becomes a sub-server that the proxy will manage.
    """
    config = {"mcpServers": {}}

    for server in servers:
        # Build the command based on runtime type
        if server.runtime_type == "npx":
            command = "npx"
            args = (
                server.start_command.split()[1:]
                if server.start_command.startswith("npx ")
                else [server.start_command]
            )
        elif server.runtime_type == "uvx":
            command = "uvx"
            args = (
                server.start_command.split()[1:]
                if server.start_command.startswith("uvx ")
                else [server.start_command]
            )
        elif server.runtime_type == "docker":
            command = "docker"
            args = ["run", "--rm", "-i", server.start_command]
        else:
            log.warning(f"Unknown runtime type for {server.name}: {server.runtime_type}")
            continue

        # Extract environment variables
        env = {}
        for env_var in server.env_variables:
            if env_var.get("value"):
                env[env_var["key"]] = env_var["value"]

        # Each server configuration for the proxy
        config["mcpServers"][server.name] = {
            "command": command,
            "args": args,
            "env": env,
            "transport": "stdio",  # All sub-servers use stdio within containers
        }

    return config


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
        log.info("Initialized DynamicServerManager")
    
    def add_server(self, server_config: MCPServer) -> None:
        """
        Add a new MCP server dynamically using FastMCP's mount() capability.
        
        Args:
            server_config: MCPServer instance containing server configuration
        """
        try:
            # Create proxy configuration for the single server
            proxy_config = create_mcp_config([server_config])
            
            # Create FastMCP proxy for the server
            proxy = FastMCP.as_proxy(proxy_config)
            
            # Mount it with the server name as prefix (synchronous operation)
            self.router.mount(proxy, prefix=server_config.name)
            
            # Track the server and its description
            self.mounted_servers[server_config.name] = proxy
            self.server_descriptions[server_config.name] = server_config.description or "No description provided"
            
            log.info(f"Successfully mounted server '{server_config.name}' dynamically")
            
        except Exception as e:
            log.error(f"Failed to add server '{server_config.name}': {e}")
            raise
    
    def remove_server(self, server_name: str) -> None:
        """
        Remove an MCP server dynamically by unmounting it from all managers.
        
        This uses the internal FastMCP managers to properly remove a mounted server,
        as FastMCP doesn't provide a public unmount() method.
        
        Args:
            server_name: Name of the server to remove
        """
        if server_name not in self.mounted_servers:
            log.warning(f"Server '{server_name}' not found in mounted servers")
            return
            
        try:
            # Get the mounted server proxy
            mounted_server = self.mounted_servers[server_name]
            
            # Remove from all FastMCP internal managers
            # Based on FastMCP developer's example in issue #934
            for manager in [self.router._tool_manager, self.router._resource_manager, self.router._prompt_manager]:
                # Find and remove the mount for this server
                mounts_to_remove = [m for m in manager._mounted_servers if m.server is mounted_server]
                for mount in mounts_to_remove:
                    manager._mounted_servers.remove(mount)
                    log.debug(f"Removed mount from {manager.__class__.__name__}")
            
            # Clear the router cache to ensure changes take effect
            self.router._cache.clear()
            
            # Remove from our tracking
            del self.mounted_servers[server_name]
            del self.server_descriptions[server_name]
            
            log.info(f"Successfully unmounted server '{server_name}' from all managers")
            
        except Exception as e:
            log.error(f"Failed to remove server '{server_name}': {e}")
            raise
    
    def get_providers(self) -> List[Dict[str, str]]:
        """
        Get list of providers with descriptions.
        
        Returns:
            List of dictionaries containing provider name and description
        """
        providers = [
            {"name": name, "description": desc}
            for name, desc in self.server_descriptions.items()
        ]
        log.debug(f"Returning {len(providers)} providers")
        return providers
    
    def get_provider_names(self) -> List[str]:
        """
        Get list of provider names only.
        
        Returns:
            List of provider names
        """
        return list(self.server_descriptions.keys())


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
        if hasattr(app, 'mcp_router') and hasattr(app.mcp_router, '_dynamic_manager'):
            return app.mcp_router._dynamic_manager
    except RuntimeError:
        # No Flask app context available
        pass
    
    # Fall back to global reference
    return _dynamic_manager


def create_router(
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
        log.info("OAuth validated at proxy layer; FastMCP running without additional auth provider")
    elif api_key:
        # For API key auth, FastMCP expects the key to be validated at the transport layer
        # The Flask proxy handles this validation
        log.info("API key authentication will be handled by the HTTP proxy layer")

    # Create base router (always create a standalone router for dynamic mounting)
    router = FastMCP(
        name="MCP-Router",
        auth=auth,
        instructions="""This router provides access to multiple MCP servers and a Python sandbox.

Use 'list_providers' to see available servers, then use tools/list with a provider parameter.

Example workflow:
1. Call list_providers() to see available servers
2. Call tools/list with provider="server_name" to see that server's tools
3. Call tools with provider="server_name" parameter to execute them
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
            
            # Create FastMCP proxy for the server
            proxy = FastMCP.as_proxy(proxy_config)
            
            # Mount it with the server name as prefix
            router.mount(proxy, prefix=server.name)
            
            # Track the server and its description in the dynamic manager
            _dynamic_manager.mounted_servers[server.name] = proxy
            _dynamic_manager.server_descriptions[server.name] = server.description or "No description provided"
            
            log.info(f"Successfully mounted server '{server.name}' during initialization")
            
        except Exception as e:
            log.error(f"Failed to mount server '{server.name}' during initialization: {e}")
            continue

    # Add the built-in Python sandbox tool
    @router.tool()
    def python_sandbox(code: str, libraries: List[str] = None) -> Dict[str, Any]:
        """
        Execute Python code in a secure sandbox with data science libraries.

        Args:
            code: Python code to execute
            libraries: Additional pip packages to install (e.g., ["pandas", "scikit-learn"])

        Returns:
            A dictionary with stdout, stderr, and exit_code
        """
        log.info(f"Executing Python code with libraries: {libraries}")

        docker_host = Config.DOCKER_HOST
        sandbox_image_template = "mcp-router-python-sandbox"

        try:
            # Use the pre-built template
            with SandboxSession(
                lang="python",
                template_name=sandbox_image_template,
                timeout=60,
                docker_host=docker_host,
            ) as session:
                # Install only the additional, non-default libraries
                if libraries:
                    default_libs = ["pandas", "numpy", "matplotlib", "seaborn", "scipy"]
                    additional_libs = [lib for lib in libraries if lib not in default_libs]

                    if additional_libs:
                        install_cmd = f"pip install --no-cache-dir {' '.join(additional_libs)}"
                        log.info(f"Installing additional libraries: {install_cmd}")
                        result = session.execute_command(install_cmd)
                        if result.exit_code != 0:
                            log.error(f"Library installation failed: {result.stderr}")
                            return {
                                "status": "error",
                                "message": "Failed to install libraries",
                                "stderr": result.stderr,
                            }

                # Execute code
                log.info("Executing Python code in sandbox")
                result = session.run(code)

                return {
                    "status": "success" if result.exit_code == 0 else "error",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                }
        except Exception as e:
            # Check if the sandbox template is missing
            if "No container template found" in str(e):
                log.error(
                    f"Sandbox template '{sandbox_image_template}' not found. Please restart the web server to build it."
                )
                return {
                    "status": "error",
                    "message": f"Sandbox template '{sandbox_image_template}' not found. It should be built on web server startup.",
                }
            log.error(f"Sandbox error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    @router.tool()
    def list_providers() -> List[Dict[str, str]]:
        """
        List all available MCP server providers with descriptions.

        Returns a list of dictionaries containing provider name and description
        that can be used with the provider parameter in tools/list and tool calls.
        """
        if _dynamic_manager:
            return _dynamic_manager.get_providers()
        else:
            log.warning("Dynamic manager not available, returning empty provider list")
            return []

    # Add the middleware for hierarchical discovery
    router.add_middleware(ProviderFilterMiddleware())

    return router


def create_api_key_auth_provider():
    """Create an API key authentication provider for FastMCP

    Returns:
        Async function that validates API key tokens
    """

    async def validate_api_key(headers: dict) -> dict | None:
        """Validate API key from request headers

        Args:
            headers: Request headers dictionary

        Returns:
            Session data dictionary if valid, None otherwise
        """
        auth_header = headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Check if token matches the configured API key
        if Config.MCP_API_KEY and token == Config.MCP_API_KEY:
            log.info("API key authentication successful")
            return {"user_id": "api_key_user", "auth_type": "api_key", "token": token}

        log.warning("API key authentication failed")
        return None

    return validate_api_key


def get_http_app():
    """
    Configure and retrieve the MCP ASGI application.

    Returns:
        Callable: The MCP ASGI application.
    """
    log.info("Configuring MCP ASGI app...")

    # Fetch active servers from the database
    with app.app_context():
        active_servers = get_active_servers()
        log.info(f"Loaded {len(active_servers)} active servers from database")

        # Create the router
        router = create_router(active_servers)
        
        # Store router reference in Flask app for access from routes
        app.mcp_router = router

    log.info("MCP ASGI app configured.")

    # Since this app is already mounted at /mcp in the ASGI configuration,
    # we use the root path "/" to avoid double-mounting (which would cause /mcp/mcp)
    return router.http_app(path="/")


def run_stdio_mode():
    """Main function to run the MCP server in STDIO mode."""
    log.info("Starting MCP Router in STDIO mode...")

    # Run the Flask web UI in a background thread
    run_web_ui_in_background()

    # Fetch active servers from the database
    with app.app_context():
        active_servers = get_active_servers()
        log.info(f"Loaded {len(active_servers)} active servers from database")

        # Create the router
        # In STDIO mode, authentication is not handled by the router itself
        router = create_router(active_servers)
        
        # Store router reference in Flask app for access from routes
        app.mcp_router = router

    # Run the stdio transport in the main thread
    log.info("Running with stdio transport for local clients (e.g., Claude Desktop)")
    router.run(transport="stdio")
