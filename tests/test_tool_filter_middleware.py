"""
Test the ToolFilterMiddleware.

This module tests the moved and refactored ToolFilterMiddleware as specified
in Phase 3 of the engineering documentation.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_anywhere.core.middleware import ToolFilterMiddleware


@pytest.mark.asyncio
async def test_tool_filter_middleware_initialization():
    """
    Test that ToolFilterMiddleware can be initialized properly.
    """
    middleware = ToolFilterMiddleware()
    assert isinstance(middleware, ToolFilterMiddleware)


@pytest.mark.asyncio
async def test_tool_filter_middleware_passthrough_when_no_disabled_tools():
    """
    When there are no disabled tools, on_list_tools should return the original list.
    """

    middleware = ToolFilterMiddleware()
    tools = [
        {"name": "enabled_tool", "description": "An enabled tool"},
        {"name": "another_enabled_tool", "description": "Another enabled tool"},
    ]

    # Mock context and call_next
    mock_context = Mock()
    mock_call_next = AsyncMock(return_value=tools)

    # No disabled tools
    with patch.object(
        ToolFilterMiddleware,
        "_get_disabled_tools_async",
        new=AsyncMock(return_value=set()),
    ):
        result = await middleware.on_list_tools(mock_context, mock_call_next)
        assert result == tools
        mock_call_next.assert_called_once_with(mock_context)


@pytest.mark.asyncio
async def test_tool_filter_middleware_filters_disabled_tools():
    """
    Test that the middleware filters out disabled tools from the tools list.
    """
    tools = [
        {"name": "enabled_tool", "description": "An enabled tool"},
        {"name": "disabled_tool", "description": "A disabled tool"},
        {"name": "another_enabled_tool", "description": "Another enabled tool"},
    ]

    middleware = ToolFilterMiddleware()

    # Mock context and call_next
    mock_context = Mock()
    mock_call_next = AsyncMock(return_value=tools)

    with patch.object(
        ToolFilterMiddleware,
        "_get_disabled_tools_async",
        new=AsyncMock(return_value={"disabled_tool"}),
    ):
        filtered = await middleware.on_list_tools(mock_context, mock_call_next)
        tool_names = {
            t["name"] if isinstance(t, dict) else getattr(t, "name", "")
            for t in filtered
        }
        assert "disabled_tool" not in tool_names
        mock_call_next.assert_called_once_with(mock_context)


@pytest.mark.asyncio
async def test_get_disabled_tools_from_database():
    """
    Test that disabled tools are correctly queried from the database.
    """
    # Create mock disabled tools
    [
        Mock(tool_name="tool1", is_enabled=False),
        Mock(tool_name="tool2", is_enabled=False),
    ]

    middleware = ToolFilterMiddleware()
    with patch("mcp_anywhere.core.middleware.get_async_session") as mock_session:
        # Setup database mock
        mock_db = AsyncMock(spec=AsyncSession)
        mock_session.return_value.__aenter__.return_value = mock_db
        # Configure execute to return an object with scalars().all()
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = ["tool1", "tool2"]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Call async method directly
        disabled = await middleware._get_disabled_tools_async()
        assert disabled == {"tool1", "tool2"}


@pytest.mark.asyncio
async def test_middleware_handles_database_errors():
    """
    If database access fails, on_list_tools should return the original list.
    """
    middleware = ToolFilterMiddleware()
    tools = [
        {"name": "enabled_tool"},
        {"name": "maybe_disabled_tool"},
    ]

    # Mock context and call_next
    mock_context = Mock()
    mock_call_next = AsyncMock(return_value=tools)

    with patch.object(
        ToolFilterMiddleware,
        "_get_disabled_tools_async",
        new=AsyncMock(side_effect=Exception("DB failure")),
    ):
        result = await middleware.on_list_tools(mock_context, mock_call_next)
        assert result == tools
        mock_call_next.assert_called_once_with(mock_context)


@pytest.mark.asyncio
async def test_tool_filtering_logic():
    """
    Test the tool filtering logic with various tool formats.
    """
    middleware = ToolFilterMiddleware()

    # Test tools in different formats
    enabled_tool_mock = Mock()
    enabled_tool_mock.name = "another_enabled_tool"
    disabled_tool_mock = Mock()
    disabled_tool_mock.name = "another_disabled_tool"

    tools = [
        {"name": "enabled_tool"},
        {"name": "disabled_tool"},
        enabled_tool_mock,
        disabled_tool_mock,
    ]

    disabled_tools = {"disabled_tool", "another_disabled_tool"}

    filtered_tools = middleware._filter_tools(tools, disabled_tools)

    # Should only have enabled tools
    assert len(filtered_tools) == 2

    # Check that disabled tools are filtered out
    tool_names = []
    for tool in filtered_tools:
        if hasattr(tool, "name"):
            tool_names.append(tool.name)
        elif isinstance(tool, dict) and "name" in tool:
            tool_names.append(tool["name"])

    assert "enabled_tool" in tool_names
    assert "another_enabled_tool" in tool_names
    assert "disabled_tool" not in tool_names
    assert "another_disabled_tool" not in tool_names
