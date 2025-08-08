"""Authentication and authorization models for OAuth 2.0 implementation."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from werkzeug.security import check_password_hash, generate_password_hash

from mcp_anywhere.base import Base


class User(Base):
    """User model for authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        """Set password with proper hashing."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check if provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        """Convert user to dictionary representation."""
        return {
            "id": self.id,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OAuth2Client(Base):
    """OAuth 2.0 client model with support for dynamic registration and PKCE."""

    __tablename__ = "oauth2_clients"

    id = Column(Integer, primary_key=True)
    client_id = Column(String(48), unique=True, nullable=False, index=True)
    client_secret = Column(String(120), nullable=True)  # Can be null for public clients
    client_name = Column(String(255), nullable=True)
    redirect_uri = Column(Text, nullable=False)  # Can store multiple URIs as JSON
    scope = Column(String(255), nullable=False, default="read")
    grant_types = Column(String(255), nullable=False, default="authorization_code")
    response_types = Column(String(255), nullable=False, default="code")
    token_endpoint_auth_method = Column(
        String(50), nullable=False, default="client_secret_basic"
    )
    is_confidential = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        """Convert client to dictionary representation."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "grant_types": self.grant_types,
            "response_types": self.response_types,
            "token_endpoint_auth_method": self.token_endpoint_auth_method,
            "is_confidential": self.is_confidential,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AuthorizationCode(Base):
    """Temporary authorization codes for OAuth 2.0 flow with PKCE support."""

    __tablename__ = "authorization_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(128), unique=True, nullable=False, index=True)
    client_id = Column(
        String(48), ForeignKey("oauth2_clients.client_id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    redirect_uri = Column(String(500), nullable=False)
    scope = Column(String(255), nullable=False)
    code_challenge = Column(String(128), nullable=True)  # PKCE support
    code_challenge_method = Column(String(10), nullable=True)  # S256 or plain
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def is_expired(self) -> bool:
        """Check if the authorization code has expired."""
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> dict:
        """Convert authorization code to dictionary representation."""
        return {
            "id": self.id,
            "code": self.code,
            "client_id": self.client_id,
            "user_id": self.user_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "code_challenge": self.code_challenge,
            "code_challenge_method": self.code_challenge_method,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_used": self.is_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OAuth2Token(Base):
    """Persistent storage for OAuth 2.0 access tokens."""

    __tablename__ = "oauth2_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    token_type = Column(String(20), nullable=False, default="Bearer")
    client_id = Column(
        String(48), ForeignKey("oauth2_clients.client_id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scope = Column(String(255), nullable=False)
    resource = Column(String(500), nullable=True)  # Resource server URL
    expires_at = Column(DateTime, nullable=False, index=True)
    is_revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    def is_expired(self) -> bool:
        """Check if the access token has expired."""
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """Check if the token is valid (not expired and not revoked)."""
        return not self.is_expired() and not self.is_revoked

    def to_dict(self) -> dict:
        """Convert token to dictionary representation."""
        return {
            "id": self.id,
            "token": self.token,
            "token_type": self.token_type,
            "client_id": self.client_id,
            "user_id": self.user_id,
            "scope": self.scope,
            "resource": self.resource,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_revoked": self.is_revoked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
        }


class OAuth2RefreshToken(Base):
    """Persistent storage for OAuth 2.0 refresh tokens."""

    __tablename__ = "oauth2_refresh_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    access_token_id = Column(
        Integer, ForeignKey("oauth2_tokens.id"), nullable=False, index=True
    )
    client_id = Column(
        String(48), ForeignKey("oauth2_clients.client_id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scope = Column(String(255), nullable=False)
    expires_at = Column(
        DateTime, nullable=True
    )  # Refresh tokens can be long-lived or never expire
    is_revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    def is_expired(self) -> bool:
        """Check if the refresh token has expired."""
        if self.expires_at is None:
            return False  # Never expires
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """Check if the refresh token is valid (not expired and not revoked)."""
        return not self.is_expired() and not self.is_revoked

    def to_dict(self) -> dict:
        """Convert refresh token to dictionary representation."""
        return {
            "id": self.id,
            "token": self.token,
            "access_token_id": self.access_token_id,
            "client_id": self.client_id,
            "user_id": self.user_id,
            "scope": self.scope,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_revoked": self.is_revoked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
        }


# Database indexes for optimal OAuth performance
Index(
    "idx_auth_codes_client_user", AuthorizationCode.client_id, AuthorizationCode.user_id
)
Index("idx_auth_codes_expires", AuthorizationCode.expires_at, AuthorizationCode.is_used)
Index("idx_tokens_client_user", OAuth2Token.client_id, OAuth2Token.user_id)
Index("idx_tokens_expires_revoked", OAuth2Token.expires_at, OAuth2Token.is_revoked)
Index(
    "idx_refresh_tokens_client_user",
    OAuth2RefreshToken.client_id,
    OAuth2RefreshToken.user_id,
)
Index(
    "idx_refresh_tokens_expires_revoked",
    OAuth2RefreshToken.expires_at,
    OAuth2RefreshToken.is_revoked,
)
