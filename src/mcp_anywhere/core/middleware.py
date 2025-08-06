"""
Custom middleware for MCP Anywhere.

This module houses custom middleware as specified in Phase 3 of the engineering documentation.
The ToolFilterMiddleware has been moved here and updated to use async-safe database access.
"""

import json
from typing import Set, List, Any, Dict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from mcp_anywhere.database import MCPServerTool, get_async_session
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class ToolFilterMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware that filters tools based on database enable/disable status.

    This middleware intercepts MCP tools/list responses and filters out disabled tools
    while preserving the prefixed tool names for correct routing. It uses async-safe
    database access via request.run_in_threadpool to avoid blocking the event loop.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Intercept requests and filter MCP tools/list responses.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint

        Returns:
            Response: The potentially modified response
        """
        # Call the next middleware/endpoint
        response = await call_next(request)

        # Only process MCP tools/list requests
        if not self._is_mcp_tools_request(request):
            return response

        # Only process successful JSON responses
        if not self._is_json_response(response):
            return response

        try:
            # Get disabled tools from database using threadpool
            disabled_tools = await request.run_in_threadpool(self._get_disabled_tools_sync)

            if not disabled_tools:
                logger.debug("No disabled tools found, returning original response")
                return response

            # Filter the response
            filtered_response = await self._filter_response(response, disabled_tools)
            return filtered_response

        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Error in ToolFilterMiddleware: {e}")
            # Return original response on error
            return response

    def _is_mcp_tools_request(self, request: Request) -> bool:
        """Check if this is an MCP tools/list request."""
        path = request.url.path
        return "/mcp" in path and ("tools" in path or "list" in path.lower())

    def _is_json_response(self, response: Response) -> bool:
        """Check if the response is JSON."""
        content_type = response.headers.get("content-type", "")
        return "application/json" in content_type and response.status_code == 200

    def _get_disabled_tools_sync(self) -> Set[str]:
        """
        Synchronous method to query disabled tools from database.
        This runs in a thread pool to avoid blocking the event loop.

        Returns:
            Set[str]: Set of disabled tool names
        """
        try:
            import asyncio

            # Run async database query in sync context
            return asyncio.run(self._get_disabled_tools_async())

        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to query disabled tools from database: {e}")
            return set()

    async def _get_disabled_tools_async(self) -> Set[str]:
        """
        Async method to query disabled tools from database.

        Returns:
            Set[str]: Set of disabled tool names
        """
        disabled_tools = set()

        async with get_async_session() as db_session:
            # Query for disabled tools
            stmt = select(MCPServerTool.tool_name).where(MCPServerTool.is_enabled == False)
            result = await db_session.execute(stmt)
            disabled_tool_names = result.scalars().all()

            # Add to set
            for tool_name in disabled_tool_names:
                disabled_tools.add(tool_name)

            logger.debug(f"Found {len(disabled_tools)} disabled tools in database")

        return disabled_tools

    async def _filter_response(self, response: Response, disabled_tools: Set[str]) -> Response:
        """
        Filter tools from the response body.

        Args:
            response: Original response
            disabled_tools: Set of disabled tool names

        Returns:
            Response: Filtered response
        """
        try:
            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Parse JSON
            response_data = json.loads(body.decode())

            # Filter tools if present
            if isinstance(response_data, dict) and "tools" in response_data:
                original_count = len(response_data["tools"])
                response_data["tools"] = self._filter_tools(response_data["tools"], disabled_tools)
                filtered_count = len(response_data["tools"])

                logger.info(
                    f"Filtered tools list from {original_count} to {filtered_count} enabled tools"
                )

            elif isinstance(response_data, list):
                # Handle case where response is directly a list of tools
                original_count = len(response_data)
                response_data = self._filter_tools(response_data, disabled_tools)
                filtered_count = len(response_data)

                logger.info(
                    f"Filtered tools list from {original_count} to {filtered_count} enabled tools"
                )

            # Create new response with filtered data
            filtered_body = json.dumps(response_data).encode()
            return Response(
                content=filtered_body,
                status_code=response.status_code,
                headers=response.headers,
                media_type="application/json",
            )

        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Error filtering response: {e}")
            return response

    def _filter_tools(self, tools: List[Any], disabled_tools: Set[str]) -> List[Any]:
        """
        Filter a list of tools based on disabled tool names.

        Args:
            tools: List of tool objects or dictionaries
            disabled_tools: Set of disabled tool names

        Returns:
            List[Any]: Filtered list of tools
        """
        enabled_tools = []

        for tool in tools:
            if not self._is_tool_disabled(tool, disabled_tools):
                enabled_tools.append(tool)
            else:
                tool_name = self._get_tool_name(tool)
                logger.debug(f"Tool '{tool_name}' is disabled, filtering out")

        return enabled_tools

    def _is_tool_disabled(self, tool: Any, disabled_tools: Set[str]) -> bool:
        """
        Check if a tool is disabled based on its name.

        Args:
            tool: Tool object or dictionary
            disabled_tools: Set of disabled tool names

        Returns:
            bool: True if tool is disabled
        """
        tool_name = self._get_tool_name(tool)
        return tool_name in disabled_tools if tool_name else False

    def _get_tool_name(self, tool: Any) -> str:
        """
        Extract tool name from different possible formats.

        Args:
            tool: Tool object or dictionary

        Returns:
            str: Tool name or empty string if not found
        """
        if hasattr(tool, "name"):
            return tool.name
        elif isinstance(tool, dict) and "name" in tool:
            return tool["name"]
        else:
            return ""
