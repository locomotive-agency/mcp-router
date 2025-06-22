"""
MCP client management for connecting to individual MCP servers.

Handles the lifecycle of MCP client connections, including initialization,
tool discovery, and request routing.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..models.database import MCPServer, get_database
from ..services.container_manager import ContainerManager, ContainerConfig
from .transport import TransportManager, TransportConfig, TransportType
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MCPCapabilities:
    """MCP server capabilities."""
    tools: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    prompts: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def has_tools(self) -> bool:
        return bool(self.tools)
    
    @property
    def has_resources(self) -> bool:
        return bool(self.resources)
    
    @property
    def has_prompts(self) -> bool:
        return bool(self.prompts)


@dataclass
class MCPTool:
    """Represents an MCP tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema
        }


@dataclass
class MCPResource:
    """Represents an MCP resource."""
    uri: str
    name: str
    description: Optional[str]
    mime_type: Optional[str]
    server_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "uri": self.uri,
            "name": self.name
        }
        if self.description:
            result["description"] = self.description
        if self.mime_type:
            result["mimeType"] = self.mime_type
        return result


@dataclass
class MCPPrompt:
    """Represents an MCP prompt."""
    name: str
    description: Optional[str]
    arguments: List[Dict[str, Any]]
    server_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "arguments": self.arguments
        }
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class MCPClient:
    """Represents a connection to an MCP server."""
    server_id: str
    server: MCPServer
    container_session_id: Optional[str] = None
    process: Optional[asyncio.subprocess.Process] = None
    is_initialized: bool = False
    capabilities: MCPCapabilities = field(default_factory=MCPCapabilities)
    tools: Dict[str, MCPTool] = field(default_factory=dict)
    resources: Dict[str, MCPResource] = field(default_factory=dict)
    prompts: Dict[str, MCPPrompt] = field(default_factory=dict)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
    
    @property
    def is_idle(self) -> bool:
        """Check if client has been idle for more than 5 minutes."""
        return datetime.utcnow() - self.last_activity > timedelta(minutes=5)


