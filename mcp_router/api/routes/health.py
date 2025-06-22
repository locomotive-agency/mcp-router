"""Health check API endpoints."""

import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mcp_router.models import get_session, HealthResponse, ServiceHealth
from mcp_router.utils.metrics import MetricsCollector

router = APIRouter()

# Track application start time
_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    db: Session = Depends(get_session)
) -> HealthResponse:
    """
    Comprehensive health check endpoint.
    
    Returns the overall health status of the application and its services.
    """
    services = {}
    overall_status = "healthy"
    
    # Check database health
    db_status = await _check_database_health(db)
    services["database"] = db_status
    if db_status.status != "healthy":
        overall_status = "degraded"
    
    # Check container backend health
    container_status = await _check_container_health(request)
    services["containers"] = container_status
    if container_status.status != "healthy":
        overall_status = "degraded"
    
    # Check external services health
    external_status = await _check_external_services_health(request)
    services["external_services"] = external_status
    if external_status.status != "healthy" and overall_status == "healthy":
        overall_status = "degraded"
    
    # Update uptime metrics
    MetricsCollector.update_uptime(_start_time)
    
    # Set overall status to unhealthy if critical services are down
    if services["database"].status == "unhealthy":
        overall_status = "unhealthy"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        services=services,
        version="0.1.0"
    )


@router.get("/health/live")
async def liveness_probe() -> Dict[str, Any]:
    """
    Kubernetes liveness probe endpoint.
    
    Returns 200 if the application is running.
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow(),
        "uptime": time.time() - _start_time
    }


@router.get("/health/ready")
async def readiness_probe(
    db: Session = Depends(get_session)
) -> Dict[str, Any]:
    """
    Kubernetes readiness probe endpoint.
    
    Returns 200 if the application is ready to receive traffic.
    """
    # Check if database is accessible
    try:
        db.execute("SELECT 1")
        ready = True
        message = "Application is ready"
    except Exception as e:
        ready = False
        message = f"Database not ready: {str(e)}"
    
    if not ready:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=message)
    
    return {
        "status": "ready",
        "timestamp": datetime.utcnow(),
        "message": message
    }


async def _check_database_health(db: Session) -> ServiceHealth:
    """Check database connectivity and performance."""
    start_time = time.time()
    
    try:
        # Simple connectivity test
        result = db.execute("SELECT 1")
        
        # Performance test
        response_time = time.time() - start_time
        
        if response_time < 0.1:  # Less than 100ms
            status = "healthy"
        elif response_time < 1.0:  # Less than 1 second
            status = "degraded"
        else:
            status = "unhealthy"
        
        details = {
            "response_time": response_time,
            "connection_pool": "active"
        }
        
    except Exception as e:
        status = "unhealthy"
        details = {
            "error": str(e),
            "connection_pool": "failed"
        }
    
    return ServiceHealth(
        status=status,
        last_check=datetime.utcnow(),
        details=details
    )


async def _check_container_health(request: Request) -> ServiceHealth:
    """Check container backend health."""
    try:
        settings = request.app.state.settings
        
        if settings.container_backend == "docker":
            # Check Docker daemon
            import docker
            try:
                client = docker.from_env()
                client.ping()
                status = "healthy"
                details = {
                    "backend": "docker",
                    "docker_version": client.version()["Version"]
                }
            except Exception as e:
                status = "unhealthy"
                details = {
                    "backend": "docker",
                    "error": str(e)
                }
        else:
            # E2B backend check would go here
            status = "healthy"
            details = {
                "backend": "e2b",
                "status": "not_implemented"
            }
    
    except Exception as e:
        status = "unhealthy"
        details = {
            "error": str(e)
        }
    
    return ServiceHealth(
        status=status,
        last_check=datetime.utcnow(),
        details=details
    )


async def _check_external_services_health(request: Request) -> ServiceHealth:
    """Check external services health."""
    details = {}
    statuses = []
    
    try:
        settings = request.app.state.settings
        
        # Check Claude API
        if settings.anthropic_api_key:
            claude_status = await _check_claude_api(settings.anthropic_api_key)
            details["claude"] = claude_status
            statuses.append(claude_status["status"])
        
        # Check GitHub API
        if settings.github_token:
            github_status = await _check_github_api(settings.github_token)
            details["github"] = github_status
            statuses.append(github_status["status"])
        
        # Determine overall external services status
        if not statuses:
            status = "healthy"  # No external services configured
        elif all(s == "healthy" for s in statuses):
            status = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            status = "degraded"
        else:
            status = "degraded"
    
    except Exception as e:
        status = "unhealthy"
        details = {"error": str(e)}
    
    return ServiceHealth(
        status=status,
        last_check=datetime.utcnow(),
        details=details
    )


async def _check_claude_api(api_key: str) -> Dict[str, Any]:
    """Check Claude API connectivity."""
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key},
                timeout=5.0
            )
            
            if response.status_code in [200, 400, 401]:  # API is responding
                status = "healthy"
                details = {"response_code": response.status_code}
            else:
                status = "degraded"
                details = {"response_code": response.status_code}
    
    except Exception as e:
        status = "unhealthy"
        details = {"error": str(e)}
    
    return {"status": status, "details": details}


async def _check_github_api(token: str) -> Dict[str, Any]:
    """Check GitHub API connectivity."""
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/rate_limit",
                headers={"Authorization": f"token {token}"},
                timeout=5.0
            )
            
            if response.status_code == 200:
                status = "healthy"
                data = response.json()
                details = {
                    "rate_limit_remaining": data.get("rate", {}).get("remaining", 0)
                }
            else:
                status = "degraded"
                details = {"response_code": response.status_code}
    
    except Exception as e:
        status = "unhealthy"
        details = {"error": str(e)}
    
    return {"status": status, "details": details} 