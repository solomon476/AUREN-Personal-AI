"""Tests for Journal and Settings / Profile API endpoints.

Verifies:
1. Unauthenticated requests to /journal and /auth are rejected with 401.
2. Authenticated user can create, list, retrieve, update, and delete journal entries.
3. Strict tenant isolation: User B cannot access or modify User A's journal entries.
4. User profile and preferences can be retrieved and patched.
5. Personal data export bundles tasks, projects, goals, memories, and journal entries.
"""

from datetime import date
from unittest.mock import patch
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app
from app.models.user import AuthenticatedUser

client = TestClient(app)

USER_A_ID = UUID("33333333-3333-3333-3333-333333333333")
USER_B_ID = UUID("44444444-4444-4444-4444-444444444444")

USER_A = AuthenticatedUser(
    id=USER_A_ID,
    email="usera_journal@example.com",
    role="authenticated",
    token="token-a",
)

USER_B = AuthenticatedUser(
    id=USER_B_ID,
    email="userb_journal@example.com",
    role="authenticated",
    token="token-b",
)


@pytest.fixture(autouse=True)
def cleanup_deps():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_journal_unauthenticated_rejected():
    """Verify that unauthenticated calls to /api/v1/journal return 401."""
    res = client.get("/api/v1/journal")
    assert res.status_code == 401

    res_post = client.post("/api/v1/journal", json={"content": "Secret journal"})
    assert res_post.status_code == 401


def test_journal_crud_flow_and_filtering():
    """Verify complete CRUD flow, pagination, and filtering for authenticated user."""
    app.dependency_overrides[get_current_user] = lambda: USER_A

    # 1. Create entry
    create_res = client.post(
        "/api/v1/journal",
        json={
            "title": "Deep Work Reflection",
            "content": "Made significant progress on AUREN personal AI command center.",
            "mood": "focused",
            "tags": ["productivity", "engineering"],
            "entry_date": "2026-11-20",
        },
    )
    assert create_res.status_code == 201
    entry_data = create_res.json()
    entry_id = entry_data["id"]
    assert entry_data["title"] == "Deep Work Reflection"
    assert entry_data["mood"] == "focused"
    assert entry_data["is_private"] is True
    assert entry_data["tags"] == ["productivity", "engineering"]

    # 2. Get entry by ID
    get_res = client.get(f"/api/v1/journal/{entry_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == entry_id

    # 3. List entries with filter
    list_res = client.get("/api/v1/journal?mood=focused")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(item["id"] == entry_id for item in list_data["items"])

    # 4. Search query filter
    search_res = client.get("/api/v1/journal?query=AUREN")
    assert search_res.status_code == 200
    assert any(item["id"] == entry_id for item in search_res.json()["items"])

    # 5. Update entry
    update_res = client.patch(
        f"/api/v1/journal/{entry_id}",
        json={"title": "Updated Deep Work Reflection", "mood": "energized"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Updated Deep Work Reflection"
    assert update_res.json()["mood"] == "energized"

    # 6. Delete entry
    del_res = client.delete(f"/api/v1/journal/{entry_id}")
    assert del_res.status_code == 204

    # 7. Verify deletion
    verify_res = client.get(f"/api/v1/journal/{entry_id}")
    assert verify_res.status_code == 404


def test_journal_strict_tenant_isolation():
    """Verify User B cannot access or delete User A's journal entry."""
    # User A creates entry
    app.dependency_overrides[get_current_user] = lambda: USER_A
    create_res = client.post(
        "/api/v1/journal",
        json={"title": "User A Private Note", "content": "Confidential content"},
    )
    entry_id = create_res.json()["id"]

    # Switch to User B
    app.dependency_overrides[get_current_user] = lambda: USER_B

    # User B tries to read User A's entry
    get_res = client.get(f"/api/v1/journal/{entry_id}")
    assert get_res.status_code == 404

    # User B tries to update User A's entry
    patch_res = client.patch(f"/api/v1/journal/{entry_id}", json={"content": "Tampered"})
    assert patch_res.status_code == 404

    # User B tries to delete User A's entry
    del_res = client.delete(f"/api/v1/journal/{entry_id}")
    assert del_res.status_code == 404

    # User A verifies entry is intact
    app.dependency_overrides[get_current_user] = lambda: USER_A
    intact_res = client.get(f"/api/v1/journal/{entry_id}")
    assert intact_res.status_code == 200
    assert intact_res.json()["content"] == "Confidential content"


def test_profile_and_preferences_endpoints():
    """Verify profile retrieval and preferences patch."""
    app.dependency_overrides[get_current_user] = lambda: USER_A

    # Get initial profile
    profile_res = client.get("/api/v1/auth/me")
    assert profile_res.status_code == 200
    profile_data = profile_res.json()
    assert profile_data["id"] == str(USER_A_ID)

    # Patch profile preferences
    patch_res = client.patch(
        "/api/v1/auth/profile",
        json={
            "full_name": "Dr. Auren User",
            "preferences": {
                "theme": "dark",
                "ai_model": "gemini-2.5-flash",
                "ai_tone": "concise",
                "memory_auto_extraction": True,
            },
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["full_name"] == "Dr. Auren User"
    assert updated["preferences"]["theme"] == "dark"
    assert updated["preferences"]["ai_model"] == "gemini-2.5-flash"


def test_user_data_export_flow():
    """Verify GDPR data export bundles user records."""
    app.dependency_overrides[get_current_user] = lambda: USER_A

    export_res = client.post("/api/v1/auth/export")
    assert export_res.status_code == 200
    bundle = export_res.json()
    assert bundle["user_id"] == str(USER_A_ID)
    assert "exported_at" in bundle
    assert "tasks" in bundle
    assert "projects" in bundle
    assert "goals" in bundle
    assert "memories" in bundle
    assert "journal_entries" in bundle
