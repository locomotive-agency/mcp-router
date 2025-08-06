"""Authentication and authorization module for MCP Anywhere."""

from .mcp_provider import MCPAnywhereAuthProvider
from .mcp_routes import create_oauth_routes
from .middleware import JWTAuthMiddleware, MCPProtectionMiddleware, create_mcp_auth_middleware
from .models import AuthorizationCode, OAuth2Client, User
from .token_verifier import TokenVerifier

__all__ = [
    "User",
    "OAuth2Client",
    "AuthorizationCode",
    "MCPAnywhereAuthProvider",
    "TokenVerifier",
    "JWTAuthMiddleware",
    "MCPProtectionMiddleware",
    "create_mcp_auth_middleware",
    "create_oauth_routes",
]
