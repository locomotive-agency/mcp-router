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
    ) -> None:
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


"""
The specialized MCPProtectionMiddleware and its factory were removed as unused.
JWTAuthMiddleware remains for generic JWT-protected endpoints if needed.
"""
