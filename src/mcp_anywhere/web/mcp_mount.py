"""Custom MCP mount handler that properly manages FastMCP lifespan."""

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class FastMCPLifespanWrapper:
    """Wrapper that ensures FastMCP's lifespan is properly managed when mounted."""

    def __init__(self, fastmcp_app: ASGIApp) -> None:
        """Initialize with the FastMCP HTTP app."""
        self.fastmcp_app = fastmcp_app
        self.lifespan_task = None
        self.lifespan_started = False
        self.startup_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI handler that ensures lifespan is running before handling requests."""
        # Start lifespan if not already started
        if not self.lifespan_started:
            await self._ensure_lifespan_started()

        # Forward the request to the FastMCP app
        await self.fastmcp_app(scope, receive, send)

    async def _ensure_lifespan_started(self) -> None:
        """Ensure the FastMCP lifespan is started."""
        if self.lifespan_started:
            return

        self.lifespan_started = True
        logger.info("Starting FastMCP lifespan manager")

        # Create a mock ASGI lifespan scope
        lifespan_scope = {
            "type": "lifespan",
            "asgi": {"version": "3.0"},
            "state": {},
        }

        # Create receive/send for lifespan protocol
        async def lifespan_receive():
            # First call returns startup
            if not self.startup_event.is_set():
                self.startup_event.set()
                return {"type": "lifespan.startup"}
            # Wait for shutdown
            await self.shutdown_event.wait()
            return {"type": "lifespan.shutdown"}

        async def lifespan_send(message) -> None:
            if message["type"] == "lifespan.startup.complete":
                logger.info("FastMCP lifespan startup complete")
            elif message["type"] == "lifespan.startup.failed":
                logger.error(
                    f"FastMCP lifespan startup failed: {message.get('message', 'Unknown error')}"
                )
                raise RuntimeError("FastMCP lifespan startup failed")
            elif message["type"] == "lifespan.shutdown.complete":
                logger.info("FastMCP lifespan shutdown complete")
            elif message["type"] == "lifespan.shutdown.failed":
                logger.error(
                    f"FastMCP lifespan shutdown failed: {message.get('message', 'Unknown error')}"
                )

        # Start the lifespan in a background task
        self.lifespan_task = asyncio.create_task(
            self.fastmcp_app(lifespan_scope, lifespan_receive, lifespan_send)
        )

        # Wait a moment for startup to complete
        await asyncio.sleep(0.1)

    async def shutdown(self) -> None:
        """Shutdown the FastMCP lifespan."""
        if self.lifespan_task and not self.lifespan_task.done():
            logger.info("Shutting down FastMCP lifespan")
            self.shutdown_event.set()
            try:
                await asyncio.wait_for(self.lifespan_task, timeout=5.0)
            except TimeoutError:
                logger.warning("FastMCP lifespan shutdown timed out")
                self.lifespan_task.cancel()
                try:
                    await self.lifespan_task
                except asyncio.CancelledError:
                    pass


async def create_mcp_mount_with_lifespan(mcp_manager):
    """Create a properly wrapped FastMCP HTTP app with lifespan management.

    Args:
        mcp_manager: The MCP manager containing the router

    Returns:
        FastMCPLifespanWrapper: Wrapped app that manages lifespan
    """
    # Create the FastMCP HTTP app
    mcp_http_app = mcp_manager.router.http_app(path="/", transport="http")

    # Wrap it with our lifespan manager
    wrapped_app = FastMCPLifespanWrapper(mcp_http_app)

    # Start the lifespan immediately
    await wrapped_app._ensure_lifespan_started()

    return wrapped_app
