"""MCP SDK-based OAuth provider implementation.
Uses the MCP auth module for spec-compliant OAuth 2.0 flows with PKCE support.
"""

import hashlib
import base64
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
    TokenError,
    TokenErrorCode,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from mcp_anywhere.auth.models import OAuth2Client
from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class MCPAnywhereAuthProvider(OAuthAuthorizationServerProvider):
    """OAuth 2.0 provider that integrates MCP SDK auth with our database with PKCE support."""

    def __init__(
        self, db_session_factory: Callable[[], Awaitable[AsyncSession]]
    ) -> None:
        """Initialize with a database session factory."""
        self.db_session_factory = db_session_factory
        self.auth_codes = {}  # In-memory storage for demo, use DB in production
        self.access_tokens = {}  # Token storage

    @staticmethod
    def _verify_pkce_challenge(
        code_verifier: str, code_challenge: str, method: str = "S256"
    ) -> bool:
        """Verify PKCE code challenge.

        Args:
            code_verifier: The plaintext code verifier from the client
            code_challenge: The stored code challenge
            method: The challenge method (S256 or plain)

        Returns:
            True if the verifier matches the challenge
        """
        if method == "plain":
            return code_verifier == code_challenge
        elif method == "S256":
            # Generate SHA256 hash of the verifier
            verifier_hash = hashlib.sha256(code_verifier.encode()).digest()
            # Base64url encode without padding
            computed_challenge = (
                base64.urlsafe_b64encode(verifier_hash).decode().rstrip("=")
            )
            return computed_challenge == code_challenge
        else:
            logger.warning(f"Unknown PKCE challenge method: {method}")
            return False

    async def handle_authorization_request(
        self,
        request: Request,
        client_id: str,
        redirect_uri: str,
        state: str | None,
        scope: str,
        response_type: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> tuple[bool, str | None]:
        """Validate authorization request and check user authentication with PKCE support.
        Returns (is_valid, error_message).
        """
        async with self.db_session_factory() as session:
            # Validate client
            stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
            client = await session.scalar(stmt)

            if not client:
                return False, "invalid_client"

            if client.redirect_uri != redirect_uri:
                return False, "invalid_redirect_uri"

            # Check if user is authenticated (via session)
            user_id = request.session.get("user_id")
            if not user_id:
                return False, "login_required"

            # Validate PKCE parameters if provided
            if code_challenge:
                if code_challenge_method not in ["S256", "plain", None]:
                    return False, "invalid_request"
                # Default to S256 if method not specified
                if not code_challenge_method:
                    code_challenge_method = "S256"

            # Store request details for later including PKCE parameters
            request.session["oauth_request"] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "user_id": user_id,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            }

            return True, None

    async def create_authorization_code(
        self,
        request: Request,
        client_id: str,
        redirect_uri: str,
        scope: str,
        user_id: str,
    ) -> str:
        """Generate and store an authorization code with PKCE support."""
        code = secrets.token_urlsafe(32)
        expires_at = time.time() + 600  # 10 minutes

        # Get PKCE parameters from session if present
        oauth_request = request.session.get("oauth_request", {})
        code_challenge = oauth_request.get("code_challenge")
        code_challenge_method = oauth_request.get("code_challenge_method")

        self.auth_codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "user_id": user_id,
            "expires_at": expires_at,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }

        return code

    async def exchange_authorization_code(
        self,
        code: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> AccessToken | None:
        """Exchange authorization code for access token with PKCE support."""
        # Validate client credentials
        async with self.db_session_factory() as session:
            stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
            client = await session.scalar(stmt)

            if not client:
                raise TokenError(TokenErrorCode.INVALID_CLIENT)

            # Only check client_secret for confidential clients (non-PKCE flows)
            if client.is_confidential and client.client_secret != client_secret:
                raise TokenError(TokenErrorCode.INVALID_CLIENT)

        # Validate authorization code
        auth_code_data = self.auth_codes.get(code)
        if not auth_code_data:
            raise TokenError(TokenErrorCode.INVALID_GRANT)

        # Check expiration
        if time.time() > auth_code_data["expires_at"]:
            del self.auth_codes[code]
            raise TokenError(TokenErrorCode.INVALID_GRANT)

        # Validate code parameters
        if (
            auth_code_data["client_id"] != client_id
            or auth_code_data["redirect_uri"] != redirect_uri
        ):
            raise TokenError(TokenErrorCode.INVALID_GRANT)

        # Verify PKCE if code challenge was stored
        if auth_code_data.get("code_challenge"):
            if not code_verifier:
                logger.warning("PKCE verification failed: missing code_verifier")
                raise TokenError(TokenErrorCode.INVALID_GRANT)

            if not self._verify_pkce_challenge(
                code_verifier,
                auth_code_data["code_challenge"],
                auth_code_data.get("code_challenge_method", "S256"),
            ):
                logger.warning("PKCE verification failed: invalid code_verifier")
                raise TokenError(TokenErrorCode.INVALID_GRANT)

        # Generate access token
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time() + 3600)  # 1 hour

        access_token = AccessToken(
            token=token,
            client_id=client_id,
            scopes=auth_code_data["scope"].split(),
            expires_at=expires_at,
            resource=f"{Config.SERVER_URL}/mcp",
        )

        # Store token for introspection
        self.access_tokens[token] = access_token

        # Delete used authorization code
        del self.auth_codes[code]

        return access_token

    async def introspect_token(self, token: str) -> AccessToken | None:
        """Introspect an access token for resource server validation.
        Required for the introspection endpoint.
        """
        access_token = self.access_tokens.get(token)

        if not access_token:
            return None

        # Check expiration
        if time.time() > access_token.expires_at:
            del self.access_tokens[token]
            return None

        return access_token

    async def revoke_token(
        self, token: str, token_type_hint: str | None = None
    ) -> bool:
        """Revoke an access token."""
        if token in self.access_tokens:
            del self.access_tokens[token]
            return True
        return False

    async def register_client(
        self, client_info: OAuthClientInformationFull
    ) -> dict[str, Any]:
        """Register a new OAuth client (optional, can be disabled)."""
        # Extract fields from the Pydantic model with sensible defaults
        client_name = getattr(client_info, "client_name", "Unknown Client")
        redirect_uris = getattr(client_info, "redirect_uris", [])
        grant_types = getattr(client_info, "grant_types", ["authorization_code"])
        response_types = getattr(client_info, "response_types", ["code"])
        scope = getattr(client_info, "scope", "mcp:read mcp:write")
        
        client_id = secrets.token_urlsafe(16)
        client_secret = secrets.token_urlsafe(32)

        async with self.db_session_factory() as session:
            client = OAuth2Client(
                client_id=client_id,
                client_secret=client_secret,
                client_name=client_name,
                redirect_uri=redirect_uris[0] if redirect_uris else "",
                scope=scope,
            )
            session.add(client)
            await session.commit()

        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "response_types": response_types,
            "scope": scope,
        }
