"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field, validator, HttpUrl


# Environment Variable Schemas
class EnvVariableBase(BaseModel):
    """Base environment variable schema."""
    key: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_required: bool = Field(True)
    is_secret: bool = Field(False)
    default_value: Optional[str] = Field(None, max_length=1000)
    validation_regex: Optional[str] = Field(None, max_length=200)


class EnvVariableCreate(EnvVariableBase):
    """Schema for creating environment variables."""
    value: Optional[str] = Field(None, max_length=1000)


class EnvVariableUpdate(BaseModel):
    """Schema for updating environment variables."""
    value: Optional[str] = Field(None, max_length=1000)
    description: Optional[str] = Field(None, max_length=500)
    is_required: Optional[bool] = None
    is_secret: Optional[bool] = None
    default_value: Optional[str] = Field(None, max_length=1000)
    validation_regex: Optional[str] = Field(None, max_length=200)


class EnvVariableResponse(EnvVariableBase):
    """Schema for environment variable responses."""
    id: str
    server_id: str
    value: Optional[str] = None  # Hidden if is_secret=True

    class Config:
        from_attributes = True

    @validator("value", pre=True, always=True)
    def hide_secret_values(cls, v, values):
        """Hide secret values in responses."""
        if values.get("is_secret") and v:
            return "***"
        return v


# MCP Server Schemas
class MCPServerBase(BaseModel):
    """Base MCP server schema."""
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(..., min_length=1, max_length=200)
    github_url: HttpUrl
    description: Optional[str] = Field(None, max_length=1000)
    runtime_type: Literal["npx", "uvx", "docker"]
    install_command: str = Field(..., min_length=1, max_length=500)
    start_command: str = Field(..., min_length=1, max_length=500)
    transport_type: Literal["stdio", "sse", "http"]
    transport_config: Dict[str, Any] = Field(default_factory=dict)
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class MCPServerCreate(MCPServerBase):
    """Schema for creating MCP servers."""
    env_variables: List[EnvVariableCreate] = Field(default_factory=list)


class MCPServerUpdate(BaseModel):
    """Schema for updating MCP servers."""
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    install_command: Optional[str] = Field(None, min_length=1, max_length=500)
    start_command: Optional[str] = Field(None, min_length=1, max_length=500)
    transport_type: Optional[Literal["stdio", "sse", "http"]] = None
    transport_config: Optional[Dict[str, Any]] = None
    capabilities: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class MCPServerResponse(MCPServerBase):
    """Schema for MCP server responses."""
    id: str
    is_active: bool
    is_healthy: bool
    last_health_check: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    env_variables: List[EnvVariableResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


# Server Analysis Schemas
class DetectedEnvVariable(BaseModel):
    """Schema for detected environment variables during analysis."""
    key: str
    description: str
    is_required: bool = True
    is_secret: bool = False
    default_value: Optional[str] = None


class ServerAnalysisRequest(BaseModel):
    """Schema for server analysis requests."""
    github_url: HttpUrl


class ServerAnalysisResponse(BaseModel):
    """Schema for server analysis responses."""
    name: str
    display_name: str
    description: str
    runtime_type: Literal["npx", "uvx", "docker"]
    install_command: str
    start_command: str
    transport_type: Literal["stdio", "sse", "http"]
    transport_config: Dict[str, Any] = Field(default_factory=dict)
    env_variables: List[DetectedEnvVariable] = Field(default_factory=list)
    detected_tools: List[str] = Field(default_factory=list)
    capabilities: Dict[str, Any] = Field(default_factory=dict)


# Container Session Schemas
class ContainerSessionResponse(BaseModel):
    """Schema for container session responses."""
    id: str
    server_id: str
    container_id: str
    status: Literal["starting", "running", "stopping", "stopped", "error"]
    started_at: datetime
    stopped_at: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


# Health Check Schemas
class ServiceHealth(BaseModel):
    """Schema for individual service health."""
    status: Literal["healthy", "degraded", "unhealthy"]
    last_check: datetime
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Schema for overall health check response."""
    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime
    services: Dict[str, ServiceHealth]
    version: str


# Test Connection Schemas
class TestConnectionRequest(BaseModel):
    """Schema for test connection requests."""
    timeout: Optional[int] = Field(30, ge=5, le=300)


class TestConnectionResponse(BaseModel):
    """Schema for test connection responses."""
    success: bool
    message: str
    capabilities: Optional[Dict[str, Any]] = None
    response_time: Optional[float] = None
    error_details: Optional[Dict[str, Any]] = None


# Log Entry Schemas
class LogEntry(BaseModel):
    """Schema for log entries."""
    timestamp: datetime
    level: str
    message: str
    source: str
    metadata: Optional[Dict[str, Any]] = None


class LogsRequest(BaseModel):
    """Schema for logs request."""
    lines: Optional[int] = Field(100, ge=1, le=10000)
    since: Optional[datetime] = None
    level: Optional[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]] = None


class LogsResponse(BaseModel):
    """Schema for logs response."""
    logs: List[LogEntry]
    total_lines: int
    has_more: bool


# Configuration Schemas
class ClaudeDesktopConfig(BaseModel):
    """Schema for Claude Desktop configuration."""
    mcpServers: Dict[str, Any]


class ConfigResponse(BaseModel):
    """Schema for configuration responses."""
    config: Dict[str, Any]


# Audit Log Schemas
class AuditLogResponse(BaseModel):
    """Schema for audit log responses."""
    id: str
    timestamp: datetime
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True


# Tool Call Schemas
class ToolCallRequest(BaseModel):
    """Schema for tool call requests."""
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    timeout: Optional[int] = Field(300, ge=5, le=3600)


class ToolCallResponse(BaseModel):
    """Schema for tool call responses."""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    container_id: Optional[str] = None


# Pagination Schemas
class PaginationParams(BaseModel):
    """Schema for pagination parameters."""
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    """Schema for paginated responses."""
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int

    @validator("pages", pre=True, always=True)
    def calculate_pages(cls, v, values):
        """Calculate total pages."""
        total = values.get("total", 0)
        size = values.get("size", 20)
        return (total + size - 1) // size if total > 0 else 0


# Error Schemas
class ErrorDetail(BaseModel):
    """Schema for error details."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """Schema for error responses."""
    error: str
    message: str
    details: Optional[List[ErrorDetail]] = None
    timestamp: datetime
