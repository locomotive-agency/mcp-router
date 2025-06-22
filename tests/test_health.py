"""Tests for health check endpoints."""

import pytest
from fastapi.testclient import TestClient

from mcp_router.main import create_app
from mcp_router.config import Settings


@pytest.fixture
def test_settings():
    """Create test settings."""
    return Settings(
        debug=True,
        database_url="sqlite:///test.db",
        anthropic_api_key="test-key",
        secret_key="test-secret",
        enable_metrics=False  # Disable metrics for testing
    )


@pytest.fixture
def test_app(test_settings):
    """Create test application."""
    return create_app(test_settings)


@pytest.fixture
def client(test_app):
    """Create test client."""
    with TestClient(test_app) as c:
        yield c


def test_liveness_probe(client):
    """Test liveness probe endpoint."""
    response = client.get("/api/health/live")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data
    assert "uptime" in data


def test_health_check_structure(client):
    """Test health check endpoint structure."""
    response = client.get("/api/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "services" in data
    assert "version" in data
    
    # Check that required services are present
    services = data["services"]
    assert "database" in services
    assert "containers" in services
    assert "external_services" in services 