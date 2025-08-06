"""Session-based authentication middleware for web UI routes."""

import fnmatch
from typing import List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse
from starlette.types import ASGIApp

from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Session-based authentication middleware for protecting web UI routes."""

    def __init__(
        self,
        app: ASGIApp,
        protected_paths: List[str] = None,
        skip_paths: List[str] = None,
        login_url: str = "/auth/login",
    ):
        """
        Initialize session authentication middleware.

        Args:
            app: ASGI application
            protected_paths: List of path patterns that require authentication
            skip_paths: List of path patterns to skip authentication
            login_url: URL to redirect to for login
        """
        super().__init__(app)
        self.protected_paths = protected_paths or ["/", "/servers", "/servers/*"]
        self.skip_paths = skip_paths or [
            "/auth/*",
            "/static/*",
            "/favicon.ico",
            "/mcp/*",  # MCP API has its own JWT middleware
        ]
        self.login_url = login_url

        logger.info(
            f"Session Auth Middleware initialized with protected paths: {self.protected_paths}"
        )

    def _should_protect_path(self, path: str) -> bool:
        """
        Check if a path should be protected by authentication.

        Args:
            path: Request path to check

        Returns:
            True if path should be protected, False otherwise
        """
        # First check if path should be skipped
        for skip_pattern in self.skip_paths:
            if fnmatch.fnmatch(path, skip_pattern):
                return False

        # Then check if path matches protected patterns
        for protected_pattern in self.protected_paths:
            if fnmatch.fnmatch(path, protected_pattern):
                return True

        return False

    def _is_authenticated(self, request: Request) -> bool:
        """
        Check if user is authenticated via session.

        Args:
            request: Starlette request object

        Returns:
            True if user is authenticated, False otherwise
        """
        user_id = request.session.get("user_id")
        return bool(user_id)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request through session authentication middleware.

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
            logger.info(f"Unauthenticated access to protected path: {path}, redirecting to login")
            # Redirect to login page
            return RedirectResponse(url=self.login_url, status_code=302)

        logger.debug(f"Authenticated session access to path: {path}")

        # User is authenticated, continue to next middleware
        return await call_next(request)
