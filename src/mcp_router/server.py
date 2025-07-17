"""FastMCP server implementation for MCP Router using proxy pattern"""

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


def create_router(
    servers: List[MCPServer], api_key: Optional[str] = None, enable_oauth: bool = False
) -> FastMCP:
    """
    Create the MCP router as a composite proxy with middleware.

    Args:
        servers: List of active MCP servers
        api_key: Optional API key for simple authentication
        enable_oauth: Enable OAuth authentication for Claude web
    """
    # Generate proxy configuration from active servers
    config = create_mcp_config(servers)

    # Prepare authentication
    auth = None
    if enable_oauth:
        # Proxy layer validates OAuth; FastMCP doesn't need to re-validate
        log.info("OAuth validated at proxy layer; FastMCP running without additional auth provider")
    elif api_key:
        # For API key auth, FastMCP expects the key to be validated at the transport layer
        # The Flask proxy handles this validation
        log.info("API key authentication will be handled by the HTTP proxy layer")

    # Check if we have any servers to proxy
    if config["mcpServers"]:
        # Create router as a proxy that manages all sub-servers
        router = FastMCP.as_proxy(
            config,
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
    else:
        # No servers configured, create a standalone MCP server
        router = FastMCP(
            name="MCP-Router",
            auth=auth,
            instructions="""This is the MCP Router. Currently no MCP servers are configured.

You can still use the Python sandbox tool to execute Python code.
To add MCP servers, use the web interface to configure and activate servers.
""",
        )

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
    def list_providers() -> List[str]:
        """
        List all available MCP server providers.

        Returns a list of server names that can be used with the provider parameter
        in tools/list and tool calls.
        """
        # Return the list of server names from the configuration
        return list(config["mcpServers"].keys())

    # Add the middleware for hierarchical discovery only if we have servers
    if config["mcpServers"]:
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

    Args:
        router (FastMCP): The FastMCP router instance.

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

    # Run the stdio transport in the main thread
    log.info("Running with stdio transport for local clients (e.g., Claude Desktop)")
    router.run(transport="stdio")
