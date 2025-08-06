"""
Test the Authlib OAuth flow end-to-end.

This module tests the OAuth authentication flows as specified in Phase 4
of the engineering documentation.
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_anywhere.auth.models import OAuth2Client, User


async def test_login_and_session(client: httpx.AsyncClient, db_session: AsyncSession):
    """
    Tests the /auth/login endpoint and verifies that a session cookie is set.

    Args:
        client: HTTP test client
        db_session: Database session with test data
    """
    # Create test user
    test_user = User(username="testuser")
    test_user.set_password("testpassword")
    db_session.add(test_user)
    await db_session.commit()

    # Mock the database session in the route handler
    with patch("mcp_anywhere.auth.routes.Request.app") as mock_app:
        mock_app.state.get_async_session.return_value.__aenter__.return_value = db_session

        # Test GET request to login page
        response = await client.get("/auth/login")
        assert response.status_code == 200
        assert "login" in response.text.lower()

        # Test POST request with valid credentials
        form_data = {"username": "testuser", "password": "testpassword"}

        response = await client.post("/auth/login", data=form_data)

        # Should redirect on successful login
        assert response.status_code == 302

        # Verify session cookie is set
        cookies = response.cookies
        assert "session" in cookies or "mcp_session" in cookies  # Check for session cookie

        # Test POST request with invalid credentials
        invalid_form_data = {"username": "testuser", "password": "wrongpassword"}

        response = await client.post("/auth/login", data=invalid_form_data)

        # Should return error
        assert response.status_code == 200
        assert "error" in response.text.lower() or "invalid" in response.text.lower()


async def test_full_auth_code_flow(client: httpx.AsyncClient, db_session: AsyncSession):
    """
    A complex test that simulates a third-party client obtaining a token by making
    sequential requests to /auth/authorize and /auth/token.

    Args:
        client: HTTP test client
        db_session: Database session
    """
    # Create test user
    test_user = User(username="oauth_user")
    test_user.set_password("oauth_password")
    db_session.add(test_user)

    # Create test OAuth client
    test_client = OAuth2Client(
        client_id="test_client_id",
        client_secret="test_client_secret",
        client_name="Test OAuth Client",
        redirect_uris=["http://localhost:3000/callback"],
        scopes=["read", "write"],
        grant_types=["authorization_code"],
    )
    db_session.add(test_client)
    await db_session.commit()

    # Mock the database session in route handlers
    with patch("mcp_anywhere.auth.routes.Request.app") as mock_app:
        mock_app.state.get_async_session.return_value.__aenter__.return_value = db_session

        # Step 1: Login user to establish session
        login_response = await client.post(
            "/auth/login", data={"username": "oauth_user", "password": "oauth_password"}
        )
        assert login_response.status_code == 302

        # Step 2: Initiate authorization request
        auth_params = {
            "response_type": "code",
            "client_id": "test_client_id",
            "redirect_uri": "http://localhost:3000/callback",
            "scope": "read write",
            "state": "random_state_value",
        }

        # GET authorization endpoint
        auth_response = await client.get("/auth/authorize", params=auth_params)

        # Should show consent page or redirect if already authorized
        assert auth_response.status_code in [200, 302]

        if auth_response.status_code == 200:
            # If consent page is shown, submit consent
            consent_data = {
                "client_id": "test_client_id",
                "response_type": "code",
                "redirect_uri": "http://localhost:3000/callback",
                "scope": "read write",
                "state": "random_state_value",
                "consent": "approve",
            }

            auth_response = await client.post("/auth/authorize", data=consent_data)

        # Should redirect with authorization code
        assert auth_response.status_code == 302
        redirect_location = auth_response.headers["location"]

        # Parse authorization code from redirect URL
        parsed_url = urlparse(redirect_location)
        query_params = parse_qs(parsed_url.query)

        assert "code" in query_params
        auth_code = query_params["code"][0]
        assert "state" in query_params
        assert query_params["state"][0] == "random_state_value"

        # Step 3: Exchange authorization code for access token
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
        }

        token_response = await client.post("/auth/token", data=token_data)

        # Should return access token
        assert token_response.status_code == 200
        token_json = token_response.json()

        assert "access_token" in token_json
        assert "token_type" in token_json
        assert token_json["token_type"] == "Bearer"
        assert "expires_in" in token_json

        # Verify token is valid (basic structure check)
        access_token = token_json["access_token"]
        assert len(access_token) > 10  # Basic sanity check

        # Step 4: Test invalid authorization code
        invalid_token_data = {
            "grant_type": "authorization_code",
            "code": "invalid_code",
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
        }

        invalid_response = await client.post("/auth/token", data=invalid_token_data)
        assert invalid_response.status_code == 400

        error_json = invalid_response.json()
        assert "error" in error_json
