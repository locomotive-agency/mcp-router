"""Configuration API endpoints."""

from typing import Dict, Any
from fastapi import APIRouter, Depends, Request

from mcp_router.models import ClaudeDesktopConfig, ConfigResponse

router = APIRouter()


@router.get("/config/claude-desktop", response_model=ConfigResponse)
async def get_claude_desktop_config(
    request: Request
) -> ConfigResponse:
    """Get Claude Desktop configuration."""
    settings = request.app.state.settings
    
    # Generate Claude Desktop configuration
    if settings.mcp_mode == "local":
        config = {
            "mcpServers": {
                "mcp-router": {
                    "command": "python",
                    "args": [
                        "-m", "mcp_router",
                        "--mode", "stdio"
                    ],
                    "env": {
                        "MCP_ROUTER_DB": str(settings.database_file_path),
                        "ANTHROPIC_API_KEY": settings.anthropic_api_key
                    }
                }
            }
        }
    else:
        config = {
            "mcpServers": {
                "mcp-router": {
                    "url": settings.mcp_remote_url or f"http://{settings.host}:{settings.port}",
                    "transport": "sse"
                }
            }
        }
    
    return ConfigResponse(config=config)


@router.get("/config/settings", response_model=Dict[str, Any])
async def get_application_settings(
    request: Request
) -> Dict[str, Any]:
    """Get application settings (sanitized for frontend)."""
    settings = request.app.state.settings
    
    # Return sanitized settings (no secrets)
    return {
        "app_name": settings.app_name,
        "debug": settings.debug,
        "mcp_mode": settings.mcp_mode,
        "container_backend": settings.container_backend,
        "max_concurrent_containers": settings.max_concurrent_containers,
        "container_timeout": settings.container_timeout,
        "enable_metrics": settings.enable_metrics,
        "version": "0.1.0"
    } 