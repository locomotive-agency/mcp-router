"""Authentication and authorization module for MCP Anywhere."""

# Avoid circular imports by not importing everything at module level
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
