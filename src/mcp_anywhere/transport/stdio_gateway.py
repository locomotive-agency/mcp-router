"""Lightweight STDIO gateway for MCP client connections.
This module provides a clean stdio interface without any web server or management overhead.
"""

# Disable FastMCP banner before any imports
import os

os.environ["FASTMCP_DISABLE_BANNER"] = "1"


import logging

from fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from mcp_anywhere.config import Config
from mcp_anywhere.core.mcp_manager import create_gateway_config
from mcp_anywhere.database import MCPServer

# Completely disable logging for clean stdio
logging.disable(logging.CRITICAL)


async def run_connect_gateway() -> None:
    """Run the lightweight STDIO gateway for MCP client connections.

    This function:
    1. Reads server configurations from the database (read-only)
    2. Creates FastMCP proxy instances for each configured server
    3. Runs the stdio transport for client communication
    4. Does NOT start any web servers or management interfaces
    """
    try:
        # Additional logging suppression for imported modules
        logging.getLogger("sqlalchemy").disabled = True
        logging.getLogger("docker").disabled = True
        logging.getLogger("uvicorn").disabled = True
        logging.getLogger("starlette").disabled = True

        # 1. Connect to database (read-only)
        # Convert SQLite URI to async version if needed
        db_uri = Config.SQLALCHEMY_DATABASE_URI
        if db_uri.startswith("sqlite://"):
            db_uri = db_uri.replace("sqlite://", "sqlite+aiosqlite://", 1)

        engine = create_async_engine(
            db_uri,
            echo=False,  # No SQL logs
            pool_size=1,  # Minimal connection pool
            max_overflow=0,
        )

        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        servers: list[MCPServer] = []
        async with AsyncSessionLocal() as session:
            # Read all configured servers
            result = await session.execute(select(MCPServer).where(MCPServer.is_active == True))
            servers = result.scalars().all()

            # Eagerly load relationships to avoid lazy loading issues
            for server in servers:
                _ = server.env_variables  # Force load

        await engine.dispose()  # Close DB connection

        if not servers:
            # Return empty capabilities if no servers configured
            router = FastMCP(
                name="MCP Anywhere Gateway",
                instructions="No servers configured. Please use the web UI to add servers.",
            )
            await router.run(transport="stdio")
            return

        # 2. Create the FastMCP router
        router = FastMCP(
            name="MCP Anywhere Gateway",
            instructions="Unified gateway for Model Context Protocol servers",
        )

        # 3. Generate proxy configuration for existing containers
        proxy_config = create_gateway_config(servers)

        if not proxy_config.get("mcpServers"):
            # Silently return if no servers configured
            return

        # 4. Mount each server as a proxy with its unique prefix
        for server in servers:
            server_id = server.id  # 8-character unique ID

            # Create individual proxy config for this server
            single_config = create_gateway_config([server])

            if not single_config.get("mcpServers"):
                continue

            # Create proxy instance
            proxy = FastMCP.as_proxy(single_config)

            # Mount with server ID as prefix
            router.mount(proxy, prefix=server_id)

            # Silently mount servers without logging

        # 5. Run the stdio transport
        # Redirect stderr to suppress all output from underlying MCP servers
        import contextlib
        import io
        import sys

        # Suppress all stderr output to keep MCP protocol clean
        with contextlib.redirect_stderr(io.StringIO()):
            await router.run_stdio_async()

    except KeyboardInterrupt:
        # Clean shutdown on Ctrl+C
        pass
    except (RuntimeError, ValueError, OSError, ConnectionError):
        # Silent exit on any error to keep stdio clean
        sys.exit(1)
