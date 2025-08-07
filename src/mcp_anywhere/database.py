"""Database models for MCP Anywhere with async support"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcp_anywhere.base import Base
from mcp_anywhere.config import Config
from mcp_anywhere.logging_config import get_logger

logger = get_logger(__name__)


def generate_id() -> str:
    """Generate a unique 8-character ID"""
    return str(uuid.uuid4())[:8]


class MCPServer(Base):
    """Model for MCP server configurations"""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(8), primary_key=True, default=generate_id)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    github_url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    runtime_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # npx, uvx, docker
    install_command: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_command: Mapped[str] = mapped_column(Text, nullable=False)
    env_variables: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    build_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    build_error: Mapped[str | None] = mapped_column(Text)
    image_tag: Mapped[str | None] = mapped_column(String(200))

    # Relationship to tools
    tools: Mapped[list["MCPServerTool"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<MCPServer {self.name}>"

    def to_dict(self) -> dict[str, Any]:
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


class MCPServerTool(Base):
    """Model for MCP server tools"""

    __tablename__ = "mcp_server_tools"

    id: Mapped[str] = mapped_column(String(8), primary_key=True, default=generate_id)
    server_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("mcp_servers.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_description: Mapped[str | None] = mapped_column(Text)
    tool_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationship back to server
    server: Mapped["MCPServer"] = relationship(back_populates="tools")

    def __repr__(self):
        return f"<MCPServerTool {self.tool_name}>"


class DatabaseManager:
    """Manages database engine and session factory lifecycle."""

    def __init__(self):
        self._engine = None
        self._session_factory = None

    async def initialize(self):
        """Initialize the async database."""
        if self._engine is None:
            # Create engine - use SQLALCHEMY_DATABASE_URI from config
            db_url = Config.SQLALCHEMY_DATABASE_URI.replace(
                "sqlite://", "sqlite+aiosqlite://"
            )
            self._engine = create_async_engine(db_url)

            # Create session factory
            self._session_factory = async_sessionmaker(
                self._engine, class_=AsyncSession, expire_on_commit=False
            )

            # Create tables
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("Async database initialized")

    def get_session(self) -> AsyncSession:
        """Get an async database session."""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._session_factory()

    async def close(self):
        """Close the database connection."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection closed")

    @property
    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._engine is not None


# Create a single instance
db_manager = DatabaseManager()


# Database session management - backward compatibility functions
async def init_db():
    """Initialize the async database"""
    await db_manager.initialize()


def get_async_session() -> AsyncSession:
    """Get an async database session"""
    return db_manager.get_session()


async def close_db():
    """Close the database connection"""
    await db_manager.close()


# Async helper functions to replace Flask-SQLAlchemy equivalents
async def get_active_servers(session: AsyncSession | None = None) -> list[MCPServer]:
    """Get all active servers (async equivalent of Flask-SQLAlchemy function)."""
    if session:
        # Use provided session
        stmt = select(MCPServer).where(MCPServer.is_active == True)
        result = await session.execute(stmt)
        return result.scalars().all()
    else:
        # Create own session
        async with get_async_session() as session:
            stmt = select(MCPServer).where(MCPServer.is_active == True)
            result = await session.execute(stmt)
            return result.scalars().all()


async def get_built_servers(session: AsyncSession | None = None) -> list[MCPServer]:
    """Get all built servers (async equivalent of Flask-SQLAlchemy function)."""
    if session:
        # Use provided session
        stmt = select(MCPServer).where(MCPServer.build_status == "built")
        result = await session.execute(stmt)
        return result.scalars().all()
    else:
        # Create own session
        async with get_async_session() as session:
            stmt = select(MCPServer).where(MCPServer.build_status == "built")
            result = await session.execute(stmt)
            return result.scalars().all()


# Import auth models after Base is defined to avoid circular imports