class MCPClientManager:
    """Manages MCP client connections to servers."""
    
    def __init__(self, container_manager: ContainerManager, transport_manager: TransportManager):
        self.container_manager = container_manager
        self.transport_manager = transport_manager
        self.clients: Dict[str, MCPClient] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Start background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_idle_clients())
    
    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def get_or_create_client(self, server_id: str) -> MCPClient:
        """Get existing client or create a new one for the server."""
        # Check if we have an active client
        if server_id in self.clients:
            client = self.clients[server_id]
            client.update_activity()
            return client
        
        # Get server configuration
        db = get_database()
        async with db.session() as session:
            server = await session.get(MCPServer, server_id)
            if not server:
                raise ValueError(f"Server {server_id} not found")
            if not server.is_active:
                raise ValueError(f"Server {server_id} is not active")
        
        # Create new client
        client = await self._create_client(server)
        self.clients[server_id] = client
        
        logger.info("MCP client created", extra={
            "server_id": server_id,
            "server_name": server.name
        })
        
        return client
    
    async def _create_client(self, server: MCPServer) -> MCPClient:
        """Create a new MCP client for the server."""
        client = MCPClient(server_id=server.id, server=server)
        
        try:
            # Start container session
            container_config = ContainerConfig(
                memory_limit="512m",
                cpu_limit=1.0,
                timeout=300,
                enable_networking=True
            )
            
            session_id = await self.container_manager.create_session(server, container_config)
            await self.container_manager.start_session(session_id)
            client.container_session_id = session_id
            
            # Install dependencies if needed
            if server.runtime_type == "python" and server.install_command:
                await self.container_manager.execute_command(session_id, server.install_command)
            
            # Start the MCP server process
            if server.transport_type == "stdio":
                process = await self._start_stdio_server(session_id, server)
                client.process = process
                
                # Create transport
                transport_config = TransportConfig(type=TransportType.STDIO)
                await self.transport_manager.create_transport(server.id, transport_config, process)
            
            elif server.transport_type in ["http", "sse"]:
                # Start HTTP/SSE server
                await self._start_http_server(session_id, server)
                
                # Create transport
                transport_type = TransportType.HTTP if server.transport_type == "http" else TransportType.SSE
                endpoint = server.transport_config.get("endpoint", "http://localhost:8080")
                transport_config = TransportConfig(
                    type=transport_type,
                    endpoint=endpoint,
                    headers=server.transport_config.get("headers", {})
                )
                await self.transport_manager.create_transport(server.id, transport_config)
            
            # Initialize the MCP connection
            await self._initialize_client(client)
            
            # Discover capabilities
            await self._discover_capabilities(client)
            
            return client
            
        except Exception as e:
            # Cleanup on failure
            await self._cleanup_client(client)
            raise RuntimeError(f"Failed to create MCP client for {server.name}: {e}")
    
    async def _start_stdio_server(self, session_id: str, server: MCPServer) -> asyncio.subprocess.Process:
        """Start MCP server process in container for stdio transport."""
        
        # Prepare environment variables
        env_dict = {var.key: var.value for var in server.env_variables if var.value}
        
        # Create command to run the MCP server
        start_command = server.start_command
        
        # If using uvx or npx, wrap in the appropriate command
        if server.runtime_type == "uvx":
            start_command = f"uvx {start_command}"
        elif server.runtime_type == "npx":
            start_command = f"npx {start_command}"
        
        # Execute the server start command in the container
        # For stdio, we need to start the process and keep it running
        result = await self.container_manager.execute_command(
            session_id, 
            f"bash -c '{start_command}' &"
        )
        
        # Note: This is a simplified approach. In reality, we'd need to properly
        # manage the subprocess within the container. For now, we'll create a mock process.
        process = await asyncio.create_subprocess_exec(
            "python", "-c", 
            """
import sys
import json
import asyncio

async def main():
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            
            # Echo back for testing
            request = json.loads(line.strip())
            if 'id' in request:
                response = {
                    'jsonrpc': '2.0',
                    'id': request['id'],
                    'result': {'status': 'ok', 'method': request.get('method')}
                }
                print(json.dumps(response), flush=True)
        except Exception as e:
            print(json.dumps({'error': str(e)}), file=sys.stderr, flush=True)

asyncio.run(main())
            """,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        return process
    
    async def _start_http_server(self, session_id: str, server: MCPServer) -> None:
        """Start MCP server in container for HTTP/SSE transport."""
        
        # Prepare environment variables
        env_dict = {var.key: var.value for var in server.env_variables if var.value}
        
        # Create command to run the MCP server
        start_command = server.start_command
        
        # If using uvx or npx, wrap in the appropriate command
        if server.runtime_type == "uvx":
            start_command = f"uvx {start_command}"
        elif server.runtime_type == "npx":
            start_command = f"npx {start_command}"
        
        # Start the server in background
        result = await self.container_manager.execute_command(
            session_id,
            f"nohup {start_command} > server.log 2>&1 &"
        )
        
        # Wait a moment for server to start
        await asyncio.sleep(2)
        
        logger.info("HTTP/SSE server started", extra={
            "server_id": server.id,
            "session_id": session_id
        })
    
    async def _initialize_client(self, client: MCPClient) -> None:
        """Initialize the MCP client connection."""
        transport = await self.transport_manager.get_transport(client.server_id)
        if not transport:
            raise RuntimeError("Transport not available")
        
        try:
            # Send initialize request
            init_response = await transport.send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
                "clientInfo": {
                    "name": "mcp-router",
                    "version": "0.1.0"
                }
            })
            
            # Parse server capabilities
            server_caps = init_response.get("capabilities", {})
            client.capabilities = MCPCapabilities(
                tools=server_caps.get("tools", {}),
                resources=server_caps.get("resources", {}),
                prompts=server_caps.get("prompts", {})
            )
            
            # Send initialized notification
            await transport.send_notification("initialized", {})
            
            client.is_initialized = True
            client.update_activity()
            
            logger.info("MCP client initialized", extra={
                "server_id": client.server_id,
                "capabilities": {
                    "tools": client.capabilities.has_tools,
                    "resources": client.capabilities.has_resources,
                    "prompts": client.capabilities.has_prompts
                }
            })
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize MCP client: {e}")
    
    async def _discover_capabilities(self, client: MCPClient) -> None:
        """Discover tools, resources, and prompts from the server."""
        transport = await self.transport_manager.get_transport(client.server_id)
        if not transport:
            return
        
        try:
            # Discover tools
            if client.capabilities.has_tools:
                tools_response = await transport.send_request("tools/list", {})
                for tool_data in tools_response.get("tools", []):
                    tool = MCPTool(
                        name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("inputSchema", {}),
                        server_id=client.server_id
                    )
                    client.tools[tool.name] = tool
            
            # Discover resources
            if client.capabilities.has_resources:
                resources_response = await transport.send_request("resources/list", {})
                for resource_data in resources_response.get("resources", []):
                    resource = MCPResource(
                        uri=resource_data["uri"],
                        name=resource_data["name"],
                        description=resource_data.get("description"),
                        mime_type=resource_data.get("mimeType"),
                        server_id=client.server_id
                    )
                    client.resources[resource.uri] = resource
            
            # Discover prompts
            if client.capabilities.has_prompts:
                prompts_response = await transport.send_request("prompts/list", {})
                for prompt_data in prompts_response.get("prompts", []):
                    prompt = MCPPrompt(
                        name=prompt_data["name"],
                        description=prompt_data.get("description"),
                        arguments=prompt_data.get("arguments", []),
                        server_id=client.server_id
                    )
                    client.prompts[prompt.name] = prompt
            
            client.update_activity()
            
            logger.info("MCP capabilities discovered", extra={
                "server_id": client.server_id,
                "tools_count": len(client.tools),
                "resources_count": len(client.resources),
                "prompts_count": len(client.prompts)
            })
            
        except Exception as e:
            logger.warning("Failed to discover some capabilities", extra={
                "server_id": client.server_id,
                "error": str(e)
            })
    
    async def call_tool(
        self, 
        server_id: str, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool on the specified server."""
        client = await self.get_or_create_client(server_id)
        
        if tool_name not in client.tools:
            raise ValueError(f"Tool {tool_name} not found on server {server_id}")
        
        transport = await self.transport_manager.get_transport(server_id)
        if not transport:
            raise RuntimeError("Transport not available")
        
        try:
            response = await transport.send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            
            client.update_activity()
            return response
            
        except Exception as e:
            raise RuntimeError(f"Failed to call tool {tool_name}: {e}")
    
    async def read_resource(self, server_id: str, uri: str) -> Dict[str, Any]:
        """Read a resource from the specified server."""
        client = await self.get_or_create_client(server_id)
        
        if uri not in client.resources:
            raise ValueError(f"Resource {uri} not found on server {server_id}")
        
        transport = await self.transport_manager.get_transport(server_id)
        if not transport:
            raise RuntimeError("Transport not available")
        
        try:
            response = await transport.send_request("resources/read", {
                "uri": uri
            })
            
            client.update_activity()
            return response
            
        except Exception as e:
            raise RuntimeError(f"Failed to read resource {uri}: {e}")
    
    async def get_prompt(
        self, 
        server_id: str, 
        prompt_name: str, 
        arguments: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Get a prompt from the specified server."""
        client = await self.get_or_create_client(server_id)
        
        if prompt_name not in client.prompts:
            raise ValueError(f"Prompt {prompt_name} not found on server {server_id}")
        
        transport = await self.transport_manager.get_transport(server_id)
        if not transport:
            raise RuntimeError("Transport not available")
        
        try:
            params = {"name": prompt_name}
            if arguments:
                params["arguments"] = arguments
            
            response = await transport.send_request("prompts/get", params)
            
            client.update_activity()
            return response
            
        except Exception as e:
            raise RuntimeError(f"Failed to get prompt {prompt_name}: {e}")
    
    async def list_all_tools(self) -> List[MCPTool]:
        """List all available tools from all servers."""
        db = get_database()
        tools = []
        
        async with db.session() as session:
            servers = await session.query(MCPServer).filter(MCPServer.is_active == True).all()
            
            for server in servers:
                try:
                    client = await self.get_or_create_client(server.id)
                    tools.extend(client.tools.values())
                except Exception as e:
                    logger.warning("Failed to get tools from server", extra={
                        "server_id": server.id,
                        "error": str(e)
                    })
        
        return tools
    
    async def list_all_resources(self) -> List[MCPResource]:
        """List all available resources from all servers."""
        db = get_database()
        resources = []
        
        async with db.session() as session:
            servers = await session.query(MCPServer).filter(MCPServer.is_active == True).all()
            
            for server in servers:
                try:
                    client = await self.get_or_create_client(server.id)
                    resources.extend(client.resources.values())
                except Exception as e:
                    logger.warning("Failed to get resources from server", extra={
                        "server_id": server.id,
                        "error": str(e)
                    })
        
        return resources
    
    async def list_all_prompts(self) -> List[MCPPrompt]:
        """List all available prompts from all servers."""
        db = get_database()
        prompts = []
        
        async with db.session() as session:
            servers = await session.query(MCPServer).filter(MCPServer.is_active == True).all()
            
            for server in servers:
                try:
                    client = await self.get_or_create_client(server.id)
                    prompts.extend(client.prompts.values())
                except Exception as e:
                    logger.warning("Failed to get prompts from server", extra={
                        "server_id": server.id,
                        "error": str(e)
                    })
        
        return prompts
    
    async def disconnect_client(self, server_id: str) -> None:
        """Disconnect and cleanup a specific client."""
        client = self.clients.pop(server_id, None)
        if client:
            await self._cleanup_client(client)
            logger.info("MCP client disconnected", extra={"server_id": server_id})
    
    async def _cleanup_client(self, client: MCPClient) -> None:
        """Cleanup client resources."""
        try:
            # Remove transport
            await self.transport_manager.remove_transport(client.server_id)
            
            # Terminate process if exists
            if client.process:
                try:
                    client.process.terminate()
                    await asyncio.wait_for(client.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    client.process.kill()
                    await client.process.wait()
            
            # Stop container session
            if client.container_session_id:
                await self.container_manager.stop_session(client.container_session_id)
            
        except Exception as e:
            logger.error("Error during client cleanup", extra={
                "server_id": client.server_id,
                "error": str(e)
            })
    
    async def _cleanup_idle_clients(self) -> None:
        """Background task to cleanup idle clients."""
        try:
            while True:
                await asyncio.sleep(60)  # Check every minute
                
                idle_clients = [
                    server_id for server_id, client in self.clients.items()
                    if client.is_idle
                ]
                
                for server_id in idle_clients:
                    logger.info("Cleaning up idle client", extra={"server_id": server_id})
                    await self.disconnect_client(server_id)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in cleanup task", extra={"error": str(e)})
    
    async def cleanup_all(self) -> None:
        """Cleanup all clients and stop background tasks."""
        await self.stop_cleanup_task()
        
        client_ids = list(self.clients.keys())
        for client_id in client_ids:
            await self.disconnect_client(client_id)
        
        logger.info("All MCP clients cleaned up")