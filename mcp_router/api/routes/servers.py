"""Server management API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid
from datetime import datetime

from mcp_router.models import (
    get_session, 
    MCPServerCreate, 
    MCPServerUpdate, 
    MCPServerResponse,
    ServerAnalysisRequest,
    ServerAnalysisResponse,
    TestConnectionResponse
)
from mcp_router.models.database import MCPServer, EnvVariable
from mcp_router.config.settings import Settings
from mcp_router.services.github_service import GitHubService
from mcp_router.services.container_manager import ContainerManager
from mcp_router.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


def get_github_service(settings: Settings = Depends(get_settings)) -> GitHubService:
    """Get GitHub service instance."""
    return GitHubService(settings)


def get_container_manager(settings: Settings = Depends(get_settings)) -> ContainerManager:
    """Get container manager instance."""
    return ContainerManager(settings)


@router.get("/servers", response_model=List[MCPServerResponse])
async def list_servers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_session)
) -> List[MCPServerResponse]:
    """List all MCP servers."""
    try:
        logger.info("Listing servers", extra={"skip": skip, "limit": limit})
        
        # Query servers with their environment variables
        servers = db.execute(
            select(MCPServer).offset(skip).limit(limit)
        ).scalars().all()
        
        result = []
        for server in servers:
            env_vars = [
                {
                    "key": env.key,
                    "value": env.value if not env.is_secret else "[HIDDEN]",
                    "description": env.description,
                    "is_required": env.is_required,
                    "is_secret": env.is_secret,
                    "default_value": env.default_value,
                    "validation_regex": env.validation_regex
                }
                for env in server.env_variables
            ]
            
            result.append(MCPServerResponse(
                id=server.id,
                name=server.name,
                display_name=server.display_name,
                description=server.description,
                github_url=server.github_url,
                runtime_type=server.runtime_type,
                install_command=server.install_command,
                start_command=server.start_command,
                transport_type=server.transport_type,
                transport_config=server.transport_config,
                env_variables=env_vars,
                capabilities=server.capabilities,
                is_active=server.is_active,
                is_healthy=server.is_healthy,
                last_health_check=server.last_health_check,
                created_at=server.created_at,
                updated_at=server.updated_at
            ))
        
        logger.info("Servers listed successfully", extra={"count": len(result)})
        return result
        
    except Exception as e:
        logger.error("Failed to list servers", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list servers"
        )


@router.post("/servers/analyze", response_model=ServerAnalysisResponse)
async def analyze_repository(
    request: ServerAnalysisRequest,
    github_service: GitHubService = Depends(get_github_service)
) -> ServerAnalysisResponse:
    """Analyze a GitHub repository to generate MCP server configuration."""
    try:
        logger.info("Analyzing repository", extra={"github_url": request.github_url})
        
        # Analyze the repository using GitHub service
        analysis_result = await github_service.analyze_repository(request.github_url)
        
        # Convert to response format
        env_variables = []
        for env_var in analysis_result.get("env_variables", []):
            env_variables.append({
                "key": env_var["key"],
                "description": env_var["description"],
                "is_required": env_var["is_required"],
                "is_secret": env_var["is_secret"],
                "default_value": env_var["default_value"]
            })
        
        response = ServerAnalysisResponse(
            name=analysis_result["name"],
            display_name=analysis_result["display_name"],
            description=analysis_result["description"],
            runtime_type=analysis_result["runtime_type"],
            install_command=analysis_result["install_command"],
            start_command=analysis_result["start_command"],
            transport_type=analysis_result["transport_type"],
            env_variables=env_variables,
            detected_tools=analysis_result.get("detected_tools", []),
            capabilities=analysis_result.get("capabilities", {}),
            confidence_score=0.85  # TODO: Implement actual confidence scoring
        )
        
        logger.info("Repository analysis completed", extra={
            "github_url": request.github_url,
            "runtime_type": response.runtime_type,
            "env_vars_count": len(response.env_variables)
        })
        
        return response
        
    except ValueError as e:
        logger.error("Invalid repository URL", extra={
            "github_url": request.github_url,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Repository analysis failed", extra={
            "github_url": request.github_url,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Repository analysis failed"
        )


@router.post("/servers", response_model=MCPServerResponse)
async def create_server(
    server: MCPServerCreate,
    db: Session = Depends(get_session)
) -> MCPServerResponse:
    """Create a new MCP server."""
    try:
        logger.info("Creating server", extra={"name": server.name})
        
        # Check if server name already exists
        existing_server = db.execute(
            select(MCPServer).where(MCPServer.name == server.name)
        ).scalar_one_or_none()
        
        if existing_server:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server name already exists"
            )
        
        # Create server record
        db_server = MCPServer(
            id=str(uuid.uuid4()),
            name=server.name,
            display_name=server.display_name,
            description=server.description,
            github_url=server.github_url,
            runtime_type=server.runtime_type,
            install_command=server.install_command,
            start_command=server.start_command,
            transport_type=server.transport_type,
            transport_config=server.transport_config,
            capabilities=server.capabilities or {},
            is_active=True,
            is_healthy=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(db_server)
        db.flush()  # Get the ID
        
        # Create environment variables
        for env_var in server.env_variables:
            db_env_var = EnvVariable(
                id=str(uuid.uuid4()),
                server_id=db_server.id,
                key=env_var.key,
                value=env_var.value,
                description=env_var.description,
                is_required=env_var.is_required,
                is_secret=env_var.is_secret,
                default_value=env_var.default_value,
                validation_regex=env_var.validation_regex
            )
            db.add(db_env_var)
        
        db.commit()
        db.refresh(db_server)
        
        # Convert to response
        env_vars = [
            {
                "key": env.key,
                "value": env.value if not env.is_secret else "[HIDDEN]",
                "description": env.description,
                "is_required": env.is_required,
                "is_secret": env.is_secret,
                "default_value": env.default_value,
                "validation_regex": env.validation_regex
            }
            for env in db_server.env_variables
        ]
        
        response = MCPServerResponse(
            id=db_server.id,
            name=db_server.name,
            display_name=db_server.display_name,
            description=db_server.description,
            github_url=db_server.github_url,
            runtime_type=db_server.runtime_type,
            install_command=db_server.install_command,
            start_command=db_server.start_command,
            transport_type=db_server.transport_type,
            transport_config=db_server.transport_config,
            env_variables=env_vars,
            capabilities=db_server.capabilities,
            is_active=db_server.is_active,
            is_healthy=db_server.is_healthy,
            last_health_check=db_server.last_health_check,
            created_at=db_server.created_at,
            updated_at=db_server.updated_at
        )
        
        logger.info("Server created successfully", extra={
            "server_id": db_server.id,
            "name": db_server.name
        })
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Server creation failed", extra={
            "name": server.name,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server creation failed"
        )


@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_server(
    server_id: str,
    db: Session = Depends(get_session)
) -> MCPServerResponse:
    """Get a specific MCP server."""
    try:
        logger.info("Getting server", extra={"server_id": server_id})
        
        server = db.execute(
            select(MCPServer).where(MCPServer.id == server_id)
        ).scalar_one_or_none()
        
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        # Convert to response
        env_vars = [
            {
                "key": env.key,
                "value": env.value if not env.is_secret else "[HIDDEN]",
                "description": env.description,
                "is_required": env.is_required,
                "is_secret": env.is_secret,
                "default_value": env.default_value,
                "validation_regex": env.validation_regex
            }
            for env in server.env_variables
        ]
        
        return MCPServerResponse(
            id=server.id,
            name=server.name,
            display_name=server.display_name,
            description=server.description,
            github_url=server.github_url,
            runtime_type=server.runtime_type,
            install_command=server.install_command,
            start_command=server.start_command,
            transport_type=server.transport_type,
            transport_config=server.transport_config,
            env_variables=env_vars,
            capabilities=server.capabilities,
            is_active=server.is_active,
            is_healthy=server.is_healthy,
            last_health_check=server.last_health_check,
            created_at=server.created_at,
            updated_at=server.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get server", extra={
            "server_id": server_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get server"
        )


@router.put("/servers/{server_id}", response_model=MCPServerResponse)
async def update_server(
    server_id: str,
    server_update: MCPServerUpdate,
    db: Session = Depends(get_session)
) -> MCPServerResponse:
    """Update an MCP server."""
    try:
        logger.info("Updating server", extra={"server_id": server_id})
        
        server = db.execute(
            select(MCPServer).where(MCPServer.id == server_id)
        ).scalar_one_or_none()
        
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        # Update server fields
        update_data = server_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(server, field):
                setattr(server, field, value)
        
        server.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(server)
        
        # Convert to response
        env_vars = [
            {
                "key": env.key,
                "value": env.value if not env.is_secret else "[HIDDEN]",
                "description": env.description,
                "is_required": env.is_required,
                "is_secret": env.is_secret,
                "default_value": env.default_value,
                "validation_regex": env.validation_regex
            }
            for env in server.env_variables
        ]
        
        response = MCPServerResponse(
            id=server.id,
            name=server.name,
            display_name=server.display_name,
            description=server.description,
            github_url=server.github_url,
            runtime_type=server.runtime_type,
            install_command=server.install_command,
            start_command=server.start_command,
            transport_type=server.transport_type,
            transport_config=server.transport_config,
            env_variables=env_vars,
            capabilities=server.capabilities,
            is_active=server.is_active,
            is_healthy=server.is_healthy,
            last_health_check=server.last_health_check,
            created_at=server.created_at,
            updated_at=server.updated_at
        )
        
        logger.info("Server updated successfully", extra={
            "server_id": server_id,
            "updated_fields": list(update_data.keys())
        })
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Server update failed", extra={
            "server_id": server_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server update failed"
        )


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    db: Session = Depends(get_session)
) -> dict:
    """Delete an MCP server."""
    try:
        logger.info("Deleting server", extra={"server_id": server_id})
        
        server = db.execute(
            select(MCPServer).where(MCPServer.id == server_id)
        ).scalar_one_or_none()
        
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        db.delete(server)
        db.commit()
        
        logger.info("Server deleted successfully", extra={"server_id": server_id})
        
        return {"success": True, "message": "Server deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Server deletion failed", extra={
            "server_id": server_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server deletion failed"
        )


@router.post("/servers/{server_id}/test", response_model=TestConnectionResponse)
async def test_server_connection(
    server_id: str,
    db: Session = Depends(get_session),
    container_manager: ContainerManager = Depends(get_container_manager)
) -> TestConnectionResponse:
    """Test connection to an MCP server."""
    try:
        logger.info("Testing server connection", extra={"server_id": server_id})
        
        server = db.execute(
            select(MCPServer).where(MCPServer.id == server_id)
        ).scalar_one_or_none()
        
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        # Create a test container session
        session_id = await container_manager.create_session(server)
        
        try:
            # Start the session
            started = await container_manager.start_session(session_id)
            
            if not started:
                return TestConnectionResponse(
                    success=False,
                    error="Failed to start container",
                    details={"container_status": "failed_to_start"}
                )
            
            # Run a simple test command
            result = await container_manager.execute_command(
                session_id,
                "echo 'Container test successful'"
            )
            
            success = result.exit_code == 0
            
            # Update server health status
            server.is_healthy = success
            server.last_health_check = datetime.utcnow()
            db.commit()
            
            return TestConnectionResponse(
                success=success,
                error=result.stderr if not success else None,
                details={
                    "container_status": "running" if success else "error",
                    "test_output": result.stdout if success else result.stderr,
                    "execution_time": result.execution_time,
                    "exit_code": result.exit_code
                }
            )
            
        finally:
            # Clean up test session
            await container_manager.stop_session(session_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Server connection test failed", extra={
            "server_id": server_id,
            "error": str(e)
        })
        return TestConnectionResponse(
            success=False,
            error=str(e),
            details={"error_type": type(e).__name__}
        ) 