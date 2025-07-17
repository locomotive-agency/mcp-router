"""Database models for MCP Router"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, text
from mcp_router.config import Config
import logging

db = SQLAlchemy()
logger = logging.getLogger(__name__)


class MCPServer(db.Model):
    """Model for MCP server configurations"""

    __tablename__ = "mcp_servers"

    id = db.Column(db.String(32), primary_key=True, default=lambda: generate_id())
    name = db.Column(db.String(100), unique=True, nullable=False)
    github_url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    runtime_type = db.Column(db.String(20), nullable=False)  # npx, uvx, docker
    install_command = db.Column(db.Text, nullable=False, default="")
    start_command = db.Column(db.Text, nullable=False)
    env_variables = db.Column(JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<MCPServer {self.name}>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "name": self.name,
            "github_url": self.github_url,
            "description": self.description,
            "runtime_type": self.runtime_type,
            "install_command": self.install_command,
            "start_command": self.start_command,
            "env_variables": self.env_variables,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MCPServerStatus(db.Model):
    """Model to track MCP server runtime status"""

    __tablename__ = "mcp_server_status"

    id = db.Column(db.Integer, primary_key=True)
    transport = db.Column(db.String(20), nullable=False)  # stdio, http
    status = db.Column(db.String(20), nullable=False, default="stopped")
    pid = db.Column(db.Integer)  # Process ID if running
    port = db.Column(db.Integer)  # Port if HTTP
    host = db.Column(db.String(100))  # Host if HTTP
    path = db.Column(db.String(100))  # Path if HTTP
    api_key = db.Column(db.String(100))  # API key if HTTP (stored for display, not secure storage)
    oauth_enabled = db.Column(db.Boolean, default=False)  # OAuth enabled flag
    auth_type = db.Column(db.String(20), nullable=False, default="api_key")  # oauth|api_key
    started_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

    def to_dict(self) -> Dict[str, Any]:
        """Convert status to dictionary for API responses"""
        return {
            "id": self.id,
            "transport": self.transport,
            "status": self.status,
            "pid": self.pid,
            "port": self.port,
            "host": self.host,
            "path": self.path,
            "api_key": "***" if self.api_key else None,  # Don't expose full API key
            "oauth_enabled": self.oauth_enabled,
            "auth_type": self.auth_type,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "error_message": self.error_message,
        }


def generate_id() -> str:
    """Generate a unique ID for servers"""
    import uuid

    return uuid.uuid4().hex[:32]


def init_db(app) -> None:
    """Initialize database with app context and handle migrations

    Args:
        app: Flask application instance
    """
    db.init_app(app)
    with app.app_context():
        # Create all tables
        db.create_all()

        # Handle migrations - check for missing columns and add them
        try:
            # Check column existence in mcp_server_status
            result = db.session.execute(text("PRAGMA table_info(mcp_server_status)")).fetchall()
            column_names = [row[1] for row in result]

            # Add oauth_enabled column if it doesn't exist
            if "oauth_enabled" not in column_names:
                logger.info("Adding oauth_enabled column to mcp_server_status table")
                db.session.execute(
                    text("ALTER TABLE mcp_server_status ADD COLUMN oauth_enabled BOOLEAN DEFAULT 0")
                )
                db.session.commit()
                logger.info("Successfully added oauth_enabled column")

            # Add auth_type column if it doesn't exist
            if "auth_type" not in column_names:
                logger.info("Adding auth_type column to mcp_server_status table")

                # Set default based on current auth type setting
                default_auth_type = Config.MCP_AUTH_TYPE

                db.session.execute(
                    text(
                        f"ALTER TABLE mcp_server_status ADD COLUMN auth_type VARCHAR(20) DEFAULT '{default_auth_type}'"
                    )
                )
                db.session.commit()
                logger.info(
                    f"Successfully added auth_type column with default '{default_auth_type}'"
                )

        except Exception as e:
            logger.error(f"Error during database migration: {e}")
            # If there's an error, try to recreate the table
            # This is safe because MCPServerStatus is ephemeral runtime data
            try:
                db.session.execute(text("DROP TABLE IF EXISTS mcp_server_status"))
                db.session.commit()
                db.create_all()
                logger.info("Recreated mcp_server_status table with new schema")
            except Exception as e2:
                logger.error(f"Failed to recreate table: {e2}")


def get_server_by_id(server_id: str) -> Optional[MCPServer]:
    """Get server by ID

    Args:
        server_id: The server ID to look up

    Returns:
        MCPServer instance if found, None otherwise
    """
    return MCPServer.query.get(server_id)


def get_active_servers() -> List[MCPServer]:
    """Get all active servers

    Returns:
        List of active MCPServer instances
    """
    return MCPServer.query.filter_by(is_active=True).all()


def get_server_status() -> Optional[MCPServerStatus]:
    """Get current MCP server status

    Returns:
        MCPServerStatus instance if exists, None otherwise
    """
    return MCPServerStatus.query.first()


def update_server_status(transport: str, status: str, **kwargs) -> MCPServerStatus:
    """Update or create server status

    Args:
        transport: Transport type (stdio, http)
        status: Server status (running, stopped, error)
        **kwargs: Additional fields to update (pid, port, host, etc.)

    Returns:
        Updated MCPServerStatus instance
    """
    server_status = MCPServerStatus.query.first()
    if not server_status:
        server_status = MCPServerStatus(transport=transport, status=status)
        db.session.add(server_status)
    else:
        server_status.transport = transport
        server_status.status = status

    # Update additional fields
    for key, value in kwargs.items():
        if hasattr(server_status, key):
            setattr(server_status, key, value)

    db.session.commit()
    return server_status


def get_auth_type() -> str:
    """Get current authentication type preference

    Returns:
        Current auth type ('oauth' or 'api_key'), defaults to 'api_key'
    """
    server_status = MCPServerStatus.query.first()
    if server_status and server_status.auth_type:
        return server_status.auth_type

    # Fallback to environment variable if no database record
    from mcp_router.config import Config

    return Config.MCP_AUTH_TYPE


def set_auth_type(auth_type: str) -> None:
    """Set authentication type preference with validation

    Args:
        auth_type: Authentication type ('oauth' or 'api_key')

    Raises:
        ValueError: If auth_type is not valid
    """
    if auth_type not in ("oauth", "api_key"):
        raise ValueError(f"Invalid auth_type '{auth_type}'. Must be 'oauth' or 'api_key'")

    server_status = ensure_server_status_exists()
    server_status.auth_type = auth_type
    db.session.commit()
    logger.info(f"Auth type updated to: {auth_type}")


def ensure_server_status_exists() -> MCPServerStatus:
    """Ensure server status record exists for current transport

    Returns:
        MCPServerStatus instance (existing or newly created)
    """
    from mcp_router.config import Config

    server_status = MCPServerStatus.query.first()
    if not server_status:
        # Create new status record with current transport and auth type
        server_status = MCPServerStatus(
            transport=Config.MCP_TRANSPORT, status="running", auth_type=Config.MCP_AUTH_TYPE
        )
        db.session.add(server_status)
        db.session.commit()
        logger.info(f"Created server status record with auth_type: {Config.MCP_AUTH_TYPE}")

    return server_status
