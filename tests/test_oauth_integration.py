"""Integration test for the complete OAuth flow.

This test simulates the full OAuth 2.0 authorization code flow with PKCE
that MCP Inspector would use to authenticate with our server.
"""

import base64
import hashlib
import secrets
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import AnyHttpUrl

from mcp_anywhere.auth.csrf import CSRFProtection
from mcp_anywhere.auth.models import OAuth2Client, User
from mcp_anywhere.auth.provider import MCPAnywhereAuthProvider


class TestOAuthIntegrationFlow:
    """Test the complete OAuth integration flow."""

    def setup_method(self):
        """Set up test fixtures for each test method."""

        # Mock database session factory
        @asynccontextmanager
        async def mock_session_factory():
            mock_session = AsyncMock()

            # Mock OAuth2Client from database
            db_client = OAuth2Client()
            db_client.client_id = "test_client_123"
            db_client.client_secret = None
            db_client.is_confidential = False
            db_client.redirect_uri = "http://localhost:3000/callback"

            # Mock User from database
            test_user = User()
            test_user.id = 1
            test_user.username = "admin"
            test_user.password_hash = "test_hash"

            # Configure mock to return appropriate objects
            def mock_scalar_side_effect(stmt):
                # Simple way to distinguish queries - in real scenarios you'd check the statement
                if hasattr(stmt, "compile") and "oauth2_clients" in str(
                    stmt.compile(compile_kwargs={"literal_binds": True})
                ):
                    return db_client
                return test_user

            mock_session.scalar = AsyncMock(side_effect=mock_scalar_side_effect)
            mock_session.add = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        # Create provider with mocked session
        self.provider = MCPAnywhereAuthProvider(mock_session_factory)

        # Create CSRF protection
        self.csrf_protection = CSRFProtection(expiration_seconds=600)

        # PKCE parameters for testing
        self.code_verifier = (
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        )
        self.code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(self.code_verifier.encode()).digest()
            )
            .decode()
            .rstrip("=")
        )

    @pytest.mark.asyncio
    async def test_step1_client_registration(self):
        """Test Step 1: OAuth client registration."""
        from mcp.server.auth.provider import OAuthClientInformationFull

        # Simulate client registration request
        client_info = OAuthClientInformationFull(
            client_id="test_client_123",
            client_secret=None,  # Public client
            client_name="MCP Inspector Test",
            redirect_uris=[AnyHttpUrl("http://localhost:3000/callback")],
            grant_types=["authorization_code"],
            response_types=["code"],
            scope="mcp:read mcp:write",
        )

        # Register the client
        await self.provider.register_client(client_info)

        # Verify client is cached
        cached_client = await self.provider.get_client("test_client_123")
        assert cached_client is not None
        assert cached_client.client_id == "test_client_123"
        assert cached_client.client_secret is None  # Public client
        assert "http://localhost:3000/callback" in [
            str(uri) for uri in cached_client.redirect_uris
        ]

        print("✅ Step 1: Client registration successful")

    @pytest.mark.asyncio
    async def test_step2_authorization_request(self):
        """Test Step 2: Authorization request with PKCE."""
        from mcp.server.auth.provider import (
            AuthorizationParams,
            OAuthClientInformationFull,
        )

        # First register the client
        client_info = OAuthClientInformationFull(
            client_id="test_client_123",
            client_secret=None,
            client_name="MCP Inspector Test",
            redirect_uris=[AnyHttpUrl("http://localhost:3000/callback")],
            grant_types=["authorization_code"],
            response_types=["code"],
            scope="mcp:read",
        )
        await self.provider.register_client(client_info)

        # Create authorization parameters (what MCP Inspector would send)
        auth_params = AuthorizationParams(
            redirect_uri=AnyHttpUrl("http://localhost:3000/callback"),
            redirect_uri_provided_explicitly=True,
            scopes=["mcp:read"],
            state="client_state_123",
            code_challenge=self.code_challenge,
            code_challenge_method="S256",
            resource="http://localhost:8000/mcp",
        )

        # Process authorization request
        consent_url = await self.provider.authorize(client_info, auth_params)

        # Verify redirect URL format
        assert consent_url.startswith("http://localhost:8000/auth/consent?state=")

        # Extract internal state parameter
        parsed = urlparse(consent_url)
        query_params = parse_qs(parsed.query)
        internal_state = query_params["state"][0]

        # Verify OAuth request is stored
        oauth_request = self.provider.oauth_requests.get(internal_state)
        assert oauth_request is not None
        assert oauth_request["client_id"] == "test_client_123"
        assert oauth_request["code_challenge"] == self.code_challenge
        assert oauth_request["state"] == "client_state_123"

        print("✅ Step 2: Authorization request successful")
        return internal_state, oauth_request

    @pytest.mark.asyncio
    async def test_step3_consent_approval(self):
        """Test Step 3: User consent approval."""
        # First do authorization request
        internal_state, oauth_request = await self.test_step2_authorization_request()

        # Add user_id to simulate authenticated admin
        oauth_request["user_id"] = 1

        # Generate CSRF state for consent form
        csrf_state = self.csrf_protection.generate_state(
            oauth_request["client_id"], oauth_request["redirect_uri"]
        )

        # Simulate consent approval
        mock_request = MagicMock()
        mock_request.session = {"csrf_state": csrf_state}

        # Create authorization code
        auth_code = await self.provider.create_authorization_code(
            request=mock_request,
            client_id=oauth_request["client_id"],
            redirect_uri=oauth_request["redirect_uri"],
            user_id=oauth_request["user_id"],
            code_challenge=oauth_request["code_challenge"],
            code_challenge_method="S256",
            scope="mcp:read",
        )

        # Verify authorization code exists
        assert auth_code in self.provider.auth_codes
        code_data = self.provider.auth_codes[auth_code]
        assert code_data["client_id"] == "test_client_123"
        assert code_data["code_challenge"] == self.code_challenge

        print("✅ Step 3: Consent approval successful")
        return auth_code, code_data

    @pytest.mark.asyncio
    async def test_step4_token_exchange(self):
        """Test Step 4: Authorization code for token exchange."""
        from mcp.server.auth.provider import AuthorizationCode
        from mcp.shared.auth import OAuthToken

        # First get authorization code
        auth_code_string, code_data = await self.test_step3_consent_approval()

        # Get client info
        client_info = await self.provider.get_client("test_client_123")

        # Create AuthorizationCode object (what MCP SDK creates)
        auth_code = AuthorizationCode(
            code=auth_code_string,
            client_id="test_client_123",
            scopes=["mcp:read"],
            expires_at=code_data["expires_at"],
            redirect_uri=AnyHttpUrl("http://localhost:3000/callback"),
            redirect_uri_provided_explicitly=True,
            code_challenge=self.code_challenge,
            resource="http://localhost:8000/mcp",
        )

        # Exchange authorization code for token
        oauth_token = await self.provider.exchange_authorization_code(
            client_info, auth_code
        )

        # Verify token response
        assert isinstance(oauth_token, OAuthToken)
        assert oauth_token.access_token is not None
        assert oauth_token.token_type == "Bearer"
        assert oauth_token.expires_in == 3600
        assert oauth_token.scope == "mcp:read"

        # Verify authorization code was consumed
        assert auth_code_string not in self.provider.auth_codes

        # Verify token is stored for introspection
        access_token_obj = await self.provider.introspect_token(
            oauth_token.access_token
        )
        assert access_token_obj is not None
        assert access_token_obj.client_id == "test_client_123"

        print("✅ Step 4: Token exchange successful")
        return oauth_token

    @pytest.mark.asyncio
    async def test_step5_token_introspection(self):
        """Test Step 5: Token validation for MCP requests."""
        # First get access token
        oauth_token = await self.test_step4_token_exchange()

        # Test token introspection (what middleware uses)
        access_token_obj = await self.provider.introspect_token(
            oauth_token.access_token
        )

        # Verify token is valid
        assert access_token_obj is not None
        assert access_token_obj.token == oauth_token.access_token
        assert access_token_obj.client_id == "test_client_123"
        assert "mcp:read" in access_token_obj.scopes

        # Test invalid token
        invalid_token_result = await self.provider.introspect_token("invalid_token_123")
        assert invalid_token_result is None

        print("✅ Step 5: Token introspection successful")

    @pytest.mark.asyncio
    async def test_complete_oauth_flow(self):
        """Test the complete OAuth flow end-to-end."""
        print("\n🚀 Testing Complete OAuth Flow")
        print("=" * 50)

        # Run all steps in sequence
        await self.test_step1_client_registration()
        await self.test_step2_authorization_request()
        await self.test_step3_consent_approval()
        oauth_token = await self.test_step4_token_exchange()
        await self.test_step5_token_introspection()

        print("\n✅ Complete OAuth Flow Test PASSED")
        print("=" * 50)
        print(f"Final Access Token: {oauth_token.access_token[:20]}...")
        print(f"Token Type: {oauth_token.token_type}")
        print(f"Expires In: {oauth_token.expires_in} seconds")
        print(f"Scope: {oauth_token.scope}")

        return oauth_token

    def test_csrf_protection_integration(self):
        """Test CSRF protection integration."""
        # Generate state
        state = self.csrf_protection.generate_state(
            "test_client", "http://localhost:3000/callback"
        )

        # Verify state is valid
        assert self.csrf_protection.validate_state(
            state, "test_client", "http://localhost:3000/callback"
        )

        # Verify state is consumed (one-time use)
        assert not self.csrf_protection.validate_state(
            state, "test_client", "http://localhost:3000/callback"
        )

        print("✅ CSRF protection integration successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
