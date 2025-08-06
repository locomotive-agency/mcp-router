import pytest
import pytest_asyncio
import tempfile
import os
import secrets
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from urllib.parse import urlparse, parse_qs
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.applications import Starlette
from starlette.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from mcp_anywhere.database import Base
from mcp_anywhere.auth.models import User, OAuth2Client, AuthorizationCode
from mcp_anywhere.auth.oauth_server import SimpleAuthorizationServer


@pytest_asyncio.fixture
async def auth_db_session():
    """Database session for OAuth server tests."""
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
async def oauth_client(auth_db_session: AsyncSession):
    """Create a test OAuth2 client."""
    client = OAuth2Client(
        client_id="test_client_123",
        client_secret="test_secret",
        redirect_uri="http://localhost:3000/callback",
        scope="read write"
    )
    auth_db_session.add(client)
    await auth_db_session.commit()
    await auth_db_session.refresh(client)
    return client


@pytest_asyncio.fixture
async def test_user(auth_db_session: AsyncSession):
    """Create a test user."""
    user = User(username="testuser")
    user.set_password("testpassword")
    auth_db_session.add(user)
    await auth_db_session.commit()
    await auth_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_server(auth_db_session: AsyncSession):
    """Create an OAuth server instance."""
    return SimpleAuthorizationServer(auth_db_session)


@pytest.mark.asyncio
async def test_oauth_server_initialization(oauth_server: SimpleAuthorizationServer):
    """Test OAuth server initialization."""
    assert oauth_server.db_session is not None


@pytest.mark.asyncio
async def test_validate_authorize_request_valid(oauth_server: SimpleAuthorizationServer, oauth_client: OAuth2Client):
    """Test validating a valid authorization request."""
    # Create mock request
    request = Mock(spec=Request)
    request.query_params = {
        "client_id": oauth_client.client_id,
        "redirect_uri": oauth_client.redirect_uri,
        "response_type": "code",
        "scope": "read",
        "state": "test_state"
    }
    request.session = {}
    
    result = await oauth_server.validate_authorize_request(request)
    
    assert result is True
    assert "oauth_params" in request.session
    assert request.session["oauth_params"]["client_id"] == oauth_client.client_id
    assert request.session["oauth_params"]["redirect_uri"] == oauth_client.redirect_uri
    assert request.session["oauth_params"]["scope"] == "read"
    assert request.session["oauth_params"]["state"] == "test_state"


@pytest.mark.asyncio
async def test_validate_authorize_request_invalid_client_id(oauth_server: SimpleAuthorizationServer):
    """Test validation with invalid client_id."""
    request = Mock(spec=Request)
    request.query_params = {
        "client_id": "invalid_client",
        "redirect_uri": "http://localhost:3000/callback",
        "response_type": "code"
    }
    request.session = {}
    
    result = await oauth_server.validate_authorize_request(request)
    
    assert result is False


@pytest.mark.asyncio
async def test_validate_authorize_request_invalid_response_type(oauth_server: SimpleAuthorizationServer, oauth_client: OAuth2Client):
    """Test validation with invalid response_type."""
    request = Mock(spec=Request)
    request.query_params = {
        "client_id": oauth_client.client_id,
        "redirect_uri": oauth_client.redirect_uri,
        "response_type": "token"  # Invalid, should be "code"
    }
    request.session = {}
    
    result = await oauth_server.validate_authorize_request(request)
    
    assert result is False


@pytest.mark.asyncio
async def test_validate_authorize_request_redirect_uri_mismatch(oauth_server: SimpleAuthorizationServer, oauth_client: OAuth2Client):
    """Test validation with mismatched redirect_uri."""
    request = Mock(spec=Request)
    request.query_params = {
        "client_id": oauth_client.client_id,
        "redirect_uri": "http://malicious.com/callback",  # Different from registered URI
        "response_type": "code"
    }
    request.session = {}
    
    result = await oauth_server.validate_authorize_request(request)
    
    assert result is False


@pytest.mark.asyncio
async def test_create_authorization_response_grant_denied(oauth_server: SimpleAuthorizationServer):
    """Test authorization response when user denies access."""
    request = Mock(spec=Request)
    request.session = {
        "oauth_params": {
            "client_id": "test_client",
            "redirect_uri": "http://localhost:3000/callback",
            "state": "test_state"
        }
    }
    
    response = await oauth_server.create_authorization_response(request, grant=False)
    
    assert response.status_code == 307
    location = response.headers["location"]
    parsed_url = urlparse(location)
    query_params = parse_qs(parsed_url.query)
    
    assert "error" in query_params
    assert query_params["error"][0] == "access_denied"
    assert query_params["state"][0] == "test_state"


