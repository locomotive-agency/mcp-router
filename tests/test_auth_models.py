import pytest
import pytest_asyncio
import tempfile
import os
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from mcp_anywhere.database import Base
from mcp_anywhere.auth.models import User, OAuth2Client


@pytest_asyncio.fixture
async def auth_db_session():
    """
    Pytest fixture to provide an async database session for auth testing.
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


@pytest.mark.asyncio
async def test_user_model_creation(auth_db_session: AsyncSession):
    """Test creating a User model."""
    user = User(
        username="admin",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/hq0.CHPllKqFBDTSu"  # "password" hashed
    )
    
    auth_db_session.add(user)
    await auth_db_session.commit()
    await auth_db_session.refresh(user)
    
    assert user.id is not None
    assert user.username == "admin"
    assert user.password_hash.startswith("$2b$")
    assert user.created_at is not None


@pytest.mark.asyncio
async def test_user_password_verification(auth_db_session: AsyncSession):
    """Test user password verification."""
    user = User(username="testuser")
    user.set_password("secret123")
    
    assert user.check_password("secret123") is True
    assert user.check_password("wrongpassword") is False


@pytest.mark.asyncio
async def test_oauth2_client_model_creation(auth_db_session: AsyncSession):
    """Test creating an OAuth2Client model."""
    client = OAuth2Client(
        client_id="test_client",
        client_secret="secret123",
        redirect_uri="http://localhost:3000/auth/callback",
        scope="read write"
    )
    
    auth_db_session.add(client)
    await auth_db_session.commit()
    await auth_db_session.refresh(client)
    
    assert client.id is not None
    assert client.client_id == "test_client"
    assert client.client_secret == "secret123"
    assert client.redirect_uri == "http://localhost:3000/auth/callback"
    assert client.scope == "read write"
    assert client.created_at is not None


@pytest.mark.asyncio
async def test_oauth2_client_default_scope(auth_db_session: AsyncSession):
    """Test OAuth2Client with default scope."""
    client = OAuth2Client(
        client_id="default_client",
        client_secret="secret",
        redirect_uri="http://localhost:3000/callback"
    )
    
    auth_db_session.add(client)
    await auth_db_session.commit()
    await auth_db_session.refresh(client)
    
    assert client.scope == "read"  # Default scope


@pytest.mark.asyncio
async def test_user_query_by_username(auth_db_session: AsyncSession):
    """Test querying user by username."""
    # Create test user
    user = User(username="querytest")
    user.set_password("testpass")
    
    auth_db_session.add(user)
    await auth_db_session.commit()
    
    # Query by username
    stmt = select(User).where(User.username == "querytest")
    result = await auth_db_session.execute(stmt)
    found_user = result.scalar_one_or_none()
    
    assert found_user is not None
    assert found_user.username == "querytest"
    assert found_user.check_password("testpass") is True


@pytest.mark.asyncio
async def test_oauth2_client_query_by_client_id(auth_db_session: AsyncSession):
    """Test querying OAuth2Client by client_id."""
    # Create test client
    client = OAuth2Client(
        client_id="query_test_client",
        client_secret="secret",
        redirect_uri="http://localhost:3000/callback"
    )
    
    auth_db_session.add(client)
    await auth_db_session.commit()
    
    # Query by client_id
    stmt = select(OAuth2Client).where(OAuth2Client.client_id == "query_test_client")
    result = await auth_db_session.execute(stmt)
    found_client = result.scalar_one_or_none()
    
    assert found_client is not None
    assert found_client.client_id == "query_test_client"
    assert found_client.client_secret == "secret"


@pytest.mark.asyncio
async def test_user_unique_username_constraint(auth_db_session: AsyncSession):
    """Test that username must be unique."""
    # Create first user
    user1 = User(username="unique_test")
    user1.set_password("password1")
    auth_db_session.add(user1)
    await auth_db_session.commit()
    
    # Try to create second user with same username
    user2 = User(username="unique_test")
    user2.set_password("password2")
    auth_db_session.add(user2)
    
    with pytest.raises(Exception):  # Should raise integrity error
        await auth_db_session.commit()