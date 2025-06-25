"""FastMCP server implementation for MCP Router"""
import asyncio
import logging
from fastmcp import FastMCP
from llm_sandbox import SandboxSession
from mcp_router.container_manager import ContainerManager
from mcp_router.models import get_active_servers
from mcp_router.app import app  # Import app to get context

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name="MCP-Router",
    instructions="""This router provides access to multiple MCP servers and a Python sandbox.
    Use 'python_sandbox' for data analysis with pandas, numpy, matplotlib, etc.
    Other tools are dynamically loaded from configured servers."""
)

# Built-in Python sandbox tool
@mcp.tool()
def python_sandbox(code: str, libraries: list[str] = None) -> dict:
    """
    Execute Python code in a secure sandbox with data science libraries.
    
    Args:
        code: Python code to execute.
        libraries: Additional pip packages to install (e.g., ["pandas", "scikit-learn"]).
    
    Returns:
        A dictionary with stdout, stderr, and exit_code.
    """
    log.info(f"Executing Python code with libraries: {libraries}")
    
    # Default libraries always available
    default_libs = ["pandas", "numpy", "matplotlib", "seaborn", "scipy"]
    
    try:
        with SandboxSession(lang="python", timeout=30) as session:
            # Install default + requested libraries
            all_libs = default_libs + (libraries or [])
            if all_libs:
                install_cmd = f"pip install --no-cache-dir {' '.join(all_libs)}"
                result = session.execute_command(install_cmd)
                if result.exit_code != 0:
                    return {
                        "status": "error",
                        "message": "Failed to install libraries",
                        "stderr": result.stderr
                    }
            
            # Execute code
            result = session.run(code)
            
            return {
                "status": "success" if result.exit_code == 0 else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code
            }
    except Exception as e:
        log.error(f"Sandbox error: {e}")
        return {"status": "error", "message": str(e)}

# Container manager for dynamic servers
container_manager = ContainerManager(app=app)

async def register_server_tools(servers: list):
    """Dynamically register tools from a list of server objects"""
    for server in servers:
        # Create a tool function for each server
        async def server_tool(**kwargs):
            """Dynamic tool that proxies to a containerized server"""
            return await container_manager.execute_server_tool(
                server_id=server.id,
                tool_params=kwargs
            )
        
        # Register with a unique name
        tool_name = f"{server.name}_tool"
        server_tool.__name__ = tool_name
        server_tool.__doc__ = f"Tool from {server.name}: {server.description}"
        
        mcp.tool()(server_tool)
        log.info(f"Registered tool: {tool_name}")

def main():
    """Main function to run the MCP server."""
    log.info("Starting MCP Router server...")

    # Synchronously fetch servers from the database before starting the event loop
    with app.app_context():
        active_servers = get_active_servers()

    # Register dynamic tools on startup
    asyncio.run(register_server_tools(active_servers))
    
    # Run with stdio for Claude Desktop
    log.info("Running with stdio transport for Claude Desktop.")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main() 