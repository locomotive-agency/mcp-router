"""Authentication and authorization module for MCP Anywhere."""

from .models import User, OAuth2Client, AuthorizationCode
from .oauth_server import SimpleAuthorizationServer
from .token_verifier import TokenVerifier
from .middleware import JWTAuthMiddleware, MCPProtectionMiddleware, create_mcp_auth_middleware
from .routes import auth_routes

__all__ = [
    "User", 
    "OAuth2Client", 
    "AuthorizationCode",
    "SimpleAuthorizationServer",
    "TokenVerifier",
    "JWTAuthMiddleware",
    "MCPProtectionMiddleware", 
    "create_mcp_auth_middleware",
    "auth_routes"
]