@pytest.mark.asyncio
async def test_create_authorization_response_grant_approved(oauth_server: SimpleAuthorizationServer, oauth_client: OAuth2Client, test_user: User):
    """Test authorization response when user approves access."""
    request = Mock(spec=Request)
    request.session = {
        "oauth_params": {
            "client_id": oauth_client.client_id,
            "redirect_uri": oauth_client.redirect_uri,
            "scope": "read",
            "state": "test_state"
        },
        "user_id": test_user.id
    }
    
    response = await oauth_server.create_authorization_response(request, grant=True)
    
    assert response.status_code == 307
    location = response.headers["location"]
    parsed_url = urlparse(location)
    query_params = parse_qs(parsed_url.query)
    
    assert "code" in query_params
    assert "state" in query_params
    assert query_params["state"][0] == "test_state"
    
    # Verify authorization code was stored in database
    code = query_params["code"][0]
    from sqlalchemy import select
    stmt = select(AuthorizationCode).where(AuthorizationCode.code == code)
    result = await oauth_server.db_session.execute(stmt)
    auth_code = result.scalar_one_or_none()
    
    assert auth_code is not None
    assert auth_code.client_id == oauth_client.client_id
    assert auth_code.user_id == test_user.id
    assert auth_code.scope == "read"


@pytest.mark.asyncio
async def test_create_token_response_valid_code(oauth_server: SimpleAuthorizationServer, oauth_client: OAuth2Client, test_user: User):
    """Test token creation with valid authorization code."""
    # First create an authorization code
    auth_code = AuthorizationCode(
        code="test_auth_code_123",
        client_id=oauth_client.client_id,
        user_id=test_user.id,
        redirect_uri=oauth_client.redirect_uri,
        scope="read",
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    oauth_server.db_session.add(auth_code)
    await oauth_server.db_session.commit()
    
    # Mock token request
    request = Mock(spec=Request)
    request_form = {
        "grant_type": "authorization_code",
        "code": "test_auth_code_123",
        "client_id": oauth_client.client_id,
        "client_secret": oauth_client.client_secret,
        "redirect_uri": oauth_client.redirect_uri
    }
    
    async def mock_form():
        return request_form
    
    request.form = mock_form
    
    response = await oauth_server.create_token_response(request)
    
    assert response.status_code == 200
    
    # Parse JSON response
    import json
    response_data = json.loads(response.body.decode())
    
    assert "access_token" in response_data
    assert "token_type" in response_data
    assert "expires_in" in response_data
    assert response_data["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_create_token_response_invalid_code(oauth_server: SimpleAuthorizationServer, oauth_client: OAuth2Client):
    """Test token creation with invalid authorization code."""
    request = Mock(spec=Request)
    request_form = {
        "grant_type": "authorization_code",
        "code": "invalid_code",
        "client_id": oauth_client.client_id,
        "client_secret": oauth_client.client_secret,
        "redirect_uri": oauth_client.redirect_uri
    }
    
    async def mock_form():
        return request_form
    
    request.form = mock_form
    
    response = await oauth_server.create_token_response(request)
    
    assert response.status_code == 400
    
    # Parse JSON response
    import json
    response_data = json.loads(response.body.decode())
    
    assert "error" in response_data
    assert response_data["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_create_token_response_expired_code(oauth_server: SimpleAuthorizationServer, oauth_client: OAuth2Client, test_user: User):
    """Test token creation with expired authorization code."""
    # Create an expired authorization code
    auth_code = AuthorizationCode(
        code="expired_code_123",
        client_id=oauth_client.client_id,
        user_id=test_user.id,
        redirect_uri=oauth_client.redirect_uri,
        scope="read",
        expires_at=datetime.utcnow() - timedelta(minutes=1)  # Expired
    )
    oauth_server.db_session.add(auth_code)
    await oauth_server.db_session.commit()
    
    request = Mock(spec=Request)
    request_form = {
        "grant_type": "authorization_code",
        "code": "expired_code_123",
        "client_id": oauth_client.client_id,
        "client_secret": oauth_client.client_secret,
        "redirect_uri": oauth_client.redirect_uri
    }
    
    async def mock_form():
        return request_form
    
    request.form = mock_form
    
    response = await oauth_server.create_token_response(request)
    
    assert response.status_code == 400
    
    # Parse JSON response
    import json
    response_data = json.loads(response.body.decode())
    
    assert "error" in response_data
    assert response_data["error"] == "invalid_grant"