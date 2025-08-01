"""Utilities for safely executing async code from sync contexts."""

import asyncio
from typing import Any, Coroutine, Optional, TypeVar
import threading
from mcp_router.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class EventLoopManager:
    """Manages the main event loop reference for async operations from sync contexts."""

    _instance: Optional["EventLoopManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    def get_instance(cls) -> "EventLoopManager":
        """Get the singleton instance of EventLoopManager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the main event loop reference."""
        self.main_loop = loop
        logger.info(f"Main event loop set: {loop}")

    def run_async(self, coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
        """
        Run an async coroutine from a sync context using the main event loop.

        Args:
            coro: The coroutine to run
            timeout: Timeout in seconds

        Returns:
            The result of the coroutine

        Raises:
            RuntimeError: If no main loop is set or if execution fails
            TimeoutError: If the operation times out
        """
        if self.main_loop is None:
            raise RuntimeError("No main event loop set. Initialize EventLoopManager first.")

        if self.main_loop.is_closed():
            raise RuntimeError("Main event loop is closed.")

        # Check if we're already in the event loop
        try:
            current_loop = asyncio.get_running_loop()
            if current_loop == self.main_loop:
                # We're already in the main loop, just await the coroutine
                logger.warning("Already in main event loop, running coroutine directly")
                return asyncio.run_coroutine_threadsafe(coro, self.main_loop).result(timeout)
        except RuntimeError:
            # No running loop, we're in sync context
            pass

        # Schedule the coroutine on the main event loop
        future = asyncio.run_coroutine_threadsafe(coro, self.main_loop)

        try:
            result = future.result(timeout=timeout)
            return result
        except TimeoutError:
            logger.error(f"Async operation timed out after {timeout} seconds")
            future.cancel()
            raise
        except Exception as e:
            logger.error(f"Error executing async operation: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up resources."""
        self.main_loop = None


def run_async_from_sync(coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
    """
    Convenience function to run async code from sync context.

    Args:
        coro: The coroutine to run
        timeout: Timeout in seconds

    Returns:
        The result of the coroutine
    """
    manager = EventLoopManager.get_instance()
    return manager.run_async(coro, timeout)
