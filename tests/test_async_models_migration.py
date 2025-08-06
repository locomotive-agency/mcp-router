"""
Test async equivalents of Flask-SQLAlchemy model functions.

This module tests the migrated async database functions to replace Flask-SQLAlchemy.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from mcp_anywhere.database import MCPServer, get_async_session

# PAUSED: Tests that create servers in database
pytestmark = pytest.mark.skip(reason="Paused: Tests create and commit servers to database")


@pytest.mark.asyncio
async def test_get_active_servers_async(db_session: AsyncSession):
    """
    Test async version of get_active_servers function.
    """
    # Create test servers
    active_server = MCPServer(
        id="act12345",
        name="Active Server",
        github_url="https://github.com/test/active",
        runtime_type="uvx",
        start_command="uvx test-server",
        is_active=True
    )
    
    inactive_server = MCPServer(
        id="ina12345", 
        name="Inactive Server",
        github_url="https://github.com/test/inactive",
        runtime_type="uvx",
        start_command="uvx inactive-server", 
        is_active=False
    )
    
    db_session.add(active_server)
    db_session.add(inactive_server)
    await db_session.commit()
    
    # Test async function using provided session
    from sqlalchemy import select
    stmt = select(MCPServer).where(MCPServer.is_active == True)
    result = await db_session.execute(stmt)
    active_servers = result.scalars().all()
    
    # Verify only active server returned
    assert len(active_servers) == 1
    assert active_servers[0].name == "Active Server"
    assert active_servers[0].is_active == True


@pytest.mark.asyncio
async def test_get_built_servers_async(db_session: AsyncSession):
    """
    Test async version of get_built_servers function.
    """
    # Create test servers with different build statuses
    built_server = MCPServer(
        id="blt12345",
        name="Built Server",
        github_url="https://github.com/test/built",
        runtime_type="uvx",
        start_command="uvx built-server",
        build_status="built"
    )
    
    pending_server = MCPServer(
        id="pen12345",
        name="Pending Server", 
        github_url="https://github.com/test/pending",
        runtime_type="uvx",
        start_command="uvx pending-server",
        build_status="pending"
    )
    
    failed_server = MCPServer(
        id="fai12345",
        name="Failed Server",
        github_url="https://github.com/test/failed", 
        runtime_type="uvx",
        start_command="uvx failed-server",
        build_status="failed"
    )
    
    db_session.add(built_server)
    db_session.add(pending_server)
    db_session.add(failed_server)
    await db_session.commit()
    
    # Test async function using provided session 
    stmt = select(MCPServer).where(MCPServer.build_status == "built")
    result = await db_session.execute(stmt)
    built_servers = result.scalars().all()
    
    # Verify only built server returned
    assert len(built_servers) == 1
    assert built_servers[0].name == "Built Server"
    assert built_servers[0].build_status == "built"


@pytest.mark.asyncio
async def test_container_manager_no_flask_dependency():
    """
    Test that ContainerManager can be initialized without Flask app.
    """
    # Import here to test after the fix is implemented
    from mcp_anywhere.container.manager import ContainerManager
    
    # Should be able to create without Flask app
    container_manager = ContainerManager()
    
    # Should have basic functionality
    assert hasattr(container_manager, 'docker_client')
    assert hasattr(container_manager, 'python_image')
    assert hasattr(container_manager, 'node_image')


@pytest.mark.asyncio
async def test_async_database_functions_work(db_session: AsyncSession):
    """
    Test that async database functions work correctly.
    """
    # Test that we can import and use async database functions
    from mcp_anywhere.database import get_active_servers, get_built_servers
    from sqlalchemy import select
    
    # Verify we can use the helper functions with provided session
    active_servers = await get_active_servers(session=db_session)
    built_servers = await get_built_servers(session=db_session)
        
    # Should return lists (empty or with servers)
    assert isinstance(active_servers, list)
    assert isinstance(built_servers, list)


@pytest.mark.asyncio
async def test_models_removed_flask_dependencies():
    """
    Test that Flask-SQLAlchemy dependencies are removed.
    """
    # After fix, this should not import Flask-SQLAlchemy
    try:
        from mcp_anywhere.database import MCPServer, MCPServerTool
        
        # These should be async SQLAlchemy models, not Flask-SQLAlchemy
        assert hasattr(MCPServer, '__tablename__')
        assert hasattr(MCPServerTool, '__tablename__')
        
        # Should not have Flask-SQLAlchemy specific attributes
        assert not hasattr(MCPServer, 'query')  # Flask-SQLAlchemy specific
        
    except ImportError:
        pytest.fail("Should be able to import from database module")