"""JWT token verification for OAuth 2.0 access tokens."""

from typing import Optional, Dict, Any
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError, InvalidSignatureError

from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


class TokenVerifier:
    """JWT token verifier for OAuth 2.0 access tokens."""
    
    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize the token verifier.
        
        Args:
            secret_key: JWT secret key. If None, uses Config.JWT_SECRET_KEY
        """
        self.secret_key = secret_key or Config.JWT_SECRET_KEY
        self.algorithm = "HS256"
        self.expected_issuer = "mcp-anywhere"
    
    def verify(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode a JWT access token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload if valid, None otherwise
        """
        try:
            # Decode and verify the token
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "require": ["sub", "exp", "iat", "iss"]
                },
                issuer=self.expected_issuer
            )
            
            logger.debug(f"Successfully verified token for user: {payload.get('sub')}")
            return payload
            
        except ExpiredSignatureError:
            logger.warning("Token verification failed: Token has expired")
            return None
            
        except InvalidSignatureError:
            logger.warning("Token verification failed: Invalid signature")
            return None
            
        except InvalidTokenError as e:
            logger.warning(f"Token verification failed: {str(e)}")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error during token verification: {str(e)}")
            return None
    
    def extract_bearer_token(self, authorization_header: Optional[str]) -> Optional[str]:
        """
        Extract bearer token from Authorization header.
        
        Args:
            authorization_header: HTTP Authorization header value
            
        Returns:
            JWT token string if valid bearer token, None otherwise
        """
        if not authorization_header:
            return None
        
        # Check if it's a Bearer token
        if not authorization_header.startswith("Bearer "):
            return None
        
        # Extract token part
        token = authorization_header[7:].strip()  # Remove "Bearer " prefix
        
        if not token:
            return None
        
        return token
    
    def verify_bearer_token(self, authorization_header: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Extract and verify bearer token from Authorization header.
        
        Args:
            authorization_header: HTTP Authorization header value
            
        Returns:
            Decoded token payload if valid, None otherwise
        """
        token = self.extract_bearer_token(authorization_header)
        if not token:
            return None
        
        return self.verify(token)
    
    def has_scope(self, token_payload: Dict[str, Any], required_scope: str) -> bool:
        """
        Check if token has required scope.
        
        Args:
            token_payload: Decoded JWT token payload
            required_scope: Required scope string
            
        Returns:
            True if token has required scope, False otherwise
        """
        token_scopes = token_payload.get("scope", "").split()
        return required_scope in token_scopes
    
    def has_any_scope(self, token_payload: Dict[str, Any], required_scopes: list) -> bool:
        """
        Check if token has any of the required scopes.
        
        Args:
            token_payload: Decoded JWT token payload
            required_scopes: List of required scope strings
            
        Returns:
            True if token has any required scope, False otherwise
        """
        token_scopes = set(token_payload.get("scope", "").split())
        required_scopes_set = set(required_scopes)
        return bool(token_scopes.intersection(required_scopes_set))
    
    def has_all_scopes(self, token_payload: Dict[str, Any], required_scopes: list) -> bool:
        """
        Check if token has all required scopes.
        
        Args:
            token_payload: Decoded JWT token payload
            required_scopes: List of required scope strings
            
        Returns:
            True if token has all required scopes, False otherwise
        """
        token_scopes = set(token_payload.get("scope", "").split())
        required_scopes_set = set(required_scopes)
        return required_scopes_set.issubset(token_scopes)