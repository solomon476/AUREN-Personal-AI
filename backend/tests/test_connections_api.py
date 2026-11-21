"""Tests for Trusted Connections, Invitation Codes, and Location Sharing."""

from uuid import UUID
import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app
from app.models.user import AuthenticatedUser

client = TestClient(app)

USER_A_ID = UUID("aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B_ID = UUID("bbbbbbb2-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

USER_A = AuthenticatedUser(
    id=USER_A_ID,
    email="usera_connections@example.com",
    role="authenticated",
    token="token-a",
)

USER_B = AuthenticatedUser(
    id=USER_B_ID,
    email="userb_connections@example.com",
    role="authenticated",
    token="token-b",
)


@pytest.fixture(autouse=True)
def cleanup_deps():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_connections_unauthenticated_rejected():
    res = client.get("/api/v1/connections")
    assert res.status_code == 401


def test_connection_invite_and_mutual_acceptance():
    # User A creates an invite for Marcus
    app.dependency_overrides[get_current_user] = lambda: USER_A
    invite_res = client.post("/api/v1/connections/invite", json={"display_name": "Marcus Vance"})
    assert invite_res.status_code == 201
    invite_data = invite_res.json()
    assert invite_data["display_name"] == "Marcus Vance"
    assert invite_data["status"] == "pending"
    assert invite_data["invite_code"].startswith("aur_")
    invite_code = invite_data["invite_code"]
    conn_id = invite_data["id"]

    # Verify pending state in User A's list
    list_a = client.get("/api/v1/connections").json()
    assert any(c["id"] == conn_id for c in list_a["pending_requests"])

    # User A cannot accept their own invite
    self_accept = client.post("/api/v1/connections/accept", json={"invite_code": invite_code})
    assert self_accept.status_code == 400

    # User B accepts the invite
    app.dependency_overrides[get_current_user] = lambda: USER_B
    accept_res = client.post("/api/v1/connections/accept", json={"invite_code": invite_code})
    assert accept_res.status_code == 200
    accepted_data = accept_res.json()
    assert accepted_data["status"] == "accepted"
    assert accepted_data["connected_user_id"] == str(USER_B_ID)

    # Both users now see the connection in active_connections
    list_b = client.get("/api/v1/connections").json()
    assert any(c["id"] == conn_id for c in list_b["active_connections"])

    app.dependency_overrides[get_current_user] = lambda: USER_A
    list_a2 = client.get("/api/v1/connections").json()
    assert any(c["id"] == conn_id for c in list_a2["active_connections"])


def test_voluntary_location_sharing_toggle_and_live_update():
    app.dependency_overrides[get_current_user] = lambda: USER_A

    # Enable location sharing for 120 minutes
    toggle_res = client.post(
        "/api/v1/connections/location-sharing",
        json={"enabled": True, "duration_minutes": 120},
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["location_sharing_active"] is True
    assert toggle_res.json()["duration_minutes"] == 120

    # Submit live GPS fix
    loc_res = client.post(
        "/api/v1/connections/location",
        json={"latitude": 37.7749, "longitude": -122.4194, "accuracy": 5.0},
    )
    assert loc_res.status_code == 200

    # Disable location sharing
    disable_res = client.post(
        "/api/v1/connections/location-sharing",
        json={"enabled": False},
    )
    assert disable_res.status_code == 200
    assert disable_res.json()["location_sharing_active"] is False


def test_revoke_connection():
    app.dependency_overrides[get_current_user] = lambda: USER_A

    # Create invite
    invite_res = client.post("/api/v1/connections/invite", json={"display_name": "Elena Rostova"})
    conn_id = invite_res.json()["id"]

    # Revoke connection
    del_res = client.delete(f"/api/v1/connections/{conn_id}")
    assert del_res.status_code == 204

    # Verify absence from active and pending
    list_res = client.get("/api/v1/connections").json()
    assert not any(c["id"] == conn_id for c in list_res["pending_requests"])
    assert not any(c["id"] == conn_id for c in list_res["active_connections"])

