from datetime import datetime, timedelta

import jwt
import pytest

from mcp_anywhere.auth.token_verifier import TokenVerifier


@pytest.mark.asyncio
async def test_token_verifier_initialization():
    """Test TokenVerifier initialization."""
    verifier = TokenVerifier()
    assert verifier.secret_key is not None
    assert verifier.algorithm == "HS256"


@pytest.mark.asyncio
async def test_verify_valid_token():
    """Test verifying a valid JWT token."""
    verifier = TokenVerifier()

    # Create a valid token payload
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read write",
        "client_id": "test_client",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "mcp-anywhere",
    }

    # Generate token
    token = jwt.encode(payload, verifier.secret_key, algorithm=verifier.algorithm)

    # Verify token
    result = verifier.verify(token)

    assert result is not None
    assert result["sub"] == "123"
    assert result["username"] == "testuser"
    assert result["scope"] == "read write"
    assert result["client_id"] == "test_client"
    assert result["iss"] == "mcp-anywhere"


@pytest.mark.asyncio
async def test_verify_expired_token():
    """Test verifying an expired JWT token."""
    verifier = TokenVerifier()

    # Create an expired token payload
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",
        "iat": datetime.utcnow() - timedelta(hours=2),
        "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
        "iss": "mcp-anywhere",
    }

    # Generate token
    token = jwt.encode(payload, verifier.secret_key, algorithm=verifier.algorithm)

    # Verify token
    result = verifier.verify(token)

    assert result is None


@pytest.mark.asyncio
async def test_verify_invalid_signature():
    """Test verifying a token with invalid signature."""
    verifier = TokenVerifier()

    # Create token with different secret
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "mcp-anywhere",
    }

    # Generate token with wrong secret
    wrong_secret = "wrong_secret_key"
    token = jwt.encode(payload, wrong_secret, algorithm=verifier.algorithm)

    # Verify token
    result = verifier.verify(token)

    assert result is None


@pytest.mark.asyncio
async def test_verify_malformed_token():
    """Test verifying a malformed JWT token."""
    verifier = TokenVerifier()

    # Use malformed token
    malformed_token = "not.a.valid.jwt.token"

    # Verify token
    result = verifier.verify(malformed_token)

    assert result is None


@pytest.mark.asyncio
async def test_verify_token_missing_issuer():
    """Test verifying a token without required issuer."""
    verifier = TokenVerifier()

    # Create token without issuer
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        # Missing "iss" field
    }

    # Generate token
    token = jwt.encode(payload, verifier.secret_key, algorithm=verifier.algorithm)

    # Verify token
    result = verifier.verify(token)

    assert result is None


@pytest.mark.asyncio
async def test_verify_token_wrong_issuer():
    """Test verifying a token with wrong issuer."""
    verifier = TokenVerifier()

    # Create token with wrong issuer
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "wrong-issuer",
    }

    # Generate token
    token = jwt.encode(payload, verifier.secret_key, algorithm=verifier.algorithm)

    # Verify token
    result = verifier.verify(token)

    assert result is None


@pytest.mark.asyncio
async def test_verify_token_with_custom_secret():
    """Test TokenVerifier with custom secret key."""
    custom_secret = "custom_secret_key"
    verifier = TokenVerifier(secret_key=custom_secret)

    # Create token with custom secret
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "mcp-anywhere",
    }

    # Generate token
    token = jwt.encode(payload, custom_secret, algorithm=verifier.algorithm)

    # Verify token
    result = verifier.verify(token)

    assert result is not None
    assert result["sub"] == "123"
    assert result["username"] == "testuser"


@pytest.mark.asyncio
async def test_extract_bearer_token():
    """Test extracting bearer token from Authorization header."""
    verifier = TokenVerifier()

    # Test valid bearer token
    auth_header = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"
    token = verifier.extract_bearer_token(auth_header)
    assert token == "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"

    # Test invalid format
    invalid_header = "Basic dXNlcjpwYXNz"
    token = verifier.extract_bearer_token(invalid_header)
    assert token is None

    # Test missing token
    missing_token = "Bearer "
    token = verifier.extract_bearer_token(missing_token)
    assert token is None

    # Test None header
    token = verifier.extract_bearer_token(None)
    assert token is None
