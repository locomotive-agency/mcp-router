"""Application settings and configuration management."""

from typing import Optional, Literal
from pathlib import Path
from pydantic import Field, validator
from pydantic_settings import BaseSettings
import secrets


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    app_name: str = "MCP Router"
    debug: bool = Field(False, env="DEBUG")
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8080, env="PORT")

    # Database
    database_url: str = Field(
        "sqlite:///./data/mcp_router.db",
        env="DATABASE_URL"
    )

    # Security
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32), env="SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_expiration: int = 86400  # 24 hours

    # External Services
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    github_token: Optional[str] = Field(None, env="GITHUB_TOKEN")
    e2b_api_key: Optional[str] = Field(None, env="E2B_API_KEY")

    # Container Configuration
    container_backend: Literal["docker", "e2b"] = Field(
        "docker",
        env="CONTAINER_BACKEND"
    )
    max_concurrent_containers: int = Field(10, env="MAX_CONTAINERS")
    container_timeout: int = Field(300, env="CONTAINER_TIMEOUT")
    container_memory_limit: str = Field("512m", env="CONTAINER_MEMORY")
    container_cpu_limit: float = Field(1.0, env="CONTAINER_CPU")

    # MCP Configuration
    mcp_mode: Literal["local", "remote"] = Field("local", env="MCP_MODE")
    mcp_remote_url: Optional[str] = Field(None, env="MCP_REMOTE_URL")

    # Cache
    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    cache_ttl: int = Field(3600, env="CACHE_TTL")

    # Monitoring
    enable_metrics: bool = Field(True, env="ENABLE_METRICS")
    metrics_port: int = Field(9090, env="METRICS_PORT")

    # Paths
    data_dir: Path = Field(Path("./data"), env="DATA_DIR")
    log_dir: Path = Field(Path("./logs"), env="LOG_DIR")

    class Config:
        """Pydantic config."""
        env_file = ".env"
        case_sensitive = False

    @validator("data_dir", "log_dir", pre=True)
    def create_directories(cls, v: Path) -> Path:
        """Ensure directories exist."""
        if isinstance(v, str):
            v = Path(v)
        v.mkdir(parents=True, exist_ok=True)
        return v

    @validator("mcp_remote_url")
    def validate_remote_url(cls, v: Optional[str], values: dict) -> Optional[str]:
        """Validate remote URL when in remote mode."""
        if values.get("mcp_mode") == "remote" and not v:
            raise ValueError("mcp_remote_url is required when mcp_mode is 'remote'")
        return v

    @property
    def database_file_path(self) -> Path:
        """Get the database file path for SQLite."""
        if self.database_url.startswith("sqlite:///"):
            db_path = self.database_url.replace("sqlite:///", "")
            return Path(db_path)
        raise ValueError("database_file_path only available for SQLite databases")

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.debug

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug 