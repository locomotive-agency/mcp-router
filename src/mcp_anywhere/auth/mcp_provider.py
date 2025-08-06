"""MCP SDK-based OAuth provider implementation.
Uses the MCP auth module for spec-compliant OAuth 2.0 flows.
"""

import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    OAuthAuthorizationServerProvider,
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
    """OAuth 2.0 provider that integrates MCP SDK auth with our database.
    """

    def __init__(self, db_session_factory: Callable[[], Awaitable[AsyncSession]]) -> None:
        """Initialize with a database session factory."""
        self.db_session_factory = db_session_factory
        self.auth_codes = {}  # In-memory storage for demo, use DB in production
        self.access_tokens = {}  # Token storage

    async def handle_authorization_request(
        self,
        request: Request,
        client_id: str,
        redirect_uri: str,
        state: str | None,
        scope: str,
        response_type: str,
    ) -> tuple[bool, str | None]:
        """Validate authorization request and check user authentication.
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

            # Store request details for later
            request.session["oauth_request"] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "user_id": user_id,
            }

            return True, None

    async def create_authorization_code(
        self, request: Request, client_id: str, redirect_uri: str, scope: str, user_id: str
    ) -> str:
        """Generate and store an authorization code."""
        code = secrets.token_urlsafe(32)
        expires_at = time.time() + 600  # 10 minutes

        self.auth_codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "user_id": user_id,
            "expires_at": expires_at,
        }

        return code

    async def exchange_authorization_code(
        self, code: str, client_id: str, client_secret: str, redirect_uri: str
    ) -> AccessToken | None:
        """Exchange authorization code for access token."""
        # Validate client credentials
        async with self.db_session_factory() as session:
            stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
            client = await session.scalar(stmt)

            if not client or client.client_secret != client_secret:
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

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        """Revoke an access token."""
        if token in self.access_tokens:
            del self.access_tokens[token]
            return True
        return False

    async def register_client(
        self,
        client_name: str,
        redirect_uris: list[str],
        grant_types: list[str],
        response_types: list[str],
        scope: str,
    ) -> dict[str, Any]:
        """Register a new OAuth client (optional, can be disabled).
        """
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
