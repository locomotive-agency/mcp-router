"""FastMCP middleware to filter tools based on database enable/disable state.

This integrates with FastMCP's middleware lifecycle (e.g., on_list_tools)
so filtering happens at the correct protocol layer, before tools are exposed.

References:
- Filtering is performed by overriding the FastMCP middleware hook that lists tools,
  similar to patterns used in related projects [server.py][1], [middleware.py][2].

"""

from typing import Any, Iterable

from fastmcp.server.middleware import Middleware
from sqlalchemy import select

from mcp_anywhere.database import MCPServerTool, get_async_session
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class ToolFilterMiddleware(Middleware):
    """FastMCP middleware that filters disabled tools during tools/list.

    Hooks into FastMCP's lifecycle so tools are filtered before exposure.
    """

    async def on_list_tools(self, tools: Iterable[Any]) -> list[Any]:
        """Called by FastMCP before returning the available tools list.

        Args:
            tools: Iterable of tool objects/dicts from FastMCP

        Returns:
            list[Any]: Filtered list with disabled tools removed
        """
        try:
            disabled_tools = await self._get_disabled_tools_async()
        except Exception as exc:  # Do not fail tool listing on DB errors
            logger.error(f"Tool filtering skipped due to DB error: {exc}")
            return list(tools)

        if not disabled_tools:
            return list(tools)

        filtered = self._filter_tools(list(tools), disabled_tools)
        logger.info(
            f"ToolFilterMiddleware: filtered tools to {len(filtered)} enabled items"
        )
        return filtered

    @staticmethod
    async def _get_disabled_tools_async() -> set[str]:
        """Query disabled tool names from the database.

        Returns:
            set[str]: Set of disabled tool names
        """
        disabled: set[str] = set()
        async with get_async_session() as db_session:
            stmt = select(MCPServerTool.tool_name).where(MCPServerTool.is_enabled == False)
            result = await db_session.execute(stmt)
            for name in result.scalars().all():
                disabled.add(name)
        logger.debug(f"Disabled tools from DB: {len(disabled)}")
        return disabled

    def _filter_tools(self, tools: list[Any], disabled_tools: set[str]) -> list[Any]:
        """Filter a list of tools based on disabled names.

        Args:
            tools: List of tool objects or dictionaries
            disabled_tools: Set of disabled tool names

        Returns:
            list[Any]: Filtered list containing only enabled tools
        """
        enabled: list[Any] = []
        for tool in tools:
            if not self._is_tool_disabled(tool, disabled_tools):
                enabled.append(tool)
            else:
                logger.debug(f"Filtering disabled tool: {self._get_tool_name(tool)}")
        return enabled

    def _is_tool_disabled(self, tool: Any, disabled_tools: set[str]) -> bool:
        name = self._get_tool_name(tool)
        return bool(name and name in disabled_tools)

    @staticmethod
    def _get_tool_name(tool: Any) -> str:
        if hasattr(tool, "name"):
            return getattr(tool, "name")
        if isinstance(tool, dict) and "name" in tool:
            return tool["name"]
        return ""
