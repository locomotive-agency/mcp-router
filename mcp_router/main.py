"""Main FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from mcp_router.config import Settings
from mcp_router.models import init_database, get_database
from mcp_router.utils.logging import setup_logging
from mcp_router.utils.metrics import setup_metrics
from mcp_router.api.routes import servers, health, config, mcp
from mcp_router.models.schemas import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    settings = app.state.settings
    
    # Setup logging
    setup_logging(settings)
    logger = logging.getLogger(__name__)
    logger.info("Starting MCP Router application", extra={"version": "0.1.0"})
    
    # Initialize database
    db_manager = init_database(settings.database_url)
    await db_manager.create_tables_async()
    app.state.db = db_manager
    logger.info("Database initialized", extra={"url": settings.database_url})
    
    # Note: Metrics middleware is set up during app creation
    if settings.enable_metrics:
        logger.info("Metrics enabled", extra={"port": settings.metrics_port})
    
    # Create data directories
    settings.data_dir.mkdir(exist_ok=True)
    settings.log_dir.mkdir(exist_ok=True)
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down MCP Router application")


def create_app(settings: Settings = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = Settings()
    
    app = FastAPI(
        title="MCP Router",
        description="A UX for adding and administering MCP servers",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan
    )
    
    # Store settings in app state
    app.state.settings = settings
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Setup metrics middleware if enabled
    if settings.enable_metrics:
        setup_metrics(app, settings)
    
    # Include routers
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(servers.router, prefix="/api", tags=["servers"])
    app.include_router(config.router, prefix="/api", tags=["config"])
    app.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
    
    # Serve static files (frontend)
    frontend_dir = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    
    # Error handlers
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error="HTTP Error",
                message=exc.detail,
                timestamp=datetime.utcnow()
            ).model_dump()
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle validation errors."""
        details = []
        for error in exc.errors():
            details.append({
                "field": ".".join(str(x) for x in error["loc"]),
                "message": error["msg"],
                "code": error["type"]
            })
        
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="Validation Error",
                message="Request validation failed",
                details=details,
                timestamp=datetime.utcnow()
            ).model_dump()
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions."""
        logger = logging.getLogger(__name__)
        logger.exception("Unhandled exception", extra={
            "path": request.url.path,
            "method": request.method,
            "error": str(exc)
        })
        
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal Server Error",
                message="An unexpected error occurred",
                timestamp=datetime.utcnow()
            ).model_dump()
        )
    
    return app


def main():
    """Main entry point for the application."""
    settings = Settings()
    
    if settings.mcp_mode == "local":
        # Run in local MCP mode (stdio)
        from mcp_router.core.router import MCPRouterServer
        router = MCPRouterServer()
        asyncio.run(router.run_stdio())
    else:
        # Run as web server
        app = create_app(settings)
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            log_config=None,  # We handle logging ourselves
            access_log=False
        )


if __name__ == "__main__":
    main() 