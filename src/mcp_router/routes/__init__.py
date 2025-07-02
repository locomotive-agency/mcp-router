"""Route modules for MCP Router"""

from .servers import servers_bp
from .mcp import mcp_bp
from .config import config_bp
from .errors import register_error_handlers

__all__ = ["servers_bp", "mcp_bp", "config_bp", "register_error_handlers"]
