"""Database utility functions for MCP Anywhere."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_anywhere.database import MCPServer, MCPServerTool
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


async def store_server_tools(
    db_session: AsyncSession,
    server_config: "MCPServer",
    discovered_tools: list[dict[str, Any]],
) -> None:
    """Store discovered tools in the database using async session.

    Args:
        db_session: Async database session
        server_config: The server configuration
        discovered_tools: List of tools discovered from the server
    """
    try:
        # Get existing tools
        stmt = select(MCPServerTool).where(MCPServerTool.server_id == server_config.id)
        result = await db_session.execute(stmt)
        existing_tools = {tool.tool_name: tool for tool in result.scalars().all()}

        discovered_tools_dict = {tool["name"]: tool for tool in discovered_tools}

        # Set of tools to add
        tools_to_add = discovered_tools_dict.keys() - existing_tools.keys()

        # Set of tools to remove
        tools_to_remove = existing_tools.keys() - discovered_tools_dict.keys()

        # Add new tools
        for tool_name in tools_to_add:
            new_tool = MCPServerTool(
                server_id=server_config.id,
                tool_name=tool_name,
                tool_description=discovered_tools_dict[tool_name]["description"],
                is_enabled=True,
            )
            db_session.add(new_tool)

        logger.info(
            f"Added {len(tools_to_add)} tools for server '{server_config.name}'"
        )

        # Remove tools that are no longer present
        if tools_to_remove:
            stmt = delete(MCPServerTool).where(
                MCPServerTool.server_id == server_config.id,
                MCPServerTool.tool_name.in_(tools_to_remove),
            )
            await db_session.execute(stmt)

        logger.info(
            f"Removed {len(tools_to_remove)} tools for server '{server_config.name}'"
        )

        await db_session.commit()
        logger.info(
            f"Stored {len(discovered_tools_dict)} tools for server '{server_config.name}'"
        )

    except (RuntimeError, ValueError, ConnectionError, IntegrityError) as e:
        logger.exception(f"Database error storing tools for {server_config.name}: {e}")
        await db_session.rollback()
        raise
