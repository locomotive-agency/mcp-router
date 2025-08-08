"""Base middleware for path-based protection."""

import fnmatch

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class BasePathProtectionMiddleware(BaseHTTPMiddleware):
    """Base middleware for path-based protection.

    This class provides common functionality for checking if paths
    should be protected, used by both JWT and Session auth middlewares.
    """

    def __init__(
        self,
        app: ASGIApp,
        protected_paths: list[str] = None,
        skip_paths: list[str] = None,
    ) -> None:
        """Initialize base path protection middleware.

        Args:
            app: ASGI application
            protected_paths: List of path patterns that require authentication
            skip_paths: List of path patterns to skip authentication
        """
        super().__init__(app)
        self.protected_paths = protected_paths or []
        self.skip_paths = skip_paths or []

    def _should_protect_path(self, path: str) -> bool:
        """Check if a path should be protected by authentication.

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
