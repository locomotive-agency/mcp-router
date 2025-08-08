"""Test critical OAuth fixes to ensure they work correctly.

This module tests the specific fixes made to address the senior engineer's
blocking issues in the OAuth implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_anywhere.auth.provider import MCPAnywhereAuthProvider
from mcp_anywhere.web.app import MCPAuthMiddleware
from mcp.server.auth.provider import OAuthClientInformationFull


class TestOAuthFixes:
    """Test the critical OAuth fixes that were implemented."""
    
    def test_introspect_token_method_exists(self):
        """Test that the provider has the introspect_token method used by middleware."""
        provider = MCPAnywhereAuthProvider(AsyncMock())
        
        # The method should exist
        assert hasattr(provider, 'introspect_token')
        assert callable(getattr(provider, 'introspect_token'))
        
        # The old verify_token method should NOT exist
        assert not hasattr(provider, 'verify_token')
    
    @pytest.mark.asyncio
    async def test_middleware_uses_introspect_token(self):
        """Test that the middleware correctly uses introspect_token."""
        # Create mock provider with introspect_token
        mock_provider = AsyncMock()
        mock_provider.introspect_token = AsyncMock(return_value=None)  # Invalid token
        
        # Create mock request
        mock_request = MagicMock()
        mock_request.url.path = "/mcp/test"
        mock_request.headers.get.return_value = "Bearer invalid_token"
        mock_request.app.state.oauth_provider = mock_provider
        
        # Create middleware
        middleware = MCPAuthMiddleware(app=None)
        
        # Create mock call_next
        call_next = AsyncMock()
        
        # Test the middleware
        response = await middleware.dispatch(mock_request, call_next)
        
        # Should have called introspect_token with the token
        mock_provider.introspect_token.assert_called_once_with("invalid_token")
        
        # Should return 401 for invalid token
        assert isinstance(response, JSONResponse)
        assert response.status_code == 401
        
        # Should not have called the next middleware
        call_next.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_exchange_authorization_code_returns_oauth_token(self):
        """Test that exchange_authorization_code returns OAuthToken, not AccessToken."""
        from mcp.shared.auth import OAuthToken
        from mcp.server.auth.provider import AuthorizationCode
        from pydantic import AnyHttpUrl
        from contextlib import asynccontextmanager
        
        # Mock database session factory
        @asynccontextmanager
        async def mock_session_factory():
            from mcp_anywhere.auth.models import OAuth2Client
            
            mock_session = AsyncMock()
            # Mock OAuth2Client from database
            db_client = OAuth2Client()
            db_client.client_id = "test_client"
            db_client.client_secret = None
            db_client.is_confidential = False
            
            mock_session.scalar = AsyncMock(return_value=db_client)
            yield mock_session
        
        # Create provider with proper session factory
        provider = MCPAnywhereAuthProvider(mock_session_factory)
        
        # Set up test data
        client = OAuthClientInformationFull(
            client_id="test_client",
            client_secret=None,
            client_name="Test Client",
            redirect_uris=[AnyHttpUrl("http://localhost:3000/callback")],
            grant_types=["authorization_code"],
            response_types=["code"],
            scope="mcp:read"
        )
        
        # Add client to provider cache so it can be found
        provider.client_cache["test_client"] = client
        
        # Create a mock authorization code in the provider's storage
        test_code = "test_code_123"
        provider.auth_codes[test_code] = {
            "client_id": "test_client",
            "redirect_uri": "http://localhost:3000/callback",
            "user_id": 1,
            "expires_at": 9999999999,  # Future timestamp
            "scope": "mcp:read"
        }
        
        # Create AuthorizationCode object
        auth_code = AuthorizationCode(
            code=test_code,
            client_id="test_client",
            scopes=["mcp:read"],
            expires_at=9999999999,
            redirect_uri=AnyHttpUrl("http://localhost:3000/callback"),
            redirect_uri_provided_explicitly=True,
            code_challenge="test_challenge",
            resource="http://localhost:8000/mcp"
        )
        
        # Test the exchange
        result = await provider.exchange_authorization_code(client, auth_code)
        
        # Should return OAuthToken, not AccessToken
        assert isinstance(result, OAuthToken)
        
        # Should have correct fields
        assert result.access_token is not None
        assert result.token_type == "Bearer"
        assert result.expires_in == 3600
        assert result.scope == "mcp:read"
    
    def test_csrf_cleanup_scheduled(self):
        """Test that CSRF cleanup is properly configured."""
        from mcp_anywhere.auth.csrf import CSRFProtection
        
        # Create CSRF protection instance
        csrf = CSRFProtection(expiration_seconds=600)
        
        # The cleanup method should exist and be callable
        assert hasattr(csrf, 'cleanup_expired')
        assert callable(csrf.cleanup_expired)
        
        # Should be able to get active state count
        assert csrf.get_active_state_count() == 0
        
        # Generate a state to test cleanup works
        state = csrf.generate_state("client_123", "http://localhost:3000/callback")
        assert csrf.get_active_state_count() == 1
        
        # Cleanup shouldn't remove non-expired states
        csrf.cleanup_expired()
        assert csrf.get_active_state_count() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])