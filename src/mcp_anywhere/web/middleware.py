"""Session-based authentication middleware for web UI routes."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp

from mcp_anywhere.config import Config
from mcp_anywhere.core.base_middleware import BasePathProtectionMiddleware
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class SessionAuthMiddleware(BasePathProtectionMiddleware):
    """Session-based authentication middleware for protecting web UI routes."""

    def __init__(
        self,
        app: ASGIApp,
        protected_paths: list[str] = None,
        skip_paths: list[str] = None,
        login_url: str = "/auth/login",
    ) -> None:
        """Initialize session authentication middleware.

        Args:
            app: ASGI application
            protected_paths: List of path patterns that require authentication
            skip_paths: List of path patterns to skip authentication
            login_url: URL to redirect to for login
        """
        # Initialize base class with path patterns
        super().__init__(
            app=app,
            protected_paths=protected_paths or ["/", "/servers", "/servers/*"],
            skip_paths=skip_paths
            or [
                "/auth/*",
                "/static/*",
                "/favicon.ico",
                f"{Config.MCP_PATH_MOUNT}/*",  # MCP API has its own JWT middleware
            ],
        )

        self.login_url = login_url

        logger.info(
            f"Session Auth Middleware initialized with protected paths: {self.protected_paths}"
        )

    def _is_authenticated(self, request: Request) -> bool:
        """Check if user is authenticated via session.

        Args:
            request: Starlette request object

        Returns:
            True if user is authenticated, False otherwise
        """
        user_id = request.session.get("user_id")
        return bool(user_id)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request through session authentication middleware.

        Args:
            request: Starlette request object
            call_next: Next middleware/application in chain

        Returns:
            Response from next middleware or redirect to login
        """
        path = request.url.path

        # Check if this path needs protection
        if not self._should_protect_path(path):
            # Path is not protected, continue to next middleware
            return await call_next(request)

        # Path is protected, check for valid session
        if not self._is_authenticated(request):
            logger.info(
                f"Unauthenticated access to protected path: {path}, redirecting to login"
            )
            # Redirect to login page
            return RedirectResponse(url=self.login_url, status_code=302)

        logger.debug(f"Authenticated session access to path: {path}")

        # User is authenticated, continue to next middleware
        return await call_next(request)


class RedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to redirect MCP mount path to its trailing-slash variant."""

    async def dispatch(self, request: Request, call_next):
        mcp_mount_path = Config.MCP_PATH_MOUNT
        if request.url.path == mcp_mount_path:
            return RedirectResponse(url=f"{Config.MCP_PATH_PREFIX}")

        # If it's a .well-known path with /mcp, strip it for correct routing
        if ".well-known" in request.url.path and request.url.path.endswith(
            mcp_mount_path
        ):
            new_path = request.url.path[: -len(mcp_mount_path)]
            request.scope["path"] = new_path

        return await call_next(request)


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that handles authentication for MCP endpoints."""

    async def dispatch(self, request: Request, call_next):
        # Only apply authentication to MCP endpoints (exact path or subpaths)
        path = request.url.path
        mcp_path = Config.MCP_PATH_MOUNT

        # Get out early if not an MCP endpoint or if it's a .well-known path
        if not path.startswith(mcp_path) or ".well-known" in path:
            return await call_next(request)

        # Get authorization header
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {
                    "error": "Authorization required",
                    "error_description": "Bearer token required",
                },
                status_code=401,
            )

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Get OAuth provider from app state
        oauth_provider = getattr(request.app.state, "oauth_provider", None)
        if not oauth_provider:
            return JSONResponse(
                {
                    "error": "Authentication configuration error",
                    "error_description": "OAuth provider not initialized",
                },
                status_code=500,
            )

        # Validate OAuth token via introspection
        access_token = await oauth_provider.introspect_token(token)
        if not access_token:
            return JSONResponse(
                {
                    "error": "Invalid token",
                    "error_description": "Token is invalid or expired",
                },
                status_code=401,
            )

        # Authentication successful, proceed with request
        return await call_next(request)
