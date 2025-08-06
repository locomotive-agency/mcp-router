"""Authentication and authorization models for OAuth 2.0 implementation."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
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
    """OAuth 2.0 client model."""

    __tablename__ = "oauth2_clients"

    id = Column(Integer, primary_key=True)
    client_id = Column(String(48), unique=True, nullable=False, index=True)
    client_secret = Column(String(120), nullable=False)
    redirect_uri = Column(String(255), nullable=False)
    scope = Column(String(255), nullable=False, default="read")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert client to dictionary representation."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuthorizationCode(Base):
    """Temporary authorization codes for OAuth 2.0 flow."""

    __tablename__ = "authorization_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(128), unique=True, nullable=False, index=True)
    client_id = Column(String(48), nullable=False)
    user_id = Column(Integer, nullable=False)
    redirect_uri = Column(String(255), nullable=False)
    scope = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
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
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
