"""Manages MCP server lifecycle (start/stop) for different transports"""
import os
import sys
import subprocess
import threading
import logging
import secrets
from typing import Optional, Dict, Any, List
from datetime import datetime
from flask import Flask
from collections import deque


logger = logging.getLogger(__name__)


class MCPServerManager:
    """Manages the MCP server process lifecycle"""
    
    def __init__(self, app: Optional[Flask] = None):
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.api_key: Optional[str] = None
        self.app = app
        # Log storage - circular buffer of last 1000 lines
        self.log_buffer = deque(maxlen=1000)
        self.log_lock = threading.Lock()
        self.stdout_thread: Optional[threading.Thread] = None
        self.stderr_thread: Optional[threading.Thread] = None
    
    def _read_output_stream(self, stream, stream_name: str):
        """Read from a stream and add to log buffer"""
        try:
            for line in iter(stream.readline, ''):
                if line:
                    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    log_line = f"[{timestamp}] [{stream_name}] {line.rstrip()}"
                    
                    with self.log_lock:
                        self.log_buffer.append(log_line)
                    
                    # Determine log level based on content
                    line_upper = line.upper()
                    line_content = line.rstrip()
                    
                    # Check for log level indicators in the message
                    if any(indicator in line_upper for indicator in ['ERROR:', 'ERROR ', 'CRITICAL:', 'CRITICAL ', 'FATAL:', 'FATAL ']):
                        logger.error(f"MCP Server: {line_content}")
                    elif any(indicator in line_upper for indicator in ['WARN:', 'WARN ', 'WARNING:', 'WARNING ']):
                        logger.warning(f"MCP Server: {line_content}")
                    elif any(indicator in line_upper for indicator in ['DEBUG:', 'DEBUG ', 'TRACE:', 'TRACE ']):
                        logger.debug(f"MCP Server: {line_content}")
                    else:
                        # Default to INFO for all other messages
                        # Even if from stderr, as many programs write info to stderr
                        logger.info(f"MCP Server: {line_content}")
        except Exception as e:
            logger.error(f"Error reading {stream_name}: {e}")
        finally:
            try:
                stream.close()
            except:
                pass
    
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
            # Check if process is actually running
            if status.pid and self._is_process_running(status.pid):
                return {
                    'status': 'error',
                    'message': 'Server is already running',
                    'current': status.to_dict()
                }
            else:
                # Process crashed - clean up the status
                logger.info(f"Detected crashed server (PID {status.pid}), cleaning up status")
                update_server_status(status.transport, 'stopped', 
                                   pid=None, 
                                   started_at=None,
                                   error_message=None)
        
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
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            
            # Clear previous logs
            with self.log_lock:
                self.log_buffer.clear()
            
            # Start threads to read stdout and stderr
            self.stdout_thread = threading.Thread(
                target=self._read_output_stream,
                args=(self.process.stdout, 'STDOUT')
            )
            self.stdout_thread.daemon = True
            self.stdout_thread.start()
            
            self.stderr_thread = threading.Thread(
                target=self._read_output_stream,
                args=(self.process.stderr, 'STDERR')
            )
            self.stderr_thread.daemon = True
            self.stderr_thread.start()
            
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
                # Ensure path has trailing slash to match what FastMCP expects
                path = env['MCP_PATH']
                if not path.endswith('/'):
                    path = path + '/'
                response['connection_info'] = {
                    'type': 'http',
                    'url': f"http://{env['MCP_HOST']}:{env['MCP_PORT']}{path}",
                    'api_key': self.api_key
                }
            elif transport == 'sse':
                # Ensure path has trailing slash to match what FastMCP expects
                path = env['MCP_SSE_PATH']
                if not path.endswith('/'):
                    path = path + '/'
                response['connection_info'] = {
                    'type': 'sse',
                    'url': f"http://{env['MCP_HOST']}:{env['MCP_PORT']}{path}",
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
            
            # Wait for output threads to finish
            if self.stdout_thread:
                self.stdout_thread.join(timeout=1)
            if self.stderr_thread:
                self.stderr_thread.join(timeout=1)
            
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
        return_code = self.process.wait()
        
        # Log final status
        with self.log_lock:
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            self.log_buffer.append(f"[{timestamp}] [SYSTEM] Process exited with code {return_code}")
        
        # If we have a Flask app, use its context for database access
        if self.app:
            with self.app.app_context():
                self._update_status_on_exit(return_code)
        else:
            # Try to access without context (will work if called from Flask request)
            try:
                self._update_status_on_exit(return_code)
            except RuntimeError:
                # Log the error but don't crash
                logger.error(f"MCP server process exited with code {return_code}, but couldn't update database (no app context)")
        
        self.process = None
    
    def _update_status_on_exit(self, return_code: int):
        """Update status in database after process exit"""
        from mcp_router.models import update_server_status, get_server_status
        
        # Update status based on exit code
        if return_code != 0:
            error_msg = f"Process exited with code {return_code}"
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
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running"""
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    
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
        
        # Check if process is actually running when database says it's running
        if status.status == 'running' and status.pid:
            if not self._is_process_running(status.pid):
                # Process crashed - update status to reflect this
                result['status'] = 'crashed'
                result['actual_status'] = 'crashed'
                result['error_message'] = 'Process is not running (may have crashed)'
                logger.warning(f"MCP server PID {status.pid} is not running but database shows 'running'")
        
        # Add connection info for running servers
        if status.status == 'running':
            if status.transport == 'stdio':
                result['connection_info'] = {
                    'type': 'stdio',
                    'command': 'python -m mcp_router'
                }
            elif status.transport == 'http':
                # Ensure path has trailing slash
                path = status.path or '/mcp'
                if not path.endswith('/'):
                    path = path + '/'
                result['connection_info'] = {
                    'type': 'http',
                    'url': f"http://{status.host}:{status.port}{path}",
                    'api_key': status.api_key if status.api_key else None
                }
            elif status.transport == 'sse':
                # Ensure path has trailing slash
                path = status.path or '/sse'
                if not path.endswith('/'):
                    path = path + '/'
                result['connection_info'] = {
                    'type': 'sse',
                    'url': f"http://{status.host}:{status.port}{path}",
                    'api_key': status.api_key if status.api_key else None
                }
        
        return result

    def get_logs(self, pid: int, lines: int = 50) -> List[str]:
        """
        Get the last N lines of logs from the process output.
        
        Args:
            pid: Process ID to check
            lines: Number of lines to return (default: 50)
            
        Returns:
            List of log lines
        """
        # Check if this is our current process
        if self.process and self.process.pid == pid:
            with self.log_lock:
                # Get the last N lines from the buffer
                log_lines = list(self.log_buffer)
                if len(log_lines) > lines:
                    return log_lines[-lines:]
                return log_lines
        
        # If process doesn't match or no process, return empty
        return []


# Global instance - will be initialized with app in app.py
server_manager = None


def init_server_manager(app: Flask):
    """Initialize the global server manager with Flask app"""
    global server_manager
    server_manager = MCPServerManager(app)
    return server_manager 