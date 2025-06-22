"""
Transport management for MCP protocol communication.

Handles stdio, SSE, and HTTP transport mechanisms for MCP servers.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Callable, AsyncIterator
import aiohttp
from dataclasses import dataclass

from ..utils.logging import get_logger

logger = get_logger(__name__)


class TransportType(str, Enum):
    """Supported MCP transport types."""
    STDIO = "stdio"
    SSE = "sse" 
    HTTP = "http"


@dataclass
class TransportConfig:
    """Configuration for MCP transport."""
    type: TransportType
    endpoint: Optional[str] = None  # For HTTP/SSE
    timeout: int = 30
    retry_attempts: int = 3
    headers: Dict[str, str] = None
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


class MCPTransport(ABC):
    """Abstract base class for MCP transport mechanisms."""
    
    def __init__(self, config: TransportConfig):
        self.config = config
        self.is_connected = False
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the MCP server."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the MCP server."""
        pass
    
    @abstractmethod
    async def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send an MCP request and return the response."""
        pass
    
    @abstractmethod
    async def send_notification(self, method: str, params: Dict[str, Any] = None) -> None:
        """Send an MCP notification (no response expected)."""
        pass


class StdioTransport(MCPTransport):
    """MCP transport over stdio (process communication)."""
    
    def __init__(self, config: TransportConfig, process: asyncio.subprocess.Process):
        super().__init__(config)
        self.process = process
        self.request_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> bool:
        """Start reading from the process stdout."""
        if self.is_connected:
            return True
        
        try:
            self._read_task = asyncio.create_task(self._read_responses())
            self.is_connected = True
            logger.info("STDIO transport connected")
            return True
        except Exception as e:
            logger.error("Failed to connect STDIO transport", extra={"error": str(e)})
            return False
    
    async def disconnect(self) -> None:
        """Stop reading and terminate the process."""
        if not self.is_connected:
            return
        
        self.is_connected = False
        
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        
        # Cancel any pending requests
        for future in self.pending_requests.values():
            future.cancel()
        self.pending_requests.clear()
        
        logger.info("STDIO transport disconnected")
    
    async def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send JSON-RPC request over stdin."""
        if not self.is_connected:
            raise RuntimeError("Transport not connected")
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        if params:
            request["params"] = params
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[self.request_id] = future
        
        try:
            # Send request
            request_data = json.dumps(request) + "\n"
            self.process.stdin.write(request_data.encode())
            await self.process.stdin.drain()
            
            # Wait for response
            response = await asyncio.wait_for(future, timeout=self.config.timeout)
            return response
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(self.request_id, None)
            raise RuntimeError(f"Request {method} timed out")
        except Exception as e:
            self.pending_requests.pop(self.request_id, None)
            raise RuntimeError(f"Request {method} failed: {e}")
    
    async def send_notification(self, method: str, params: Dict[str, Any] = None) -> None:
        """Send JSON-RPC notification over stdin."""
        if not self.is_connected:
            raise RuntimeError("Transport not connected")
        
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params:
            notification["params"] = params
        
        try:
            notification_data = json.dumps(notification) + "\n"
            self.process.stdin.write(notification_data.encode())
            await self.process.stdin.drain()
        except Exception as e:
            raise RuntimeError(f"Notification {method} failed: {e}")
    
    async def _read_responses(self) -> None:
        """Read responses from process stdout."""
        try:
            while self.is_connected:
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                try:
                    response = json.loads(line.decode().strip())
                    await self._handle_response(response)
                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON received", extra={"line": line.decode(), "error": str(e)})
                except Exception as e:
                    logger.error("Error handling response", extra={"error": str(e)})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error reading responses", extra={"error": str(e)})
    
    async def _handle_response(self, response: Dict[str, Any]) -> None:
        """Handle incoming response or notification."""
        if "id" in response:
            # This is a response to a request
            request_id = response["id"]
            future = self.pending_requests.pop(request_id, None)
            if future and not future.cancelled():
                if "error" in response:
                    future.set_exception(RuntimeError(response["error"]))
                else:
                    future.set_result(response.get("result", {}))
        else:
            # This is a notification from the server
            logger.debug("Received notification", extra={"method": response.get("method")})


