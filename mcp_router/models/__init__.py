"""Database models for MCP Router."""

from .database import (
    Base, 
    get_database, 
    init_database,
    get_session,
    get_async_session,
    DatabaseManager,
    MCPServer,
    EnvVariable,
    AuditLog,
    ContainerSession,
)
from .schemas import (
    # Environment Variable Schemas
    EnvVariableBase,
    EnvVariableCreate,
    EnvVariableUpdate,
    EnvVariableResponse,
    
    # MCP Server Schemas
    MCPServerBase,
    MCPServerCreate,
    MCPServerUpdate,
    MCPServerResponse,
    
    # Analysis Schemas
    DetectedEnvVariable,
    ServerAnalysisRequest,
    ServerAnalysisResponse,
    
    # Container Schemas
    ContainerSessionResponse,
    
    # Health Schemas
    ServiceHealth,
    HealthResponse,
    
    # Test Connection Schemas
    TestConnectionRequest,
    TestConnectionResponse,
    
    # Log Schemas
    LogEntry,
    LogsRequest,
    LogsResponse,
    
    # Configuration Schemas
    ClaudeDesktopConfig,
    ConfigResponse,
    
    # Audit Schemas
    AuditLogResponse,
    
    # Tool Call Schemas
    ToolCallRequest,
    ToolCallResponse,
    
    # Pagination Schemas
    PaginationParams,
    PaginatedResponse,
    
    # Error Schemas
    ErrorDetail,
    ErrorResponse,
)

__all__ = [
    # Database
    "Base",
    "get_database",
    "init_database",
    "get_session",
    "get_async_session",
    "DatabaseManager",
    "MCPServer",
    "EnvVariable", 
    "AuditLog",
    "ContainerSession",
    
    # Environment Variable Schemas
    "EnvVariableBase",
    "EnvVariableCreate",
    "EnvVariableUpdate",
    "EnvVariableResponse",
    
    # MCP Server Schemas
    "MCPServerBase",
    "MCPServerCreate",
    "MCPServerUpdate",
    "MCPServerResponse",
    
    # Analysis Schemas
    "DetectedEnvVariable",
    "ServerAnalysisRequest",
    "ServerAnalysisResponse",
    
    # Container Schemas
    "ContainerSessionResponse",
    
    # Health Schemas
    "ServiceHealth",
    "HealthResponse",
    
    # Test Connection Schemas
    "TestConnectionRequest",
    "TestConnectionResponse",
    
    # Log Schemas
    "LogEntry",
    "LogsRequest",
    "LogsResponse",
    
    # Configuration Schemas
    "ClaudeDesktopConfig",
    "ConfigResponse",
    
    # Audit Schemas
    "AuditLogResponse",
    
    # Tool Call Schemas
    "ToolCallRequest",
    "ToolCallResponse",
    
    # Pagination Schemas
    "PaginationParams",
    "PaginatedResponse",
    
    # Error Schemas
    "ErrorDetail",
    "ErrorResponse",
]
