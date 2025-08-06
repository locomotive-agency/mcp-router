import pytest
import pytest_asyncio
import tempfile
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from mcp_anywhere.database import MCPServer, Base

# PAUSED: Tests that create servers in database
pytestmark = pytest.mark.skip(reason="Paused: Tests create and commit servers to database")


@pytest_asyncio.fixture
async def async_db_session():
    """
    Pytest fixture to provide an async database session for testing.
    Creates an in-memory SQLite database for each test.
    """
    # Create temporary file for test database
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_fd)
    
    engine = None
    session = None
    
    try:
        # Create async engine
        engine = create_async_engine(f"sqlite+aiosqlite:///{temp_path}")
        
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # Create session factory
        async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create and yield session
        session = async_session_factory()
        yield session
        
    finally:
        # Cleanup
        if session:
            await session.close()
        if engine:
            await engine.dispose()
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@pytest_asyncio.fixture
async def sample_server():
    """Fixture providing a sample MCPServer for testing"""
    return MCPServer(
        name="Test Server",
        runtime_type="docker",
        start_command="echo hello",
        github_url="https://github.com/test/repo"
    )


@pytest.mark.asyncio
async def test_async_database_operations(async_db_session: AsyncSession, sample_server: MCPServer):
    """
    Test basic async database operations with MCPServer model.
    """
    # Test creating a server
    async_db_session.add(sample_server)
    await async_db_session.commit()
    
    # Test querying the server
    stmt = select(MCPServer).where(MCPServer.name == "Test Server")
    result = await async_db_session.execute(stmt)
    retrieved_server = result.scalar_one_or_none()
    
    assert retrieved_server is not None
    assert retrieved_server.name == "Test Server"
    assert retrieved_server.runtime_type == "docker"
    assert retrieved_server.github_url == "https://github.com/test/repo"
    assert retrieved_server.id is not None  # Should have generated an ID


@pytest.mark.asyncio
async def test_multiple_servers_query(async_db_session: AsyncSession):
    """
    Test querying multiple servers from the database.
    """
    # Create multiple servers
    servers = [
        MCPServer(name="Server 1", runtime_type="docker", start_command="cmd1", github_url="https://github.com/test/repo1"),
        MCPServer(name="Server 2", runtime_type="npx", start_command="cmd2", github_url="https://github.com/test/repo2"),
        MCPServer(name="Server 3", runtime_type="uvx", start_command="cmd3", github_url="https://github.com/test/repo3"),
    ]
    
    for server in servers:
        async_db_session.add(server)
    await async_db_session.commit()
    
    # Query all servers
    stmt = select(MCPServer).order_by(MCPServer.name)
    result = await async_db_session.execute(stmt)
    all_servers = result.scalars().all()
    
    assert len(all_servers) == 3
    assert all_servers[0].name == "Server 1"
    assert all_servers[1].name == "Server 2"
    assert all_servers[2].name == "Server 3"


@pytest.mark.asyncio
async def test_server_to_dict(async_db_session: AsyncSession, sample_server: MCPServer):
    """
    Test the to_dict method of MCPServer.
    """
    async_db_session.add(sample_server)
    await async_db_session.commit()
    
    server_dict = sample_server.to_dict()
    assert server_dict["name"] == "Test Server"
    assert server_dict["runtime_type"] == "docker"
    assert server_dict["github_url"] == "https://github.com/test/repo"
    assert "id" in server_dict
    assert "created_at" in server_dict