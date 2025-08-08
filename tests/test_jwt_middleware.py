from datetime import datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_anywhere.auth.middleware import JWTAuthMiddleware


@pytest_asyncio.fixture
async def jwt_secret():
    """JWT secret for testing."""
    return "test-jwt-secret-key"


@pytest_asyncio.fixture
async def valid_token(jwt_secret: str):
    """Create a valid JWT token for testing."""
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read write",
        "client_id": "test_client",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "mcp-anywhere",
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


@pytest_asyncio.fixture
async def expired_token(jwt_secret: str):
    """Create an expired JWT token for testing."""
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",
        "iat": datetime.utcnow() - timedelta(hours=2),
        "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
        "iss": "mcp-anywhere",
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


@pytest_asyncio.fixture
async def test_app_with_auth():
    """Create test app with JWT middleware."""

    async def protected_endpoint(request: Request):
        # This endpoint should only be accessible with valid JWT
        return JSONResponse({"message": "success", "user": request.state.user})

    async def public_endpoint(request: Request):
        # This endpoint should be accessible without JWT
        return JSONResponse({"message": "public"})

    # Create app with JWT middleware on protected route
    app = Starlette(
        routes=[
            Route("/public", public_endpoint),
            Route("/protected", protected_endpoint),
        ],
        middleware=[
            Middleware(
                JWTAuthMiddleware,
                secret_key="test-jwt-secret-key",
                protected_paths=["/protected"],
                required_scopes=["read"],
            )
        ],
    )

    return app


@pytest.mark.asyncio
async def test_jwt_middleware_allows_public_routes(test_app_with_auth: Starlette):
    """Test that JWT middleware allows access to public routes."""
    with TestClient(test_app_with_auth) as client:
        response = client.get("/public")
        assert response.status_code == 200
        assert response.json()["message"] == "public"


@pytest.mark.asyncio
async def test_jwt_middleware_blocks_protected_without_token(
    test_app_with_auth: Starlette,
):
    """Test that JWT middleware blocks access to protected routes without token."""
    with TestClient(test_app_with_auth) as client:
        response = client.get("/protected")
        assert response.status_code == 401
        assert "error" in response.json()


@pytest.mark.asyncio
async def test_jwt_middleware_allows_protected_with_valid_token(
    test_app_with_auth: Starlette, valid_token: str
):
    """Test that JWT middleware allows access with valid token."""
    with TestClient(test_app_with_auth) as client:
        headers = {"Authorization": f"Bearer {valid_token}"}
        response = client.get("/protected", headers=headers)
        assert response.status_code == 200
        assert response.json()["message"] == "success"
        assert "user" in response.json()


@pytest.mark.asyncio
async def test_jwt_middleware_blocks_expired_token(
    test_app_with_auth: Starlette, expired_token: str
):
    """Test that JWT middleware blocks expired tokens."""
    with TestClient(test_app_with_auth) as client:
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.get("/protected", headers=headers)
        assert response.status_code == 401
        assert "error" in response.json()


@pytest.mark.asyncio
async def test_jwt_middleware_blocks_invalid_token(test_app_with_auth: Starlette):
    """Test that JWT middleware blocks invalid tokens."""
    with TestClient(test_app_with_auth) as client:
        headers = {"Authorization": "Bearer invalid.jwt.token"}
        response = client.get("/protected", headers=headers)
        assert response.status_code == 401
        assert "error" in response.json()


@pytest.mark.asyncio
async def test_jwt_middleware_blocks_malformed_auth_header(
    test_app_with_auth: Starlette,
):
    """Test that JWT middleware blocks malformed Authorization headers."""
    with TestClient(test_app_with_auth) as client:
        headers = {"Authorization": "Basic dXNlcjpwYXNz"}  # Not Bearer token
        response = client.get("/protected", headers=headers)
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_middleware_scope_validation():
    """Test JWT middleware with scope requirements."""

    async def admin_endpoint(request: Request):
        return JSONResponse({"message": "admin access"})

    # Create app with admin scope requirement
    app = Starlette(
        routes=[Route("/admin", admin_endpoint)],
        middleware=[
            Middleware(
                JWTAuthMiddleware,
                secret_key="test-jwt-secret-key",
                protected_paths=["/admin"],
                required_scopes=["admin"],
            )
        ],
    )

    # Create token with only "read" scope
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",  # Missing "admin" scope
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "mcp-anywhere",
    }
    token = jwt.encode(payload, "test-jwt-secret-key", algorithm="HS256")

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/admin", headers=headers)
        assert response.status_code == 403  # Forbidden due to insufficient scope
        assert "insufficient_scope" in response.json()["error"]


@pytest.mark.asyncio
async def test_jwt_middleware_multiple_scopes():
    """Test JWT middleware with multiple scope requirements."""

    async def multi_scope_endpoint(request: Request):
        return JSONResponse({"message": "multi scope access"})

    # Create app requiring multiple scopes
    app = Starlette(
        routes=[Route("/multi", multi_scope_endpoint)],
        middleware=[
            Middleware(
                JWTAuthMiddleware,
                secret_key="test-jwt-secret-key",
                protected_paths=["/multi"],
                required_scopes=["read", "write"],
            )
        ],
    )

    # Create token with both required scopes
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read write admin",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "mcp-anywhere",
    }
    token = jwt.encode(payload, "test-jwt-secret-key", algorithm="HS256")

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/multi", headers=headers)
        assert response.status_code == 200
        assert response.json()["message"] == "multi scope access"


@pytest.mark.asyncio
async def test_jwt_middleware_wildcard_protected_paths():
    """Test JWT middleware with wildcard protected paths."""

    async def api_endpoint(request: Request):
        return JSONResponse({"message": "api access"})

    # Create app with wildcard path protection
    app = Starlette(
        routes=[
            Route("/api/v1/test", api_endpoint),
            Route("/api/v2/test", api_endpoint),
        ],
        middleware=[
            Middleware(
                JWTAuthMiddleware,
                secret_key="test-jwt-secret-key",
                protected_paths=["/api/*"],
                required_scopes=["read"],
            )
        ],
    )

    # Create valid token
    payload = {
        "sub": "123",
        "username": "testuser",
        "scope": "read",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iss": "mcp-anywhere",
    }
    token = jwt.encode(payload, "test-jwt-secret-key", algorithm="HS256")

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}

        # Both API endpoints should require auth
        response1 = client.get("/api/v1/test", headers=headers)
        assert response1.status_code == 200

        response2 = client.get("/api/v2/test", headers=headers)
        assert response2.status_code == 200

        # Without auth should fail
        response3 = client.get("/api/v1/test")
        assert response3.status_code == 401
