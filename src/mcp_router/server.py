"""FastMCP server implementation for MCP Router using proxy pattern"""
import logging
import os
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from llm_sandbox import SandboxSession
from mcp_router.middleware import ProviderFilterMiddleware
from mcp_router.models import get_active_servers, MCPServer
from mcp_router.app import app
from mcp_router.config import Config
from mcp_router.mcp_oauth import create_bearer_auth_provider

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
            args = server.start_command.split()[1:] if server.start_command.startswith("npx ") else [server.start_command]
        elif server.runtime_type == "uvx":
            command = "uvx"
            args = server.start_command.split()[1:] if server.start_command.startswith("uvx ") else [server.start_command]
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
            "transport": "stdio"  # All sub-servers use stdio within containers
        }
    
    return config


def create_router(servers: List[MCPServer], api_key: Optional[str] = None, enable_oauth: bool = False) -> FastMCP:
    """
    Create the MCP router as a composite proxy with middleware.
    
    Args:
        servers: List of active MCP servers
        api_key: Optional API key for simple authentication
        enable_oauth: Enable OAuth authentication for Claude web
    """
    # Generate proxy configuration from active servers
    config = create_mcp_config(servers)
    
    # Check if we have any servers to proxy
    if config["mcpServers"]:
        # Create router as a proxy that manages all sub-servers
        router = FastMCP.as_proxy(
            config,
            name="MCP-Router",
            instructions="""This router provides access to multiple MCP servers and a Python sandbox.
        
Use 'list_providers' to see available servers, then use tools/list with a provider parameter.

Example workflow:
1. Call list_providers() to see available servers
2. Call tools/list with provider="server_name" to see that server's tools
3. Call tools with provider="server_name" parameter to execute them
"""
        )
    else:
        # No servers configured, create a standalone MCP server
        router = FastMCP(
            name="MCP-Router",
            instructions="""This is the MCP Router. Currently no MCP servers are configured.
            
You can still use the Python sandbox tool to execute Python code.
To add MCP servers, use the web interface to configure and activate servers.
"""
        )
    
    # Log authentication configuration
    if enable_oauth:
        log.info("OAuth authentication will be handled by the HTTP proxy layer")
    elif api_key:
        log.info("API key authentication will be handled by the HTTP proxy layer")
    
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
                docker_host=docker_host
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
                                "stderr": result.stderr
                            }
                
                # Execute code
                log.info("Executing Python code in sandbox")
                result = session.run(code)
                
                return {
                    "status": "success" if result.exit_code == 0 else "error",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code
                }
        except Exception as e:
            # Check if the sandbox template is missing
            if "No container template found" in str(e):
                log.error(f"Sandbox template '{sandbox_image_template}' not found. Please restart the web server to build it.")
                return {"status": "error", "message": f"Sandbox template '{sandbox_image_template}' not found. It should be built on web server startup."}
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


def main():
    """Main function to run the MCP server."""
    log.info("Starting MCP Router server...")
    
    # Get configuration from environment
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    
    # Fetch active servers from database synchronously before async context
    with app.app_context():
        active_servers = get_active_servers()
        log.info(f"Loaded {len(active_servers)} active servers from database")
    
    # Get authentication configuration
    api_key = None
    enable_oauth = False
    
    if transport == "http":
        # Check if OAuth is enabled
        enable_oauth = os.environ.get("MCP_OAUTH_ENABLED", "false").lower() == "true"
        
        if not enable_oauth:
            # Fall back to API key authentication
            api_key = os.environ.get("MCP_API_KEY")
            if api_key:
                log.info("API Key configured for HTTP transport authentication")
            else:
                log.warning("No authentication configured for HTTP transport!")
    
    # Create the router with proxy configuration
    router = create_router(active_servers, api_key=api_key, enable_oauth=enable_oauth)
    
    # Run with appropriate transport
    if transport == "stdio":
        log.info("Running with stdio transport for Claude Desktop")
        router.run(transport="stdio")
    elif transport == "http":
        # HTTP transport configuration
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8001"))  # Different from Flask port
        path = os.environ.get("MCP_PATH", "/mcp")
        log_level = os.environ.get("MCP_LOG_LEVEL", "info")
        
        # Ensure path ends with trailing slash for FastMCP
        if not path.endswith('/'):
            path = path + '/'
        
        log.info(f"Running with HTTP transport on {host}:{port}{path}")
        log.info(f"Authentication: {'OAuth' if enable_oauth else 'API Key' if api_key else 'None'}")
        
        router.run(
            transport="http",
            host=host,
            port=port,
            path=path,
            log_level=log_level
        )
    else:
        raise ValueError(f"Unknown transport: {transport}. Supported: stdio, http")


if __name__ == "__main__":
    main() 