"""
Shared test fixtures for the MCP Anywhere test suite.

This module provides centralized fixtures for async testing as specified
in Phase 4 of the engineering documentation.
"""

import os
import tempfile
from collections.abc import AsyncGenerator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.applications import Starlette

from mcp_anywhere.base import Base
from mcp_anywhere.web.app import create_app


@pytest_asyncio.fixture(scope="function")
async def app() -> Starlette:
    """
    Creates a Starlette app instance for each test.
    Defaults to HTTP mode for backward compatibility with existing tests.

    Returns:
        Starlette: The configured application instance
    """
    return await create_app(transport_mode="http")


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Creates an in-memory SQLite database for testing.
    Initializes the schema, yields the session object, and cleans up after the test.

    Yields:
        AsyncSession: Database session for testing
    """
    # Create temporary file for test database
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_fd)

    engine = None
    session = None

    try:
        # Create async engine
        engine = create_async_engine(f"sqlite+aiosqlite:///{temp_path}")

        # Create tables (initialize schema)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create session maker
        async_session_maker = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )

        # Create and yield session
        async with async_session_maker() as session:
            yield session

    finally:
        # Cleanup
        if session:
            await session.close()
        if engine:
            await engine.dispose()

        # Remove temporary database file
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@pytest_asyncio.fixture
async def client(app: Starlette) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Creates an httpx.AsyncClient that can make requests to the test app.

    Args:
        app: The Starlette application instance

    Yields:
        httpx.AsyncClient: HTTP client for testing web endpoints
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
