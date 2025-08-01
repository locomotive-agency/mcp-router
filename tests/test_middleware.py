from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch, MagicMock

from fastmcp import Client, FastMCP

from mcp_router.middleware import ToolFilterMiddleware


class TestToolFilterMiddleware(unittest.TestCase):
    """Test the ToolFilterMiddleware for database-based tool filtering."""

    @patch('mcp_router.middleware.app')
    @patch('mcp_router.middleware.db')
    @patch('mcp_router.middleware.MCPServerTool')
    def test_tool_filtering_with_disabled_tools(self, mock_tool_model, mock_db, mock_app) -> None:
        """Test that middleware filters tools based on database disabled status."""

        mock_query_result = [('server01', 'server01_disabled_tool')]
        mock_db.session.query.return_value.filter_by.return_value.all.return_value = mock_query_result
        
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=None)
        mock_app.app_context.return_value = mock_context
        server = FastMCP("TestServer")
        server.add_middleware(ToolFilterMiddleware())

        @server.tool()
        def server01_enabled_tool() -> str:
            """Tool that should be visible."""
            return "This tool is enabled"

        @server.tool()
        def server01_disabled_tool() -> str:
            """Tool that should be hidden by middleware."""
            return "This tool should be filtered out"

        @server.tool()
        def server02_other_tool() -> str:
            """Tool from another server that should be visible."""
            return "This tool from server02"

        client = Client(server)

        async def _run() -> tuple[list[str], str]:
            async with client:
                tools = await client.list_tools()
                tool_names = [tool.name for tool in tools]
                enabled_result = await client.call_tool("server01_enabled_tool", {})
                return tool_names, enabled_result.structured_content["result"]

        visible_tools, enabled_result = asyncio.run(_run())
        self.assertIn("server01_enabled_tool", visible_tools)
        self.assertNotIn("server01_disabled_tool", visible_tools)
        self.assertIn("server02_other_tool", visible_tools)
        self.assertEqual(enabled_result, "This tool is enabled")

    @patch('mcp_router.app.app')
    @patch('mcp_router.models.db')
    @patch('mcp_router.models.MCPServerTool')
    def test_no_disabled_tools(self, mock_tool_model, mock_db, mock_app) -> None:
        """Test that middleware passes through all tools when none are disabled."""

        mock_db.session.query.return_value.filter_by.return_value.all.return_value = []
        mock_app.app_context.return_value.__enter__ = MagicMock()
        mock_app.app_context.return_value.__exit__ = MagicMock()
        server = FastMCP("TestServer")
        server.add_middleware(ToolFilterMiddleware())

        @server.tool()
        def tool1() -> str:
            """First tool."""
            return "tool1 result"

        @server.tool()
        def tool2() -> str:
            """Second tool."""
            return "tool2 result"

        client = Client(server)

        async def _run() -> list[str]:
            async with client:
                tools = await client.list_tools()
                return [tool.name for tool in tools]

        visible_tools = asyncio.run(_run())
        self.assertIn("tool1", visible_tools)
        self.assertIn("tool2", visible_tools)

    def test_native_prefix_handling(self) -> None:
        """Test that FastMCP handles prefixed tool calls natively without middleware intervention."""

        child_server = FastMCP("ChildServer")

        @child_server.tool()
        def echo(text: str) -> str:
            """Return the provided text verbatim."""
            return text

        parent_server = FastMCP("ParentServer")
        
        with patch('mcp_router.app.app'), \
             patch('mcp_router.models.db') as mock_db:
            
            mock_db.session.query.return_value.filter_by.return_value.all.return_value = []
            parent_server.add_middleware(ToolFilterMiddleware())

            prefix = "test_id"
            parent_server.mount(child_server, prefix=prefix, as_proxy=True)

            client = Client(parent_server)

            async def _run() -> str:
                async with client:
                    result = await client.call_tool(f"{prefix}_echo", {"text": "hello"})
                    return result.structured_content["result"]

            response = asyncio.run(_run())
            self.assertEqual(response, "hello")


if __name__ == "__main__":
    unittest.main() 