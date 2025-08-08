"""MCP SDK-based OAuth provider implementation.
Uses the MCP auth module for spec-compliant OAuth 2.0 flows with PKCE support.
"""

import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationCodeT,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthToken
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
        # Add in-memory client cache for immediate availability (single-user system)
        self.client_cache: dict[str, OAuthClientInformationFull] = {}
        # Storage for OAuth requests during authorization flow
        self.oauth_requests: dict[str, dict[str, Any]] = {}

    async def create_authorization_code(
        self,
        request: Request,
        client_id: str,
        redirect_uri: str,
        user_id: str,
        code_challenge: str = None,
        code_challenge_method: str = None,
        scopes: list[str] = None,
        scope: str = None,
        **kwargs,  # Accept any additional parameters
    ) -> str:
        """Generate and store an authorization code with PKCE support.

        Args:
            request: The HTTP request
            client_id: OAuth client ID
            redirect_uri: Redirect URI for the code
            user_id: ID of the authenticated user
            code_challenge: PKCE code challenge (optional)
            code_challenge_method: PKCE challenge method (optional)
            scopes: List of requested scopes (optional)
            scope: Legacy scope parameter (optional)
            **kwargs: Any additional OAuth parameters

        Returns:
            Generated authorization code
        """
        code = secrets.token_urlsafe(32)
        expires_at = time.time() + 600  # 10 minutes

        # Handle scope/scopes parameter
        if scopes:
            scope_str = " ".join(scopes) if isinstance(scopes, list) else scopes
        elif scope:
            scope_str = scope
        else:
            scope_str = "mcp:read"

        self.auth_codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope_str,
            "user_id": user_id,
            "expires_at": expires_at,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }

        logger.info(f"Created authorization code for client {client_id}")
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCodeT
    ) -> OAuthToken:
        """Exchange authorization code for access token with PKCE support.

        Note: Client authentication is already handled by the vendor's ClientAuthenticator
        before this method is called, so we don't need to re-validate credentials here.
        """
        # Extract the code string from the AuthorizationCode object
        code_string = authorization_code.code

        # Validate authorization code
        auth_code_data = self.auth_codes.get(code_string)
        if not auth_code_data:
            raise TokenError("invalid_grant")

        # Check expiration
        if time.time() > auth_code_data["expires_at"]:
            del self.auth_codes[code_string]
            raise TokenError("invalid_grant")

        # Validate code parameters
        if auth_code_data["client_id"] != client.client_id or auth_code_data[
            "redirect_uri"
        ] != str(client.redirect_uris[0]):
            raise TokenError("invalid_grant")

        # Note: PKCE verification is handled by the MCP SDK token handler before calling this method
        # The MCP SDK validates the code_verifier against the code_challenge before getting here
        # So we don't need to do PKCE validation again in the provider

        # Generate access token
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time() + 3600)  # 1 hour

        access_token = AccessToken(
            token=token,
            client_id=client.client_id,
            scopes=auth_code_data["scope"].split(),
            expires_at=expires_at,
            resource=f"{Config.SERVER_URL}{Config.MCP_PATH_PREFIX}",
        )

        # Store token for introspection
        self.access_tokens[token] = access_token

        # Delete used authorization code
        del self.auth_codes[code_string]

        # Return OAuthToken for MCP SDK compatibility
        return OAuthToken(
            access_token=token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(access_token.scopes),
        )

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

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get OAuth client information by client ID.

        This method is required by the MCP SDK for client validation.
        First checks in-memory cache, then database for single-user efficiency.

        Args:
            client_id: The OAuth client ID to lookup

        Returns:
            OAuthClientInformationFull object if found, None otherwise
        """
        # First check in-memory cache for immediate availability
        if client_id in self.client_cache:
            logger.debug(f"Client found in cache: {client_id}")
            return self.client_cache[client_id]

        # Then check database
        async with self.db_session_factory() as session:
            stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
            db_client = await session.scalar(stmt)

            if not db_client:
                logger.debug(f"Client not found in database: {client_id}")
                return None

            # Convert database model to MCP SDK model and cache it
            client_info = OAuthClientInformationFull(
                client_id=db_client.client_id,
                client_secret=(
                    db_client.client_secret if db_client.is_confidential else None
                ),
                client_name=db_client.client_name,
                redirect_uris=[db_client.redirect_uri],
                grant_types=["authorization_code"],
                response_types=["code"],
                scope=db_client.scope,
            )

            # Cache for future requests
            self.client_cache[client_id] = client_info
            logger.debug(f"Client loaded from database and cached: {client_id}")
            return client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Handle authorization request by storing OAuth parameters and redirecting.

        This method is called by the MCP SDK's /authorize endpoint.
        We need to store the OAuth request parameters so our consent page can access them.

        Args:
            client: The OAuth client requesting authorization
            params: Authorization parameters from the request

        Returns:
            URL to redirect the client to (login or consent page)
        """
        logger.info(f"Authorization request for client {client.client_id}")

        # Generate a state parameter for this OAuth request
        state = params.state or secrets.token_hex(16)

        # Store OAuth request parameters for later retrieval by consent page
        # Using the same pattern as simple auth but adapted for our session-based approach
        self.oauth_requests[state] = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "code_challenge": params.code_challenge,
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "scopes": params.scopes,
            "resource": params.resource,
            "state": params.state,  # Original state from client
        }

        # Build the consent URL with state parameter so consent page can retrieve OAuth data
        base_url = str(Config.SERVER_URL).rstrip("/")
        consent_url = f"{base_url}/auth/consent?state={state}"

        logger.info(f"Stored OAuth request with state {state}, redirecting to consent")
        return consent_url

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        """Load authorization code data.

        The MCP SDK calls this with client and code parameters.

        Args:
            client: The OAuth client information
            authorization_code: The authorization code to look up

        Returns:
            AuthorizationCode object if found and valid, None otherwise
        """
        auth_code_data = self.auth_codes.get(authorization_code)
        if not auth_code_data:
            return None

        # Convert dict to AuthorizationCode object for MCP SDK
        from pydantic import AnyHttpUrl

        return AuthorizationCode(
            code=authorization_code,
            client_id=auth_code_data["client_id"],
            redirect_uri=AnyHttpUrl(auth_code_data["redirect_uri"]),
            redirect_uri_provided_explicitly=True,
            expires_at=auth_code_data["expires_at"],
            scopes=auth_code_data["scope"].split() if auth_code_data["scope"] else [],
            code_challenge=auth_code_data.get("code_challenge"),
            resource=None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Load access token for introspection.

        Args:
            token: The access token to look up

        Returns:
            AccessToken object if found and valid, None otherwise
        """
        return await self.introspect_token(token)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        """Load refresh token.

        Args:
            client: The OAuth client
            refresh_token: The refresh token to look up

        Returns:
            RefreshToken object if found, None otherwise
        """
        # We don't currently support refresh tokens in this implementation
        return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken
    ) -> AccessToken:
        """Exchange refresh token for new access token.

        Args:
            client: The OAuth client
            refresh_token: The refresh token to exchange

        Returns:
            New AccessToken

        Raises:
            TokenError: If refresh token is invalid
        """
        # We don't currently support refresh tokens in this implementation
        raise TokenError("unsupported_grant_type")

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Register a new OAuth client.

        The MCP SDK generates the client_id and passes it in client_info.
        We must use the provided client_id, not generate our own.
        For single-user systems, cache immediately for availability.

        Args:
            client_info: Complete client information including client_id generated by MCP SDK
        """
        logger.info(f"Registering OAuth client: {client_info.client_id}")

        # Cache immediately for MCP SDK availability (single-user system)
        self.client_cache[client_info.client_id] = client_info

        # Also persist to database
        client_id = client_info.client_id
        client_secret = client_info.client_secret  # Keep None for public clients
        client_name = client_info.client_name or "Unknown Client"
        redirect_uris = [str(url) for url in (client_info.redirect_uris or [])]
        scope = client_info.scope or "mcp:read mcp:write"

        # Determine if client is confidential (has a secret)
        is_confidential = client_secret is not None

        async with self.db_session_factory() as session:
            client = OAuth2Client(
                client_id=client_id,
                client_secret=client_secret,
                client_name=client_name,
                redirect_uri=redirect_uris[0] if redirect_uris else "",
                scope=scope,
                is_confidential=is_confidential,
            )
            session.add(client)
            await session.commit()
            logger.info(f"Successfully registered and cached client {client_id}")
