"""Authentication and authorization module for MCP Anywhere."""

from .models import User, OAuth2Client, AuthorizationCode
from .mcp_provider import MCPAnywhereAuthProvider
from .token_verifier import TokenVerifier
from .middleware import JWTAuthMiddleware, MCPProtectionMiddleware, create_mcp_auth_middleware
from .mcp_routes import create_oauth_routes

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
