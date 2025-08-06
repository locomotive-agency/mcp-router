"""HTTP transport module for running MCP Anywhere as a web server."""

import uvicorn
from typing import Optional

from mcp_anywhere.web.app import create_app
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


async def run_http_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    log_level: str = "info"
) -> None:
    """
    Run the MCP Anywhere as an HTTP web server using uvicorn.
    
    Args:
        host: Host address to bind to
        port: Port number to bind to
        log_level: Logging level for uvicorn
    """
    logger.info(f"Starting HTTP server on {host}:{port}")
    
    try:
        # Create the Starlette application with http transport mode
        app = create_app(transport_mode="http")
        
        # Create uvicorn server configuration
        config = uvicorn.Config(
            app, 
            host=host, 
            port=port, 
            log_level=log_level
        )
        
        # Create and run the server
        server = uvicorn.Server(config)
        await server.serve()
        
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")
        raise