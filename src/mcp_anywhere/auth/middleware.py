"""JWT Authentication Middleware for Starlette applications."""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from mcp_anywhere.auth.token_verifier import TokenVerifier
from mcp_anywhere.core.base_middleware import BasePathProtectionMiddleware
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class JWTAuthMiddleware(BasePathProtectionMiddleware):
    """JWT Authentication Middleware for protecting API endpoints."""

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str | None = None,
        protected_paths: list[str] = None,
        required_scopes: list[str] = None,
        skip_paths: list[str] = None,
    ):
        """Initialize JWT authentication middleware.

        Args:
            app: ASGI application
            secret_key: JWT secret key for token verification
            protected_paths: List of path patterns that require authentication
            required_scopes: List of scopes required for access
            skip_paths: List of path patterns to skip authentication
        """
        # Initialize base class with path patterns
        super().__init__(
            app=app,
            protected_paths=protected_paths or ["/api/*"],
            skip_paths=skip_paths or ["/auth/*", "/static/*"],
        )

        self.token_verifier = TokenVerifier(secret_key=secret_key)
        self.required_scopes = required_scopes or []

        logger.info(
            f"JWT Auth Middleware initialized with protected paths: {self.protected_paths}"
        )

    def _create_auth_error_response(
        self, error: str, description: str = None, status_code: int = 401
    ) -> JSONResponse:
        """Create standardized authentication error response.

        Args:
            error: Error code
            description: Error description
            status_code: HTTP status code

        Returns:
            JSONResponse with error details
        """
        error_data = {"error": error}
        if description:
            error_data["error_description"] = description

        return JSONResponse(error_data, status_code=status_code)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request through JWT authentication middleware.

        Args:
            request: Starlette request object
            call_next: Next middleware/application in chain

        Returns:
            Response from next middleware or authentication error
        """
        path = request.url.path

        # Check if this path needs protection
        if not self._should_protect_path(path):
            # Path is not protected, continue to next middleware
            return await call_next(request)

        # Path is protected, check for valid JWT token
        authorization_header = request.headers.get("Authorization")

        if not authorization_header:
            logger.warning(f"Missing Authorization header for protected path: {path}")
            return self._create_auth_error_response(
                "invalid_token", "Missing Authorization header"
            )

        # Verify the token
        token_payload = self.token_verifier.verify_bearer_token(authorization_header)

        if not token_payload:
            logger.warning(f"Invalid or expired token for path: {path}")
            return self._create_auth_error_response(
                "invalid_token", "Invalid or expired token"
            )

        # Check required scopes if specified
        if self.required_scopes:
            if not self.token_verifier.has_all_scopes(
                token_payload, self.required_scopes
            ):
                token_scopes = token_payload.get("scope", "").split()
                logger.warning(
                    f"Insufficient scope for path: {path}. "
                    f"Required: {self.required_scopes}, Token: {token_scopes}"
                )
                return self._create_auth_error_response(
                    "insufficient_scope",
                    f"Required scopes: {', '.join(self.required_scopes)}",
                    status_code=403,
                )

        # Add user information to request state
        request.state.user = {
            "id": token_payload.get("sub"),
            "username": token_payload.get("username"),
            "scopes": token_payload.get("scope", "").split(),
            "client_id": token_payload.get("client_id"),
            "token_payload": token_payload,
        }

        logger.debug(
            f"Authenticated request for user: {token_payload.get('username')} on path: {path}"
        )

        # Continue to next middleware/application
        return await call_next(request)


class MCPProtectionMiddleware(JWTAuthMiddleware):
    """Specialized JWT middleware for protecting MCP endpoints."""

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str | None = None,
        mcp_path: str = "/mcp",
        required_scopes: list[str] = None,
    ):
        """Initialize MCP protection middleware.

        Args:
            app: ASGI application
            secret_key: JWT secret key for token verification
            mcp_path: Base path for MCP endpoints
            required_scopes: List of scopes required for MCP access
        """
        # Protect all MCP endpoints
        protected_paths = [f"{mcp_path}/*"]

        # Skip auth endpoints and other public paths
        # (Web UI routes are handled by SessionAuthMiddleware)
        skip_paths = [
            "/auth/*",
            "/static/*",
            "/favicon.ico",
            "/",
            "/servers/*",
            "/health",
        ]

        # Default MCP scopes if not specified
        if not required_scopes:
            required_scopes = ["read"]

        super().__init__(
            app=app,
            secret_key=secret_key,
            protected_paths=protected_paths,
            required_scopes=required_scopes or ["read"],
            skip_paths=skip_paths,
        )

        logger.info(f"MCP Protection Middleware initialized for path: {mcp_path}")


def create_mcp_auth_middleware(
    secret_key: str | None = None,
    mcp_path: str = "/mcp",
    required_scopes: list[str] = None,
) -> type:
    """Factory function to create MCP authentication middleware class.

    Args:
        secret_key: JWT secret key
        mcp_path: Base path for MCP endpoints
        required_scopes: Required scopes for MCP access

    Returns:
        Middleware class configured for MCP protection
    """

    def middleware_factory(app: ASGIApp) -> MCPProtectionMiddleware:
        return MCPProtectionMiddleware(
            app=app,
            secret_key=secret_key,
            mcp_path=mcp_path,
            required_scopes=required_scopes,
        )

    return middleware_factory