class HTTPTransport(MCPTransport):
    """MCP transport over HTTP."""
    
    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_id = 0
    
    async def connect(self) -> bool:
        """Create HTTP session."""
        if self.is_connected:
            return True
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self.config.headers
            )
            self.is_connected = True
            logger.info("HTTP transport connected", extra={"endpoint": self.config.endpoint})
            return True
        except Exception as e:
            logger.error("Failed to connect HTTP transport", extra={"error": str(e)})
            return False
    
    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
        self.is_connected = False
        logger.info("HTTP transport disconnected")
    
    async def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send JSON-RPC request over HTTP."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Transport not connected")
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        if params:
            request["params"] = params
        
        try:
            async with self.session.post(
                self.config.endpoint,
                json=request,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
                result = await response.json()
                
                if "error" in result:
                    raise RuntimeError(result["error"])
                
                return result.get("result", {})
                
        except aiohttp.ClientError as e:
            raise RuntimeError(f"HTTP request {method} failed: {e}")
    
    async def send_notification(self, method: str, params: Dict[str, Any] = None) -> None:
        """Send JSON-RPC notification over HTTP."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Transport not connected")
        
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params:
            notification["params"] = params
        
        try:
            async with self.session.post(
                self.config.endpoint,
                json=notification,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
        except aiohttp.ClientError as e:
            raise RuntimeError(f"HTTP notification {method} failed: {e}")


class SSETransport(MCPTransport):
    """MCP transport over Server-Sent Events."""
    
    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self._sse_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> bool:
        """Connect to SSE endpoint."""
        if self.is_connected:
            return True
        
        try:
            timeout = aiohttp.ClientTimeout(total=None)  # SSE connections are long-lived
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self.config.headers
            )
            
            # Start SSE listening task
            self._sse_task = asyncio.create_task(self._listen_sse())
            self.is_connected = True
            logger.info("SSE transport connected", extra={"endpoint": self.config.endpoint})
            return True
        except Exception as e:
            logger.error("Failed to connect SSE transport", extra={"error": str(e)})
            return False
    
    async def disconnect(self) -> None:
        """Close SSE connection."""
        self.is_connected = False
        
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
            self.session = None
        
        # Cancel any pending requests
        for future in self.pending_requests.values():
            future.cancel()
        self.pending_requests.clear()
        
        logger.info("SSE transport disconnected")
    
    async def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send request over SSE (using HTTP POST for requests)."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Transport not connected")
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        if params:
            request["params"] = params
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[self.request_id] = future
        
        try:
            # Send request via HTTP POST
            async with self.session.post(
                self.config.endpoint,
                json=request,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
            
            # Wait for response via SSE
            result = await asyncio.wait_for(future, timeout=self.config.timeout)
            return result
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(self.request_id, None)
            raise RuntimeError(f"SSE request {method} timed out")
        except Exception as e:
            self.pending_requests.pop(self.request_id, None)
            raise RuntimeError(f"SSE request {method} failed: {e}")
    
    async def send_notification(self, method: str, params: Dict[str, Any] = None) -> None:
        """Send notification over SSE (using HTTP POST)."""
        if not self.is_connected or not self.session:
            raise RuntimeError("Transport not connected")
        
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params:
            notification["params"] = params
        
        try:
            async with self.session.post(
                self.config.endpoint,
                json=notification,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
        except aiohttp.ClientError as e:
            raise RuntimeError(f"SSE notification {method} failed: {e}")
    
    async def _listen_sse(self) -> None:
        """Listen for SSE events."""
        try:
            async with self.session.get(
                f"{self.config.endpoint}/events",
                headers={"Accept": "text/event-stream"}
            ) as response:
                response.raise_for_status()
                
                async for line in response.content:
                    if not self.is_connected:
                        break
                    
                    line_str = line.decode().strip()
                    if line_str.startswith("data: "):
                        try:
                            data = json.loads(line_str[6:])  # Remove "data: " prefix
                            await self._handle_sse_message(data)
                        except json.JSONDecodeError:
                            logger.warning("Invalid SSE JSON", extra={"line": line_str})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("SSE listening error", extra={"error": str(e)})
    
    async def _handle_sse_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming SSE message."""
        if "id" in message:
            # This is a response to a request
            request_id = message["id"]
            future = self.pending_requests.pop(request_id, None)
            if future and not future.cancelled():
                if "error" in message:
                    future.set_exception(RuntimeError(message["error"]))
                else:
                    future.set_result(message.get("result", {}))
        else:
            # This is a notification from the server
            logger.debug("Received SSE notification", extra={"method": message.get("method")})


class TransportManager:
    """Manages MCP transport connections for different servers."""
    
    def __init__(self):
        self.transports: Dict[str, MCPTransport] = {}
    
    async def create_transport(
        self,
        server_id: str,
        config: TransportConfig,
        process: Optional[asyncio.subprocess.Process] = None
    ) -> MCPTransport:
        """Create and connect a transport for the given server."""
        
        # Clean up existing transport if it exists
        await self.remove_transport(server_id)
        
        # Create new transport based on type
        if config.type == TransportType.STDIO:
            if not process:
                raise ValueError("Process required for STDIO transport")
            transport = StdioTransport(config, process)
        elif config.type == TransportType.HTTP:
            if not config.endpoint:
                raise ValueError("Endpoint required for HTTP transport")
            transport = HTTPTransport(config)
        elif config.type == TransportType.SSE:
            if not config.endpoint:
                raise ValueError("Endpoint required for SSE transport")
            transport = SSETransport(config)
        else:
            raise ValueError(f"Unsupported transport type: {config.type}")
        
        # Connect the transport
        if await transport.connect():
            self.transports[server_id] = transport
            logger.info("Transport created", extra={
                "server_id": server_id,
                "type": config.type.value
            })
            return transport
        else:
            raise RuntimeError(f"Failed to connect {config.type} transport for server {server_id}")
    
    async def get_transport(self, server_id: str) -> Optional[MCPTransport]:
        """Get existing transport for server."""
        return self.transports.get(server_id)
    
    async def remove_transport(self, server_id: str) -> None:
        """Remove and disconnect transport for server."""
        transport = self.transports.pop(server_id, None)
        if transport:
            await transport.disconnect()
            logger.info("Transport removed", extra={"server_id": server_id})
    
    async def cleanup_all(self) -> None:
        """Disconnect and remove all transports."""
        server_ids = list(self.transports.keys())
        for server_id in server_ids:
            await self.remove_transport(server_id)
        logger.info("All transports cleaned up")