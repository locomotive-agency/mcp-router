"""
Database models for MCP Router.

This module defines the database schema for storing MCP server configurations,
environment variables, and session metadata.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

Base = declarative_base()


class MCPServer(Base):
    """MCP Server configuration model."""
    __tablename__ = "mcp_servers"
    
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    github_url = Column(String, nullable=False)
    description = Column(Text)
    runtime_type = Column(String, nullable=False)  # 'npx', 'uvx', 'docker'
    install_command = Column(String, nullable=False)
    start_command = Column(String, nullable=False)
    transport_type = Column(String, nullable=False)  # 'stdio', 'sse', 'http'
    transport_config = Column(JSON, nullable=False, default=dict)
    capabilities = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    is_healthy = Column(Boolean, nullable=False, default=False)
    last_health_check = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    env_variables = relationship("EnvVariable", back_populates="server", cascade="all, delete-orphan")
    container_sessions = relationship("ContainerSession", back_populates="server", cascade="all, delete-orphan")


class EnvVariable(Base):
    """Environment variable model."""
    __tablename__ = "env_variables"
    
    id = Column(String, primary_key=True)
    server_id = Column(String, ForeignKey("mcp_servers.id"), nullable=False)
    key = Column(String, nullable=False)
    value = Column(String)  # Can be null if not set
    description = Column(Text)
    is_required = Column(Boolean, nullable=False, default=True)
    is_secret = Column(Boolean, nullable=False, default=False)
    default_value = Column(String)
    validation_regex = Column(String)
    
    # Relationships
    server = relationship("MCPServer", back_populates="env_variables")


class ContainerSession(Base):
    """Container session tracking model."""
    __tablename__ = "container_sessions"
    
    id = Column(String, primary_key=True)
    server_id = Column(String, ForeignKey("mcp_servers.id"), nullable=False)
    container_id = Column(String, nullable=False)
    status = Column(String, nullable=False)  # 'starting', 'running', 'stopping', 'stopped', 'error'
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    stopped_at = Column(DateTime)
    metrics = Column(JSON)
    
    # Relationships
    server = relationship("MCPServer", back_populates="container_sessions")


class AuditLog(Base):
    """Audit log model."""
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String)
    details = Column(JSON)
    user_id = Column(String)
    ip_address = Column(String)


@dataclass
class DatabaseManager:
    """Database manager for async operations."""
    
    engine: Any = None
    session_factory: Any = None
    
    def __init__(self, database_url: str):
        """Initialize database manager."""
        self.database_url = database_url
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def create_tables_async(self):
        """Create database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    def get_session(self) -> AsyncSession:
        """Get database session."""
        return self.session_factory()
    
    async def close(self):
        """Close database engine."""
        if self.engine:
            await self.engine.dispose()


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def init_database(database_url: str) -> DatabaseManager:
    """Initialize global database manager."""
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    return _db_manager


def get_database() -> DatabaseManager:
    """Get global database manager."""
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_manager


# For backward compatibility with existing code
def get_session():
    """Get database session for dependency injection."""
    return get_database().get_session()
