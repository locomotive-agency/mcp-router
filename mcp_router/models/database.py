"""Database configuration and SQLAlchemy models."""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, JSON, Integer, Float,
    ForeignKey, CheckConstraint, create_engine, event
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func

Base = declarative_base()


def generate_uuid() -> str:
    """Generate a UUID string for database records."""
    return str(uuid.uuid4())


class MCPServer(Base):
    """MCP Server model."""
    
    __tablename__ = "mcp_servers"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    github_url = Column(String, nullable=False)
    description = Column(Text)
    runtime_type = Column(
        String, 
        nullable=False,
        # CheckConstraint clause will be added in migration
    )
    install_command = Column(String, nullable=False)
    start_command = Column(String, nullable=False)
    transport_type = Column(
        String,
        nullable=False,
        # CheckConstraint clause will be added in migration
    )
    transport_config = Column(JSON, nullable=False, default=dict)
    capabilities = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    is_healthy = Column(Boolean, nullable=False, default=False)
    last_health_check = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    env_variables = relationship("EnvVariable", back_populates="server", cascade="all, delete-orphan")
    container_sessions = relationship("ContainerSession", back_populates="server", cascade="all, delete-orphan")
    
    def get_env_dict(self) -> Dict[str, str]:
        """Get environment variables as a dictionary."""
        return {env.key: env.value for env in self.env_variables if env.value}
    
    def __repr__(self) -> str:
        return f"<MCPServer(name='{self.name}', runtime='{self.runtime_type}')>"


class EnvVariable(Base):
    """Environment Variable model."""
    
    __tablename__ = "env_variables"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    server_id = Column(String, ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False)
    key = Column(String, nullable=False)
    value = Column(String)
    description = Column(Text)
    is_required = Column(Boolean, nullable=False, default=True)
    is_secret = Column(Boolean, nullable=False, default=False)
    default_value = Column(String)
    validation_regex = Column(String)
    
    # Relationships
    server = relationship("MCPServer", back_populates="env_variables")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "key IS NOT NULL AND key != ''",
            name="env_var_key_not_empty"
        ),
    )
    
    def __repr__(self) -> str:
        return f"<EnvVariable(server='{self.server_id}', key='{self.key}')>"


class AuditLog(Base):
    """Audit Log model for tracking changes."""
    
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, nullable=False, default=func.now())
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String)
    details = Column(JSON)
    user_id = Column(String)
    ip_address = Column(String)
    
    def __repr__(self) -> str:
        return f"<AuditLog(action='{self.action}', resource='{self.resource_type}')>"


class ContainerSession(Base):
    """Container Session model for tracking container lifecycle."""
    
    __tablename__ = "container_sessions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    server_id = Column(String, ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False)
    container_id = Column(String, nullable=False)
    status = Column(
        String,
        nullable=False,
        # CheckConstraint will be added in migration
    )
    started_at = Column(DateTime, nullable=False, default=func.now())
    stopped_at = Column(DateTime)
    metrics = Column(JSON)
    
    # Relationships
    server = relationship("MCPServer", back_populates="container_sessions")
    
    def __repr__(self) -> str:
        return f"<ContainerSession(server='{self.server_id}', status='{self.status}')>"


# Database connection and session management
class DatabaseManager:
    """Database connection manager."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.async_engine = None
        self.SessionLocal = None
        self.AsyncSessionLocal = None
    
    def initialize_sync(self):
        """Initialize synchronous database connection."""
        if "sqlite" in self.database_url:
            # Enable foreign key constraints for SQLite
            self.engine = create_engine(
                self.database_url,
                connect_args={"check_same_thread": False},
                echo=False
            )
            
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        else:
            self.engine = create_engine(self.database_url)
        
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def initialize_async(self):
        """Initialize asynchronous database connection."""
        async_url = self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        
        if "sqlite" in async_url:
            self.async_engine = create_async_engine(
                async_url,
                echo=False,
                future=True
            )
        else:
            self.async_engine = create_async_engine(async_url)
        
        self.AsyncSessionLocal = sessionmaker(
            self.async_engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    
    def create_tables(self):
        """Create all database tables."""
        if self.engine is None:
            self.initialize_sync()
        Base.metadata.create_all(bind=self.engine)
    
    async def create_tables_async(self):
        """Create all database tables asynchronously."""
        if self.async_engine is None:
            self.initialize_async()
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


# Global database instance
_db_manager: Optional[DatabaseManager] = None


def init_database(database_url: str) -> DatabaseManager:
    """Initialize the global database manager."""
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    _db_manager.initialize_sync()
    _db_manager.initialize_async()
    return _db_manager


def get_database() -> DatabaseManager:
    """Get the global database manager."""
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_manager


def get_session():
    """Get a database session."""
    db = get_database()
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def get_async_session():
    """Get an async database session."""
    db = get_database()
    async with db.AsyncSessionLocal() as session:
        yield session
