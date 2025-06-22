"""
Main MCP Router Server implementation.

This module provides the core MCP server that acts as a router to multiple
MCP servers running in containers. It implements the MCP protocol and
routes requests to appropriate servers.
"""

import asyncio
import sys
import json
import logging
from typing import Dict, List, Any, Optional
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.tools import Tool

from ..config.settings import Settings
from ..services.container_manager import ContainerManager
from .transport import TransportManager
from .client import MCPClientManager, MCPTool, MCPResource, MCPPrompt
from ..utils.logging import get_logger

logger = get_logger(__name__)


class MCPRouterServer:
    """Main MCP Router Server that aggregates multiple MCP servers."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize the MCP Router Server."""
        self.settings = settings or Settings()
        self.mcp = FastMCP("mcp-router")
        
        # Initialize managers
        self.container_manager = ContainerManager(self.settings)
        self.transport_manager = TransportManager()
        self.client_manager = MCPClientManager(
            self.container_manager,
            self.transport_manager
        )
        
        # Set up default tools
        self._setup_default_tools()
        
        logger.info("MCP Router Server initialized")
    
    def _setup_default_tools(self):
        """Set up default tools provided by the router itself."""
        
        @self.mcp.tool()
        async def python_sandbox(code: str) -> Dict[str, Any]:
            """Execute Python code in a sandboxed environment with data science libraries.
            
            Args:
                code: Python code to execute
                
            Returns:
                Dictionary with execution results
            """
            try:
                # Create a temporary Python sandbox session
                session_id = f"sandbox_{asyncio.get_event_loop().time()}"
                
                # For now, use a simple execution approach
                # In a real implementation, this would use the container manager
                # to create a proper sandboxed Python environment
                
                result = {
                    "output": f"Code execution not yet implemented: {code[:100]}...",
                    "error": "",
                    "exit_code": 0,
                    "type": "sandbox_result"
                }
                
                logger.info("Python sandbox executed", extra={
                    "code_length": len(code),
                    "session_id": session_id
                })
                
                return result
                
            except Exception as e:
                logger.error("Python sandbox execution failed", extra={"error": str(e)})
                return {
                    "output": "",
                    "error": str(e),
                    "exit_code": 1,
                    "type": "sandbox_error"
                }
        
        @self.mcp.tool()
        async def list_available_servers() -> List[Dict[str, Any]]:
            """List all available MCP servers and their capabilities.
            
            Returns:
                List of server information with capabilities
            """
            try:
                # This would query the database for active servers
                # For now, return a placeholder
                servers = [
                    {
                        "id": "default-server",
                        "name": "Default Server",
                        "status": "active",
                        "tools_count": 0,
                        "resources_count": 0,
                        "prompts_count": 0
                    }
                ]
                
                logger.info("Listed available servers", extra={
                    "servers_count": len(servers)
                })
                
                return servers
                
            except Exception as e:
                logger.error("Failed to list servers", extra={"error": str(e)})
                return []
        
        @self.mcp.tool()
        async def refresh_server_tools() -> Dict[str, Any]:
            """Refresh and reload tools from all active servers.
            
            Returns:
                Summary of refreshed tools
            """
            try:
                # Clear existing dynamic tools and reload
                await self._refresh_dynamic_tools()
                
                return {
                    "status": "success",
                    "message": "Server tools refreshed successfully"
                }
                
            except Exception as e:
                logger.error("Failed to refresh server tools", extra={"error": str(e)})
                return {
                    "status": "error",
                    "message": f"Failed to refresh tools: {e}"
                }
    
    async def _refresh_dynamic_tools(self):
        """Refresh tools from all connected MCP servers."""
        try:
            # Get all available tools from client manager
            tools = await self.client_manager.list_all_tools()
            
            # Create dynamic tool wrappers for each MCP tool
            for tool in tools:
                await self._register_dynamic_tool(tool)
            
            logger.info("Dynamic tools refreshed", extra={
                "tools_count": len(tools)
            })
            
        except Exception as e:
            logger.error("Failed to refresh dynamic tools", extra={"error": str(e)})
    
    async def _register_dynamic_tool(self, mcp_tool: MCPTool):
        """Register a dynamic tool that proxies to an MCP server."""
        
        # Create a dynamic tool function
        async def dynamic_tool_func(**kwargs) -> Any:
            """Dynamic tool that routes to MCP server."""
            try:
                result = await self.client_manager.call_tool(
                    mcp_tool.server_id,
                    mcp_tool.name,
                    kwargs
                )
                return result
            except Exception as e:
                logger.error("Dynamic tool call failed", extra={
                    "tool_name": mcp_tool.name,
                    "server_id": mcp_tool.server_id,
                    "error": str(e)
                })
                raise
        
        # Set function metadata
        dynamic_tool_func.__name__ = f"{mcp_tool.server_id}_{mcp_tool.name}"
        dynamic_tool_func.__doc__ = f"{mcp_tool.description}\n\nServer: {mcp_tool.server_id}"
        
        # Register the tool with FastMCP
        tool = Tool(
            name=f"{mcp_tool.server_id}_{mcp_tool.name}",
            description=mcp_tool.description,
            func=dynamic_tool_func
        )
        
        # Add to MCP server
        self.mcp.add_tool(tool)
        
        logger.debug("Dynamic tool registered", extra={
            "tool_name": tool.name,
            "server_id": mcp_tool.server_id
        })
    
    async def initialize(self):
        """Initialize the router and load available tools."""
        try:
            logger.info("Initializing MCP Router")
            
            # Refresh tools from all servers
            await self._refresh_dynamic_tools()
            
            logger.info("MCP Router initialization complete")
            
        except Exception as e:
            logger.error("MCP Router initialization failed", extra={"error": str(e)})
            raise
    
    async def run_stdio(self):
        """Run the MCP server in stdio mode for Claude Desktop integration."""
        try:
            logger.info("Starting MCP Router in stdio mode")
            
            # Initialize the router
            await self.initialize()
            
            # Run the FastMCP server in stdio mode
            await self.mcp.run_stdio()
            
        except KeyboardInterrupt:
            logger.info("MCP Router stopped by user")
        except Exception as e:
            logger.error("MCP Router stdio mode failed", extra={"error": str(e)})
            raise
        finally:
            await self.cleanup()
    
    async def run_server(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the MCP server in HTTP mode."""
        try:
            logger.info("Starting MCP Router in server mode", extra={
                "host": host,
                "port": port
            })
            
            # Initialize the router
            await self.initialize()
            
            # Run the FastMCP server in HTTP mode
            await self.mcp.run_server(host=host, port=port)
            
        except KeyboardInterrupt:
            logger.info("MCP Router stopped by user")
        except Exception as e:
            logger.error("MCP Router server mode failed", extra={"error": str(e)})
            raise
        finally:
            await self.cleanup()
    
    async def handle_mcp_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Handle MCP protocol requests manually (for integration with FastAPI)."""
        try:
            if method == "initialize":
                return await self._handle_initialize(params or {})
            elif method == "initialized":
                return await self._handle_initialized(params)
            elif method == "tools/list":
                return await self._handle_tools_list(params)
            elif method == "tools/call":
                return await self._handle_tools_call(params or {})
            elif method == "resources/list":
                return await self._handle_resources_list(params)
            elif method == "resources/read":
                return await self._handle_resources_read(params or {})
            elif method == "prompts/list":
                return await self._handle_prompts_list(params)
            elif method == "prompts/get":
                return await self._handle_prompts_get(params or {})
            else:
                raise ValueError(f"Unknown method: {method}")
                
        except Exception as e:
            logger.error("MCP request handling failed", extra={
                "method": method,
                "error": str(e)
            })
            raise
    
    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request."""
        await self.initialize()
        
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"dynamicRegistration": True},
                "resources": {"dynamicRegistration": True},
                "prompts": {"dynamicRegistration": True}
            },
            "serverInfo": {
                "name": "mcp-router",
                "version": "0.1.0"
            }
        }
    
    async def _handle_initialized(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle MCP initialized notification."""
        logger.info("MCP client initialized")
        return {"acknowledged": True}
    
    async def _handle_tools_list(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle tools/list request."""
        try:
            # Get tools from FastMCP (includes default tools)
            fastmcp_tools = []
            for tool_name, tool in self.mcp.tools.items():
                fastmcp_tools.append({
                    "name": tool_name,
                    "description": tool.description or "",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                })
            
            # Get tools from connected MCP servers
            mcp_tools = await self.client_manager.list_all_tools()
            server_tools = []
            for tool in mcp_tools:
                server_tools.append(tool.to_dict())
            
            all_tools = fastmcp_tools + server_tools
            
            logger.info("Listed tools", extra={
                "fastmcp_tools": len(fastmcp_tools),
                "server_tools": len(server_tools),
                "total_tools": len(all_tools)
            })
            
            return {"tools": all_tools}
            
        except Exception as e:
            logger.error("Failed to list tools", extra={"error": str(e)})
            return {"tools": []}
    
    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise ValueError("Tool name is required")
        
        # Check if it's a default tool (handled by FastMCP)
        if tool_name in self.mcp.tools:
            result = await self.mcp.tools[tool_name].func(**arguments)
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        
        # Check if it's a server tool (format: server_id_tool_name)
        if "_" in tool_name:
            parts = tool_name.split("_", 1)
            if len(parts) == 2:
                server_id, actual_tool_name = parts
                try:
                    result = await self.client_manager.call_tool(
                        server_id, actual_tool_name, arguments
                    )
                    return result
                except Exception as e:
                    logger.error("Server tool call failed", extra={
                        "tool_name": tool_name,
                        "server_id": server_id,
                        "error": str(e)
                    })
                    raise
        
        raise ValueError(f"Tool not found: {tool_name}")
    
    async def _handle_resources_list(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle resources/list request."""
        try:
            resources = await self.client_manager.list_all_resources()
            resource_list = [resource.to_dict() for resource in resources]
            
            logger.info("Listed resources", extra={
                "resources_count": len(resource_list)
            })
            
            return {"resources": resource_list}
            
        except Exception as e:
            logger.error("Failed to list resources", extra={"error": str(e)})
            return {"resources": []}
    
    async def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")
        if not uri:
            raise ValueError("Resource URI is required")
        
        # Parse URI to determine server (format: server_id://resource_path)
        if "://" in uri:
            server_id, resource_path = uri.split("://", 1)
            try:
                result = await self.client_manager.read_resource(server_id, uri)
                return result
            except Exception as e:
                logger.error("Resource read failed", extra={
                    "uri": uri,
                    "server_id": server_id,
                    "error": str(e)
                })
                raise
        
        raise ValueError(f"Invalid resource URI format: {uri}")
    
    async def _handle_prompts_list(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle prompts/list request."""
        try:
            prompts = await self.client_manager.list_all_prompts()
            prompt_list = [prompt.to_dict() for prompt in prompts]
            
            logger.info("Listed prompts", extra={
                "prompts_count": len(prompt_list)
            })
            
            return {"prompts": prompt_list}
            
        except Exception as e:
            logger.error("Failed to list prompts", extra={"error": str(e)})
            return {"prompts": []}
    
    async def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/get request."""
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not prompt_name:
            raise ValueError("Prompt name is required")
        
        # Parse prompt name to determine server (format: server_id_prompt_name)
        if "_" in prompt_name:
            parts = prompt_name.split("_", 1)
            if len(parts) == 2:
                server_id, actual_prompt_name = parts
                try:
                    result = await self.client_manager.get_prompt(
                        server_id, actual_prompt_name, arguments
                    )
                    return result
                except Exception as e:
                    logger.error("Prompt get failed", extra={
                        "prompt_name": prompt_name,
                        "server_id": server_id,
                        "error": str(e)
                    })
                    raise
        
        raise ValueError(f"Prompt not found: {prompt_name}")
    
    async def cleanup(self):
        """Cleanup router resources."""
        try:
            logger.info("Cleaning up MCP Router")
            
            # Cleanup client manager
            await self.client_manager.cleanup_all()
            
            # Cleanup transport manager
            await self.transport_manager.cleanup_all()
            
            # Cleanup container manager sessions
            await self.container_manager.cleanup_all_sessions()
            
            logger.info("MCP Router cleanup complete")
            
        except Exception as e:
            logger.error("Error during MCP Router cleanup", extra={"error": str(e)})


# Convenience function for CLI usage
async def main():
    """Main entry point for CLI usage."""
    settings = Settings()
    router = MCPRouterServer(settings)
    
    # Determine mode from environment or CLI args
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        await router.run_server()
    else:
        await router.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())