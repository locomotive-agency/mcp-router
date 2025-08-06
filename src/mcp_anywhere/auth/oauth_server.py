"""OAuth 2.0 Authorization Server implementation."""

import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from mcp_anywhere.auth.models import OAuth2Client, AuthorizationCode, User
from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class SimpleAuthorizationServer:
    """Simple OAuth 2.0 Authorization Server implementation."""
    
    def __init__(self, db_session: AsyncSession):
        """Initialize the authorization server."""
        self.db_session = db_session
        self.jwt_secret = Config.JWT_SECRET_KEY
        self.jwt_algorithm = "HS256"
        self.access_token_expires_in = 3600  # 1 hour
        self.auth_code_expires_in = 600     # 10 minutes
    
    async def validate_authorize_request(self, request: Request) -> bool:
        """
        Validate OAuth 2.0 authorization request.
        
        Args:
            request: Starlette request object
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Extract required parameters
            client_id = request.query_params.get("client_id")
            redirect_uri = request.query_params.get("redirect_uri")
            response_type = request.query_params.get("response_type")
            scope = request.query_params.get("scope", "read")
            state = request.query_params.get("state")
            
            # Validate required parameters
            if not client_id or not redirect_uri or not response_type:
                logger.warning("Missing required OAuth parameters")
                return False
            
            # Validate response_type
            if response_type != "code":
                logger.warning(f"Invalid response_type: {response_type}")
                return False
            
            # Validate client_id and redirect_uri
            stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
            result = await self.db_session.execute(stmt)
            client = result.scalar_one_or_none()
            
            if not client:
                logger.warning(f"Invalid client_id: {client_id}")
                return False
            
            if client.redirect_uri != redirect_uri:
                logger.warning(f"Redirect URI mismatch. Expected: {client.redirect_uri}, Got: {redirect_uri}")
                return False
            
            # Validate scope (must be subset of client's allowed scopes)
            client_scopes = set(client.scope.split())
            requested_scopes = set(scope.split())
            if not requested_scopes.issubset(client_scopes):
                logger.warning(f"Invalid scope. Requested: {scope}, Allowed: {client.scope}")
                return False
            
            # Store validated parameters in session
            oauth_params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": response_type,
                "scope": scope,
                "state": state
            }
            request.session["oauth_params"] = oauth_params
            
            logger.info(f"OAuth authorization request validated for client: {client_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating authorization request: {e}")
            return False
    
    async def create_authorization_response(self, request: Request, grant: bool) -> RedirectResponse:
        """
        Create OAuth 2.0 authorization response.
        
        Args:
            request: Starlette request object
            grant: Whether user granted authorization
            
        Returns:
            RedirectResponse with authorization code or error
        """
        oauth_params = request.session.get("oauth_params", {})
        redirect_uri = oauth_params.get("redirect_uri")
        state = oauth_params.get("state")
        
        if not redirect_uri:
            raise ValueError("Missing OAuth parameters in session")
        
        # Build redirect URL with query parameters
        if not grant:
            # User denied access
            params = {"error": "access_denied"}
            if state:
                params["state"] = state
            
            redirect_url = f"{redirect_uri}?{urlencode(params)}"
            logger.info("User denied OAuth authorization")
            return RedirectResponse(url=redirect_url)
        
        # User granted access - generate authorization code
        try:
            user_id = request.session.get("user_id")
            if not user_id:
                raise ValueError("User not authenticated")
            
            # Generate authorization code
            auth_code = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(seconds=self.auth_code_expires_in)
            
            # Store authorization code in database
            auth_code_obj = AuthorizationCode(
                code=auth_code,
                client_id=oauth_params["client_id"],
                user_id=user_id,
                redirect_uri=oauth_params["redirect_uri"],
                scope=oauth_params["scope"],
                expires_at=expires_at
            )
            
            self.db_session.add(auth_code_obj)
            await self.db_session.commit()
            
            # Build successful redirect URL
            params = {"code": auth_code}
            if state:
                params["state"] = state
            
            redirect_url = f"{redirect_uri}?{urlencode(params)}"
            logger.info(f"Authorization code generated for client: {oauth_params['client_id']}")
            return RedirectResponse(url=redirect_url)
            
        except Exception as e:
            logger.error(f"Error creating authorization response: {e}")
            # Redirect with error
            params = {"error": "server_error"}
            if state:
                params["state"] = state
            redirect_url = f"{redirect_uri}?{urlencode(params)}"
            return RedirectResponse(url=redirect_url)
    
    async def create_token_response(self, request: Request) -> JSONResponse:
        """
        Create OAuth 2.0 token response.
        
        Args:
            request: Starlette request object
            
        Returns:
            JSONResponse with access token or error
        """
        try:
            # Parse form data
            form_data = await request.form()
            grant_type = form_data.get("grant_type")
            code = form_data.get("code")
            client_id = form_data.get("client_id")
            client_secret = form_data.get("client_secret")
            redirect_uri = form_data.get("redirect_uri")
            
            # Validate grant_type
            if grant_type != "authorization_code":
                return JSONResponse(
                    {"error": "unsupported_grant_type"},
                    status_code=400
                )
            
            # Validate required parameters
            if not all([code, client_id, client_secret, redirect_uri]):
                return JSONResponse(
                    {"error": "invalid_request", "error_description": "Missing required parameters"},
                    status_code=400
                )
            
            # Validate client credentials
            stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
            result = await self.db_session.execute(stmt)
            client = result.scalar_one_or_none()
            
            if not client or client.client_secret != client_secret:
                return JSONResponse(
                    {"error": "invalid_client"},
                    status_code=401
                )
            
            # Validate authorization code
            stmt = select(AuthorizationCode).where(AuthorizationCode.code == code)
            result = await self.db_session.execute(stmt)
            auth_code = result.scalar_one_or_none()
            
            if not auth_code:
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "Authorization code not found"},
                    status_code=400
                )
            
            # Check if code is expired
            if auth_code.is_expired():
                # Delete expired code
                await self.db_session.delete(auth_code)
                await self.db_session.commit()
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "Authorization code expired"},
                    status_code=400
                )
            
            # Validate code parameters
            if (auth_code.client_id != client_id or 
                auth_code.redirect_uri != redirect_uri):
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "Authorization code mismatch"},
                    status_code=400
                )
            
            # Generate access token
            access_token = await self._generate_access_token(auth_code.user_id, auth_code.scope, client_id)
            
            # Delete used authorization code
            await self.db_session.delete(auth_code)
            await self.db_session.commit()
            
            # Return token response
            token_response = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": self.access_token_expires_in,
                "scope": auth_code.scope
            }
            
            logger.info(f"Access token issued for client: {client_id}")
            return JSONResponse(token_response)
            
        except Exception as e:
            logger.error(f"Error creating token response: {e}")
            return JSONResponse(
                {"error": "server_error", "error_description": "Internal server error"},
                status_code=500
            )
    
    async def _generate_access_token(self, user_id: int, scope: str, client_id: str) -> str:
        """
        Generate JWT access token.
        
        Args:
            user_id: User ID
            scope: Granted scope
            client_id: Client ID
            
        Returns:
            JWT access token
        """
        # Get user information
        stmt = select(User).where(User.id == user_id)
        result = await self.db_session.execute(stmt)
        user = result.scalar_one()
        
        # Create JWT payload
        now = datetime.utcnow()
        payload = {
            "sub": str(user_id),
            "username": user.username,
            "scope": scope,
            "client_id": client_id,
            "iat": now,
            "exp": now + timedelta(seconds=self.access_token_expires_in),
            "iss": "mcp-anywhere"
        }
        
        # Generate JWT token
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token