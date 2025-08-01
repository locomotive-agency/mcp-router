"""Database models for MCP Router"""

from datetime import datetime
from typing import List, Dict, Any
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, text
from mcp_router.logging_config import get_logger

from mcp_router.config import Config

db = SQLAlchemy()
logger = get_logger(__name__)


class MCPServer(db.Model):
    """Model for MCP server configurations"""

    __tablename__ = "mcp_servers"

    id = db.Column(db.String(8), primary_key=True, default=lambda: generate_id())
    name = db.Column(db.String(100), unique=True, nullable=False)
    github_url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    runtime_type = db.Column(db.String(20), nullable=False)  # npx, uvx
    install_command = db.Column(db.Text, nullable=False, default="")
    start_command = db.Column(db.Text, nullable=False)
    env_variables = db.Column(JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # After the existing fields
    build_status = db.Column(db.String(20), nullable=False, default="pending")

    build_error = db.Column(db.Text)

    image_tag = db.Column(db.String(200))

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
            "build_status": self.build_status,
            "build_error": self.build_error,
            "image_tag": self.image_tag,
        }


class MCPServerTool(db.Model):
    """Model for MCP server tools"""

    __tablename__ = "mcp_server_tools"

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(
        db.String(8), db.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )
    tool_name = db.Column(db.String(200), nullable=False)
    tool_description = db.Column(db.Text)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    server = db.relationship("MCPServer", backref=db.backref("tools", cascade="all, delete-orphan"))

    # Unique constraint to prevent duplicate tools per server
    __table_args__ = (db.UniqueConstraint("server_id", "tool_name"),)

    def __repr__(self) -> str:
        return f"<MCPServerTool {self.server_id}_{self.tool_name}>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "tool_description": self.tool_description,
            "is_enabled": self.is_enabled,
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

    return uuid.uuid4().hex[:8]


def init_db(app) -> None:
    """Initialize database with app context and handle migrations"""
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

            # Check column existence in mcp_servers table for new build fields
            result = db.session.execute(text("PRAGMA table_info(mcp_servers)")).fetchall()
            column_names = [row[1] for row in result]

            # Add new columns if they don't exist
            if "build_status" not in column_names:
                logger.info("Adding build_status column to mcp_servers table")
                db.session.execute(
                    text(
                        "ALTER TABLE mcp_servers ADD COLUMN build_status VARCHAR(20) DEFAULT 'pending'"
                    )
                )
                db.session.commit()

            if "build_error" not in column_names:
                logger.info("Adding build_error column to mcp_servers table")
                db.session.execute(text("ALTER TABLE mcp_servers ADD COLUMN build_error TEXT"))
                db.session.commit()

            if "image_tag" not in column_names:
                logger.info("Adding image_tag column to mcp_servers table")
                db.session.execute(
                    text("ALTER TABLE mcp_servers ADD COLUMN image_tag VARCHAR(200)")
                )
                db.session.commit()

            # Check if mcp_server_tools table exists and create if needed
            try:
                result = db.session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_server_tools'"
                    )
                ).fetchone()
                if not result:
                    logger.info("Creating mcp_server_tools table")
                    # Create the table using SQLAlchemy metadata
                    MCPServerTool.__table__.create(db.engine)
                    logger.info("Successfully created mcp_server_tools table")
            except Exception as table_error:
                logger.error(f"Error creating mcp_server_tools table: {table_error}")

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


def get_active_servers() -> List[MCPServer]:
    """Get all active servers"""
    return MCPServer.query.filter_by(is_active=True).all()


def get_built_servers() -> List[MCPServer]:
    """Get all built servers"""
    return MCPServer.query.filter_by(build_status="built").all()


def get_auth_type() -> str:
    """Get current authentication type preference"""
    server_status = MCPServerStatus.query.first()
    if server_status and server_status.auth_type:
        return server_status.auth_type

    # Fallback to environment variable if no database record
    from mcp_router.config import Config

    return Config.MCP_AUTH_TYPE


def set_auth_type(auth_type: str) -> None:
    """Set authentication type preference with validation"""
    if auth_type not in ("oauth", "api_key"):
        raise ValueError(f"Invalid auth_type '{auth_type}'. Must be 'oauth' or 'api_key'")

    server_status = ensure_server_status_exists()
    server_status.auth_type = auth_type
    db.session.commit()
    logger.info(f"Auth type updated to: {auth_type}")


def ensure_server_status_exists() -> MCPServerStatus:
    """Ensure server status record exists for current transport"""

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


def clear_database() -> None:
    """Clear all data from the database tables."""
    logger.info("Clearing database...")
    try:
        # Drop all tables
        db.drop_all()
        logger.info("All tables dropped successfully")

        # Recreate all tables
        db.create_all()
        logger.info("All tables recreated successfully")

        # Perform any necessary migrations
        logger.info("Running post-creation migrations...")
        # The migrations will be handled by init_db if needed

        logger.info("Database cleared successfully")
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        raise


def get_connection_status(request=None) -> Dict[str, Any]:
    """Get the current connection status and configuration."""
    status_info = {
        "transport": Config.MCP_TRANSPORT,
        "status": "running",  # If this code is running, the app is running
    }

    if Config.MCP_TRANSPORT == "stdio":
        # For STDIO mode, show command for local clients
        status_info.update(
            {
                "connection_info": {
                    "type": "stdio",
                    "description": "Connect via Claude Desktop or local clients",
                    "command": "python -m mcp_router --transport stdio",
                    "web_ui_url": f"http://127.0.0.1:{Config.FLASK_PORT}",
                    "web_ui_description": "Web UI running in background for server management",
                    "config_download_url": f"http://127.0.0.1:{Config.FLASK_PORT}/config/claude-desktop",
                    "config_description": "Download Claude Desktop configuration file",
                }
            }
        )
    elif Config.MCP_TRANSPORT == "http":
        # Determine base URL from request if available
        if request:
            scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
            host = request.headers.get("X-Forwarded-Host", request.host)
            base_url = f"{scheme}://{host}"
        else:
            base_url = f"http://{Config.MCP_HOST}:{Config.FLASK_PORT}"

        mcp_url = f"{base_url}{Config.MCP_PATH}"

        status_info.update(
            {
                "connection_info": {
                    "type": "http",
                    "mcp_endpoint": mcp_url,
                    "web_ui_url": base_url,
                    "path": Config.MCP_PATH,
                },
                "host": Config.MCP_HOST,
                "port": Config.FLASK_PORT,
            }
        )

        # Add authentication information
        current_auth_type = get_auth_type()

        # Always show both auth methods are available
        auth_info = {
            "auth_type": current_auth_type,
            "oauth_available": True,
            "oauth_metadata_url": f"{base_url}/.well-known/oauth-authorization-server",
        }

        if current_auth_type == "oauth":
            auth_info.update(
                {
                    "primary_auth": "OAuth 2.1 with PKCE",
                    "api_key_available": True,
                }
            )
        else:  # api_key
            auth_info.update(
                {
                    "primary_auth": "API Key",
                    "api_key": Config.MCP_API_KEY if Config.MCP_API_KEY else "auto-generated",
                    "oauth_hint": "Switch to OAuth for enhanced security",
                }
            )

        status_info["connection_info"].update(auth_info)

    return status_info
