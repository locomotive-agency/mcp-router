"""Manages MCP server lifecycle (start/stop) for different transports"""
import os
import sys
import subprocess
import threading
import logging
import secrets
from typing import Optional, Dict, Any
from datetime import datetime
from flask import Flask

logger = logging.getLogger(__name__)


class MCPServerManager:
    """Manages the MCP server process lifecycle"""
    
    def __init__(self, app: Optional[Flask] = None):
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.api_key: Optional[str] = None
        self.app = app
    
    def start_server(self, transport: str = 'stdio', **kwargs) -> Dict[str, Any]:
        """
        Start the MCP server with specified transport
        
        Args:
            transport: Transport type (stdio, http, sse)
            **kwargs: Additional parameters (host, port, path for HTTP/SSE)
            
        Returns:
            Dict with status and connection info
        """
        # Import here to avoid circular imports
        from mcp_router.models import update_server_status, get_server_status
        
        # Check if already running
        status = get_server_status()
        if status and status.status == 'running':
            return {
                'status': 'error',
                'message': 'Server is already running',
                'current': status.to_dict()
            }
        
        try:
            # Prepare environment
            env = os.environ.copy()
            env['MCP_TRANSPORT'] = transport
            
            # Set transport-specific configuration
            if transport in ['http', 'sse']:
                # Generate API key if not provided
                self.api_key = kwargs.get('api_key') or secrets.token_urlsafe(32)
                env['MCP_API_KEY'] = self.api_key
                
                # Set host/port/path
                env['MCP_HOST'] = kwargs.get('host', '127.0.0.1')
                env['MCP_PORT'] = str(kwargs.get('port', 8001))
                
                if transport == 'http':
                    env['MCP_PATH'] = kwargs.get('path', '/mcp')
                else:  # sse
                    env['MCP_SSE_PATH'] = kwargs.get('path', '/sse')
            
            # Start the server process
            cmd = [sys.executable, '-m', 'mcp_router']
            self.process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Update status in database
            status_kwargs = {
                'pid': self.process.pid,
                'started_at': datetime.utcnow(),
                'error_message': None
            }
            
            if transport in ['http', 'sse']:
                status_kwargs.update({
                    'host': env['MCP_HOST'],
                    'port': int(env['MCP_PORT']),
                    'path': env.get('MCP_PATH') or env.get('MCP_SSE_PATH'),
                    'api_key': self.api_key
                })
            
            update_server_status(transport, 'running', **status_kwargs)
            
            # Start monitoring thread
            self.thread = threading.Thread(target=self._monitor_process)
            self.thread.daemon = True
            self.thread.start()
            
            # Prepare response
            response = {
                'status': 'success',
                'message': f'Server started with {transport} transport',
                'pid': self.process.pid,
                'transport': transport
            }
            
            if transport == 'stdio':
                response['connection_info'] = {
                    'type': 'stdio',
                    'command': 'python -m mcp_router'
                }
            elif transport == 'http':
                response['connection_info'] = {
                    'type': 'http',
                    'url': f"http://{env['MCP_HOST']}:{env['MCP_PORT']}{env['MCP_PATH']}",
                    'api_key': self.api_key
                }
            elif transport == 'sse':
                response['connection_info'] = {
                    'type': 'sse',
                    'url': f"http://{env['MCP_HOST']}:{env['MCP_PORT']}{env['MCP_SSE_PATH']}",
                    'api_key': self.api_key
                }
            
            logger.info(f"Started MCP server with {transport} transport (PID: {self.process.pid})")
            return response
            
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            update_server_status(transport, 'error', error_message=str(e))
            return {
                'status': 'error',
                'message': f'Failed to start server: {str(e)}'
            }
    
    def stop_server(self) -> Dict[str, Any]:
        """Stop the running MCP server"""
        from mcp_router.models import update_server_status, get_server_status
        
        status = get_server_status()
        if not status or status.status != 'running':
            return {
                'status': 'error',
                'message': 'No server is running'
            }
        
        try:
            if self.process:
                # Terminate the process
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self.process.kill()
                    self.process.wait()
                
                self.process = None
            
            # Update status
            update_server_status(status.transport, 'stopped', 
                               pid=None, 
                               started_at=None,
                               error_message=None)
            
            logger.info("Stopped MCP server")
            return {
                'status': 'success',
                'message': 'Server stopped successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to stop MCP server: {e}")
            return {
                'status': 'error',
                'message': f'Failed to stop server: {str(e)}'
            }
    
    def _monitor_process(self):
        """Monitor the server process and update status on exit"""
        if not self.process:
            return
        
        # Wait for process to complete
        stdout, stderr = self.process.communicate()
        
        # If we have a Flask app, use its context for database access
        if self.app:
            with self.app.app_context():
                self._update_status_on_exit(stderr)
        else:
            # Try to access without context (will work if called from Flask request)
            try:
                self._update_status_on_exit(stderr)
            except RuntimeError:
                # Log the error but don't crash
                logger.error(f"MCP server process exited with code {self.process.returncode}, but couldn't update database (no app context)")
        
        self.process = None
    
    def _update_status_on_exit(self, stderr: str):
        """Update status in database after process exit"""
        from mcp_router.models import update_server_status, get_server_status
        
        # Update status based on exit code
        if self.process.returncode != 0:
            error_msg = stderr or f"Process exited with code {self.process.returncode}"
            logger.error(f"MCP server crashed: {error_msg}")
            
            status = get_server_status()
            if status:
                update_server_status(status.transport, 'error', 
                                   pid=None,
                                   error_message=error_msg)
        else:
            # Normal exit
            status = get_server_status()
            if status:
                update_server_status(status.transport, 'stopped', 
                                   pid=None,
                                   started_at=None)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current server status"""
        from mcp_router.models import get_server_status
        
        status = get_server_status()
        if not status:
            return {
                'status': 'stopped',
                'transport': None
            }
        
        result = status.to_dict()
        
        # Add connection info for running servers
        if status.status == 'running':
            if status.transport == 'stdio':
                result['connection_info'] = {
                    'type': 'stdio',
                    'command': 'python -m mcp_router'
                }
            elif status.transport == 'http':
                result['connection_info'] = {
                    'type': 'http',
                    'url': f"http://{status.host}:{status.port}{status.path}",
                    'api_key': status.api_key if status.api_key else None
                }
            elif status.transport == 'sse':
                result['connection_info'] = {
                    'type': 'sse',
                    'url': f"http://{status.host}:{status.port}{status.path}",
                    'api_key': status.api_key if status.api_key else None
                }
        
        return result


# Global instance - will be initialized with app in app.py
server_manager = None


def init_server_manager(app: Flask):
    """Initialize the global server manager with Flask app"""
    global server_manager
    server_manager = MCPServerManager(app)
    return server_manager 