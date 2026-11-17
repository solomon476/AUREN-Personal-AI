"""Tests for Web API and Worker deployment startup configurations.

Verifies:
1. FastAPI app initializes with expected metadata, lifespans, and routers.
2. Production CORS policy rejects untrusted origins and permits allowed origins.
3. Memory Worker startup configuration enforces login-role safety (auren_worker_service).
4. Memory Worker disabled flag cleanly bypasses worker startup.
5. Railway configuration artifacts exist and define expected entry points.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.memory.runner import WorkerRunner, main_async

client = TestClient(app)


def test_api_startup_and_health():
    """Verify Web API initializes and serves health check without error."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["app_name"] == settings.APP_NAME


def test_cors_origin_policy():
    """Verify CORS preflight handling for allowed and rejected origins."""
    # Test allowed origin from settings
    allowed_origin = settings.CORS_ORIGINS[0]
    res_allowed = client.options(
        "/api/v1/health",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_allowed.headers.get("access-control-allow-origin") == allowed_origin

    # Test completely foreign untrusted origin
    res_blocked = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://malicious-site.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # When an origin is rejected by FastAPI CORS middleware, access-control-allow-origin is NOT present
    assert "access-control-allow-origin" not in res_blocked.headers


@pytest.mark.asyncio
async def test_worker_startup_rejects_nologin_role():
    """Verify WorkerRunner rejects connection attempts using the NOLOGIN role 'auren_worker'."""
    runner = WorkerRunner(
        database_url="postgresql://auren_worker:secret@localhost:5432/postgres"
    )
    with pytest.raises(ValueError, match="WORKER_DATABASE_URL cannot use 'auren_worker' directly"):
        await runner.initialize()


@pytest.mark.asyncio
async def test_worker_startup_requires_database_url_when_no_pool():
    """Verify WorkerRunner fails fast when no database URL or pool is provided."""
    runner = WorkerRunner(database_url=None, db_pool=None)
    with pytest.raises(ValueError, match="WORKER_DATABASE_URL or db_pool must be provided"):
        await runner.initialize()


@pytest.mark.asyncio
async def test_worker_startup_disabled_flag():
    """Verify main_async exits cleanly without starting worker when MEMORY_WORKER_ENABLED is false."""
    with patch("app.services.memory.runner.default_settings.MEMORY_WORKER_ENABLED", False):
        with patch("app.services.memory.runner.WorkerRunner") as mock_runner:
            await main_async()
            mock_runner.assert_not_called()


def test_deployment_configuration_files_exist():
    """Verify that Procfile and railway.toml exist in both backend and root directories."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    backend_dir = repo_root / "backend"

    assert (backend_dir / "Procfile").is_file(), "backend/Procfile missing"
    assert (backend_dir / "railway.toml").is_file(), "backend/railway.toml missing"
    assert (repo_root / "Procfile").is_file(), "Procfile missing at repo root"
    assert (repo_root / "railway.toml").is_file(), "railway.toml missing at repo root"

    backend_procfile = (backend_dir / "Procfile").read_text()
    assert "uvicorn app.main:app" in backend_procfile
    assert "app.services.memory.runner" in backend_procfile
