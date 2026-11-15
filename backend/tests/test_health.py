"""Tests for the service health check endpoint."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify that /api/v1/health returns HTTP 200 and expected payload structure."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "app_name" in data
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


def test_root_endpoint():
    """Verify that root endpoint provides API navigation info."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["health"] == "/api/v1/health"
    assert data["docs"] == "/docs"

