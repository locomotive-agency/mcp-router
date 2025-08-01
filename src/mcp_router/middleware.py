"""Middleware for tool filtering based on database enable/disable status in MCP Router"""

from typing import Any, Callable, Awaitable, Set, List
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import Tool
from mcp_router.logging_config import get_logger
from mcp_router.models import MCPServerTool, db
from mcp_router.app import app

logger = get_logger(__name__)


class ToolFilterMiddleware(Middleware):
    """
    Middleware that filters tools based on database enable/disable status.

    This middleware queries the database to check which tools are disabled
    and filters them out from the tools/list response while preserving
    the prefixed tool names for correct routing.
    """

    async def on_list_tools(
        self,
        ctx: MiddlewareContext,
        call_next: Callable[[MiddlewareContext], Awaitable[List[Tool]]],
    ) -> List[Tool]:
        """Intercept the tools/list request and filter the results."""
        all_tools = await call_next(ctx)
        logger.debug(repr(all_tools))
        logger.debug("Intercepting tools/list response to filter disabled tools")

        disabled_tools = self._get_disabled_tools()
        logger.debug(f"Disabled tools: {disabled_tools}")
        if not disabled_tools:
            logger.debug("No disabled tools found, returning all tools")
            return all_tools

        enabled_tools = [
            tool for tool in all_tools if not self._is_tool_disabled(tool, disabled_tools)
        ]

        logger.info(
            f"Filtered tools list from {len(all_tools)} to {len(enabled_tools)} enabled tools"
        )
        return enabled_tools

    def _get_disabled_tools(self) -> Set[str]:
        """Query the database for disabled tools and return their names."""
        try:
            disabled_tools = set()

            with app.app_context():

                # Query for disabled tools
                disabled_tools_query = (
                    db.session.query(MCPServerTool.server_id, MCPServerTool.tool_name)
                    .filter_by(is_enabled=False)
                    .all()
                )

                # Create tool names
                for server_id, tool_name in disabled_tools_query:
                    disabled_tools.add(tool_name)

                logger.debug(f"Found {len(disabled_tools)} disabled tools in database")

            return disabled_tools

        except Exception as e:
            logger.error(f"Failed to query disabled tools from database: {e}")
            return set()

    def _is_tool_disabled(self, tool: Any, disabled_tools: Set[str]) -> bool:
        """Check if a tool is disabled based on its name."""
        # Get tool name from different possible formats
        tool_name = None
        if hasattr(tool, "name"):
            tool_name = tool.name
        elif isinstance(tool, dict) and "name" in tool:
            tool_name = tool["name"]

        if tool_name and tool_name in disabled_tools:
            logger.debug(f"Tool '{tool_name}' is disabled, filtering out")
            return True

        return False
