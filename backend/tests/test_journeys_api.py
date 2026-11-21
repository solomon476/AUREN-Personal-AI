"""Tests for GPS Journeys API, offline sync, idempotency, and tenant isolation."""

from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app
from app.models.user import AuthenticatedUser

client = TestClient(app)

USER_1_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_2_ID = UUID("22222222-2222-2222-2222-222222222222")

USER_1 = AuthenticatedUser(
    id=USER_1_ID,
    email="user1_journeys@example.com",
    role="authenticated",
    token="token-1",
)

USER_2 = AuthenticatedUser(
    id=USER_2_ID,
    email="user2_journeys@example.com",
    role="authenticated",
    token="token-2",
)


@pytest.fixture(autouse=True)
def cleanup_deps():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_journeys_unauthenticated_rejected():
    res = client.get("/api/v1/journeys")
    assert res.status_code == 401


def test_journey_creation_and_retrieval():
    app.dependency_overrides[get_current_user] = lambda: USER_1

    payload = {
        "title": "Evening Perimeter Patrol",
        "status": "completed",
        "distance_meters": 3420.5,
        "duration_seconds": 1840,
        "avg_speed_kmh": 6.7,
        "is_offline_recorded": True,
        "is_team_assignment": True,
        "assignment_site": "Sector 4 Solar Array",
        "assignment_purpose": "Routine Sensor Audit",
        "points": [
            {"lat": 37.7749, "lng": -122.4194, "accuracy": 4.2, "timestamp": "2026-11-21T18:00:00Z"},
            {"lat": 37.7755, "lng": -122.4201, "accuracy": 3.8, "timestamp": "2026-11-21T18:05:00Z"},
        ],
        "idempotency_key": "patrol-batch-001",
    }

    create_res = client.post("/api/v1/journeys", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["title"] == "Evening Perimeter Patrol"
    assert data["distance_meters"] == 3420.5
    assert data["is_offline_recorded"] is True
    assert len(data["points"]) == 2
    journey_id = data["id"]

    # Verify listing
    list_res = client.get("/api/v1/journeys")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(j["id"] == journey_id for j in list_data["items"])

    # Verify get by ID
    get_res = client.get(f"/api/v1/journeys/{journey_id}")
    assert get_res.status_code == 200
    assert get_res.json()["assignment_site"] == "Sector 4 Solar Array"


def test_journey_idempotency_deduplication():
    app.dependency_overrides[get_current_user] = lambda: USER_1

    payload = {
        "title": "Idempotent Journey",
        "distance_meters": 1200.0,
        "duration_seconds": 600,
        "idempotency_key": "unique-idemp-key-999",
    }

    res1 = client.post("/api/v1/journeys", json=payload)
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    # Resend identical idempotency key
    res2 = client.post("/api/v1/journeys", json=payload)
    assert res2.status_code == 201
    id2 = res2.json()["id"]

    # Must return existing record without duplicate insertion
    assert id1 == id2


def test_batch_sync_offline_journeys():
    app.dependency_overrides[get_current_user] = lambda: USER_1

    batch_payload = {
        "journeys": [
            {
                "title": "Offline Journey 1",
                "distance_meters": 800.0,
                "duration_seconds": 450,
                "is_offline_recorded": True,
                "idempotency_key": "offline-sync-101",
            },
            {
                "title": "Offline Journey 2",
                "distance_meters": 1500.0,
                "duration_seconds": 900,
                "is_offline_recorded": True,
                "idempotency_key": "offline-sync-102",
            },
        ]
    }

    sync_res = client.post("/api/v1/journeys/sync-batch", json=batch_payload)
    assert sync_res.status_code == 200
    synced = sync_res.json()
    assert len(synced) == 2


def test_tenant_isolation_user_cannot_access_other_journey():
    app.dependency_overrides[get_current_user] = lambda: USER_1

    # User 1 creates journey
    res = client.post("/api/v1/journeys", json={"title": "User 1 Secret Route", "distance_meters": 500.0})
    journey_id = res.json()["id"]

    # User 2 tries to access User 1's journey
    app.dependency_overrides[get_current_user] = lambda: USER_2
    get_res = client.get(f"/api/v1/journeys/{journey_id}")
    assert get_res.status_code == 404

    delete_res = client.delete(f"/api/v1/journeys/{journey_id}")
    assert delete_res.status_code == 404

