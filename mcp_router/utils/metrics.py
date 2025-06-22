"""Metrics and monitoring configuration for MCP Router."""

import time
from typing import Dict, Any
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    Counter, Histogram, Gauge, Info, 
    generate_latest, CONTENT_TYPE_LATEST,
    start_http_server
)
from starlette.middleware.base import BaseHTTPMiddleware

from mcp_router.config import Settings


# Metrics definitions
http_requests_total = Counter(
    'mcp_router_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'mcp_router_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

mcp_requests_total = Counter(
    'mcp_router_mcp_requests_total',
    'Total MCP requests',
    ['server', 'method', 'status']
)

mcp_request_duration_seconds = Histogram(
    'mcp_router_mcp_request_duration_seconds',
    'MCP request duration in seconds',
    ['server', 'method']
)

active_containers = Gauge(
    'mcp_router_active_containers',
    'Number of active containers',
    ['runtime_type']
)

container_start_duration_seconds = Histogram(
    'mcp_router_container_start_duration_seconds',
    'Container startup duration in seconds',
    ['runtime_type']
)

server_health_status = Gauge(
    'mcp_router_server_health_status',
    'Health status of MCP servers (1=healthy, 0=unhealthy)',
    ['server_name']
)

database_operations_total = Counter(
    'mcp_router_database_operations_total',
    'Total database operations',
    ['operation', 'table', 'status']
)

server_info = Info(
    'mcp_router_server_info',
    'Information about MCP Router server'
)

# Application metrics
app_uptime_seconds = Gauge(
    'mcp_router_uptime_seconds',
    'Application uptime in seconds'
)

github_api_requests_total = Counter(
    'mcp_router_github_api_requests_total',
    'Total GitHub API requests',
    ['endpoint', 'status_code']
)

claude_api_requests_total = Counter(
    'mcp_router_claude_api_requests_total',
    'Total Claude API requests',
    ['operation', 'status']
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics."""
    
    async def dispatch(self, request: Request, call_next):
        """Process request and collect metrics."""
        start_time = time.time()
        
        # Extract endpoint for metrics (remove IDs and query params)
        endpoint = self._normalize_endpoint(request.url.path)
        method = request.method
        
        try:
            response = await call_next(request)
            
            # Record metrics
            duration = time.time() - start_time
            status_code = str(response.status_code)
            
            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()
            
            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
            
            return response
            
        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            
            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code="500"
            ).inc()
            
            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
            
            raise
    
    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics."""
        # Remove UUIDs and IDs
        import re
        
        # Replace UUIDs
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '/{id}',
            path
        )
        
        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)
        
        # Remove query parameters
        if '?' in path:
            path = path.split('?')[0]
        
        return path


def setup_metrics(app: FastAPI, settings: Settings) -> None:
    """Setup metrics collection for the application."""
    
    # Add metrics middleware
    app.add_middleware(MetricsMiddleware)
    
    # Set server info
    server_info.info({
        'version': '0.1.0',
        'environment': 'development' if settings.is_development else 'production',
        'mcp_mode': settings.mcp_mode
    })
    
    # Start metrics server if enabled
    if settings.enable_metrics:
        start_http_server(settings.metrics_port)
    
    # Add metrics endpoint
    @app.get("/metrics")
    async def metrics_endpoint():
        """Prometheus metrics endpoint."""
        return Response(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )


class MetricsCollector:
    """Helper class for collecting application metrics."""
    
    @staticmethod
    def record_mcp_request(server: str, method: str, duration: float, success: bool):
        """Record MCP request metrics."""
        status = "success" if success else "error"
        
        mcp_requests_total.labels(
            server=server,
            method=method,
            status=status
        ).inc()
        
        mcp_request_duration_seconds.labels(
            server=server,
            method=method
        ).observe(duration)
    
    @staticmethod
    def record_container_start(runtime_type: str, duration: float):
        """Record container startup metrics."""
        container_start_duration_seconds.labels(
            runtime_type=runtime_type
        ).observe(duration)
    
    @staticmethod
    def set_active_containers(runtime_type: str, count: int):
        """Set the number of active containers."""
        active_containers.labels(runtime_type=runtime_type).set(count)
    
    @staticmethod
    def set_server_health(server_name: str, is_healthy: bool):
        """Set server health status."""
        server_health_status.labels(server_name=server_name).set(
            1 if is_healthy else 0
        )
    
    @staticmethod
    def record_database_operation(operation: str, table: str, success: bool):
        """Record database operation metrics."""
        status = "success" if success else "error"
        
        database_operations_total.labels(
            operation=operation,
            table=table,
            status=status
        ).inc()
    
    @staticmethod
    def record_github_request(endpoint: str, status_code: int):
        """Record GitHub API request metrics."""
        github_api_requests_total.labels(
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
    
    @staticmethod
    def record_claude_request(operation: str, success: bool):
        """Record Claude API request metrics."""
        status = "success" if success else "error"
        
        claude_api_requests_total.labels(
            operation=operation,
            status=status
        ).inc()
    
    @staticmethod
    def update_uptime(start_time: float):
        """Update application uptime."""
        uptime = time.time() - start_time
        app_uptime_seconds.set(uptime)


# Decorator for automatic metrics collection
def track_time(metric_name: str, labels: Dict[str, str] = None):
    """Decorator to track execution time of functions."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Record success metric
                if metric_name == "mcp_request":
                    MetricsCollector.record_mcp_request(
                        labels.get("server", "unknown"),
                        labels.get("method", "unknown"),
                        duration,
                        True
                    )
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                
                # Record error metric
                if metric_name == "mcp_request":
                    MetricsCollector.record_mcp_request(
                        labels.get("server", "unknown"),
                        labels.get("method", "unknown"),
                        duration,
                        False
                    )
                
                raise
        
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Record success metric
                if metric_name == "database_operation":
                    MetricsCollector.record_database_operation(
                        labels.get("operation", "unknown"),
                        labels.get("table", "unknown"),
                        True
                    )
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                
                # Record error metric
                if metric_name == "database_operation":
                    MetricsCollector.record_database_operation(
                        labels.get("operation", "unknown"),
                        labels.get("table", "unknown"),
                        False
                    )
                
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator 