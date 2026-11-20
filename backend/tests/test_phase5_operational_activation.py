"""End-to-End Operational Activation & Integration Verification Suite for AUREN Phase 5.

Verifies the live operational integrity of the system:
1. Health & Service Diagnostics (/api/v1/health)
2. Authentication, User Session Scoping, Preferences & Data Export (/api/v1/auth)
3. Chat Completion & SSE Streaming with Model Selection & Idempotency (/api/v1/chat)
4. Long-Term Memory Lifecycle, Epistemic Correction, Lineage & Tenant Isolation (/api/v1/memories)
5. Productivity Domain: Tasks, Projects, Goals CRUD & Scoping (/api/v1/tasks, /projects, /goals)
6. Private Journal Cryptographic Quarantine & Tenant Isolation (/api/v1/journal)
7. Cross-Domain Omnisearch Query Execution (/api/v1/search)
"""

import json
import time
from uuid import UUID, uuid4
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)
TEST_JWT_SECRET = "super-secret-test-key-for-supabase-jwt-verification-unit-tests"


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """Ensure consistent test isolation with SQLite repository and deterministic test JWT secret."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "CHAT_REPOSITORY_TYPE", "sqlite")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")


def create_test_jwt(user_id: str, email: str = "operator@auren.local") -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 7200,
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Operational Operator"},
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def operator_a():
    uid = str(uuid4())
    token = create_test_jwt(uid, "operator_a@auren.local")
    return {"id": uid, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def operator_b():
    uid = str(uuid4())
    token = create_test_jwt(uid, "operator_b@auren.local")
    return {"id": uid, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


# ============================================================================
# 1. Health & Diagnostics
# ============================================================================

def test_service_health_endpoint():
    """Verify health endpoint responds with healthy operational status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "AUREN" in data["app_name"]
    assert "version" in data
    assert "environment" in data


# ============================================================================
# 2. Authentication, User Session Scoping & Data Export
# ============================================================================

def test_auth_unauthenticated_rejection():
    """Verify that unauthenticated requests to protected endpoints return 401."""
    protected_urls = [
        "/api/v1/auth/me",
        "/api/v1/journal",
        "/api/v1/memories",
        "/api/v1/tasks",
        "/api/v1/projects",
        "/api/v1/goals",
        "/api/v1/search?q=test",
    ]
    for url in protected_urls:
        res = client.get(url)
        assert res.status_code == 401, f"Expected 401 for unauthenticated {url}, got {res.status_code}"


def test_auth_invalid_token_rejection():
    """Verify that malformed or forged JWT tokens are rejected with 401."""
    res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.fake.token"})
    assert res.status_code == 401


def test_auth_user_profile_and_preferences_lifecycle(operator_a, operator_b):
    """Verify authenticated user profile retrieval, preferences update, and tenant isolation."""
    # 1. Retrieve initial profile
    res_a = client.get("/api/v1/auth/me", headers=operator_a["headers"])
    assert res_a.status_code == 200
    profile_a = res_a.json()
    assert profile_a["id"] == operator_a["id"]
    assert profile_a["email"] == "operator_a@auren.local"

    # 2. Update preferences for operator A
    patch_payload = {
        "full_name": "Lead Commander A",
        "preferences": {
            "theme": "dark",
            "communication_style": "concise",
            "voice_enabled": False,
        },
    }
    res_patch = client.patch("/api/v1/auth/profile", json=patch_payload, headers=operator_a["headers"])
    assert res_patch.status_code == 200
    updated_a = res_patch.json()
    assert updated_a["full_name"] == "Lead Commander A"
    assert updated_a["preferences"]["communication_style"] == "concise"

    # 3. Verify operator B has independent profile and default preferences
    res_b = client.get("/api/v1/auth/me", headers=operator_b["headers"])
    assert res_b.status_code == 200
    profile_b = res_b.json()
    assert profile_b["id"] == operator_b["id"]
    assert profile_b["email"] == "operator_b@auren.local"
    assert profile_b.get("full_name") != "Lead Commander A"


def test_user_personal_data_export(operator_a):
    """Verify complete personal data export package containing all domain entities."""
    # Create one memory, one task, one journal entry
    mem_res = client.post(
        "/api/v1/memories",
        json={"content": "Export test memory fact", "memory_type": "fact", "category": "general", "importance": 3},
        headers=operator_a["headers"],
    )
    assert mem_res.status_code == 201

    task_res = client.post(
        "/api/v1/tasks",
        json={"title": "Export test task", "priority": "high"},
        headers=operator_a["headers"],
    )
    assert task_res.status_code == 201

    journal_res = client.post(
        "/api/v1/journal",
        json={"content": "Export test private journal", "mood": "focused"},
        headers=operator_a["headers"],
    )
    assert journal_res.status_code == 201

    # Export personal data
    res = client.post("/api/v1/auth/export", headers=operator_a["headers"])
    assert res.status_code == 200
    export_pkg = res.json()
    assert export_pkg["user_id"] == operator_a["id"]
    assert len(export_pkg["memories"]) >= 1
    assert len(export_pkg["tasks"]) >= 1
    assert len(export_pkg["journal_entries"]) >= 1


# ============================================================================
# 3. Chat Completion & SSE Streaming with Model Routing & Idempotency
# ============================================================================

def test_chat_completion_sse_stream_and_persistence(operator_a):
    """Verify chat completions with model selection, SSE event delivery, and DB persistence."""
    req_payload = {
        "message": "Hello AUREN operational test",
        "model_id": "mock",
        "temperature": 0.5,
    }
    with client.stream(
        "POST",
        "/api/v1/chat/completions",
        json=req_payload,
        headers=operator_a["headers"],
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = "".join(response.iter_text())
        assert "event: meta" in body or "data:" in body
        assert "event: done" in body

    # Verify conversation list reflects the new session
    convs_res = client.get("/api/v1/chat/conversations", headers=operator_a["headers"])
    assert convs_res.status_code == 200
    convs = convs_res.json()
    assert len(convs) >= 1
    assert any("Hello AUREN" in c.get("title", "") for c in convs)


def test_chat_oversized_message_rejected(operator_a):
    """Verify that messages exceeding CHAT_MAX_MESSAGE_LENGTH are rejected with HTTP 413 or 422."""
    oversized = "A" * (settings.CHAT_MAX_MESSAGE_LENGTH + 100)
    res = client.post(
        "/api/v1/chat/completions",
        json={"message": oversized, "model_id": "mock"},
        headers=operator_a["headers"],
    )
    assert res.status_code in [413, 422]


def test_chat_idempotency_fingerprint_conflict(operator_a):
    """Verify that reusing the same idempotency key with conflicting prompts is safely rejected."""
    key = str(uuid4())
    # First request
    with client.stream(
        "POST",
        "/api/v1/chat/completions",
        json={"message": "First prompt", "idempotency_key": key, "model_id": "mock"},
        headers=operator_a["headers"],
    ) as r1:
        assert r1.status_code == 200
        "".join(r1.iter_text())

    # Conflicting second request with same idempotency key
    with client.stream(
        "POST",
        "/api/v1/chat/completions",
        json={"message": "Different conflicting prompt", "idempotency_key": key, "model_id": "mock"},
        headers=operator_a["headers"],
    ) as r2:
        # Either 409 status code or SSE event error with idempotency_conflict code
        if r2.status_code == 200:
            body = "".join(r2.iter_text())
            assert "idempotency_conflict" in body or "conflict" in body.lower()
        else:
            assert r2.status_code == 409


# ============================================================================
# 4. Memory Lifecycle, Epistemic Verification, Lineage & Tenant Isolation
# ============================================================================

def test_memory_lifecycle_and_lineage_preservation(operator_a, operator_b):
    """Verify memory creation, epistemic status, correction with lineage tracking, and tenant isolation."""
    # 1. Create initial memory for Operator A
    create_payload = {
        "content": "Operator prefers concise bullet-point executive summaries",
        "memory_type": "preference",
        "category": "work",
        "importance": 4,
    }
    create_res = client.post("/api/v1/memories", json=create_payload, headers=operator_a["headers"])
    assert create_res.status_code == 201
    mem_a = create_res.json()
    mem_id = mem_a["id"]
    assert mem_a["content"] == create_payload["content"]
    assert mem_a["confirmation_status"] in ["unconfirmed", "pending", "confirmed"]

    # 2. Retrieve memory by ID
    get_res = client.get(f"/api/v1/memories/{mem_id}", headers=operator_a["headers"])
    assert get_res.status_code == 200
    assert get_res.json()["id"] == mem_id

    # 3. Filter/Search memories
    search_res = client.get("/api/v1/memories?query=bullet-point", headers=operator_a["headers"])
    assert search_res.status_code == 200
    items = search_res.json()["items"]
    assert any(i["id"] == mem_id for i in items)

    # 4. Correct memory (lineage preservation)
    correction_payload = {
        "content": "Operator prefers single-paragraph executive summaries with bold action items",
        "confidence": 0.98,
        "notes": "Updated preference after direct command",
    }
    correct_res = client.post(
        f"/api/v1/memories/{mem_id}/correct",
        json=correction_payload,
        headers=operator_a["headers"],
    )
    assert correct_res.status_code in [200, 201]
    corrected_mem = correct_res.json()
    assert corrected_mem["previous_version_id"] == mem_id
    assert corrected_mem["content"] == correction_payload["content"]

    # 5. Verify the old memory is marked superseded
    old_mem_res = client.get(f"/api/v1/memories/{mem_id}", headers=operator_a["headers"])
    assert old_mem_res.status_code == 200
    old_mem = old_mem_res.json()
    assert old_mem["lifecycle_status"] == "superseded"
    assert old_mem["superseded_by_id"] == corrected_mem["id"]

    # 6. Strict Tenant Isolation: Operator B cannot access Operator A's memory
    b_access_res = client.get(f"/api/v1/memories/{mem_id}", headers=operator_b["headers"])
    assert b_access_res.status_code == 404


# ============================================================================
# 5. Productivity Domain: Tasks, Projects, Goals
# ============================================================================

def test_productivity_tasks_projects_goals_crud(operator_a, operator_b):
    """Verify Tasks, Projects, and Goals lifecycle and cross-user scoping."""
    # 1. Tasks
    task_res = client.post(
        "/api/v1/tasks",
        json={"title": "Deploy Phase 5 Staging", "priority": "urgent", "due_date": "2026-11-25T12:00:00Z"},
        headers=operator_a["headers"],
    )
    assert task_res.status_code in [200, 201]
    task = task_res.json()
    task_id = task["id"]
    assert task["title"] == "Deploy Phase 5 Staging"

    # Mark completed
    patch_task = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "completed"},
        headers=operator_a["headers"],
    )
    assert patch_task.status_code == 200
    assert patch_task.json()["status"] == "completed"

    # 2. Projects
    project_res = client.post(
        "/api/v1/projects",
        json={"name": "AUREN Operational Activation", "description": "Phase 5 end-to-end integration"},
        headers=operator_a["headers"],
    )
    assert project_res.status_code in [200, 201]
    project = project_res.json()
    project_id = project["id"]
    assert project["name"] == "AUREN Operational Activation"

    # 3. Goals
    goal_res = client.post(
        "/api/v1/goals",
        json={"title": "Achieve 100% Operational Dependability", "target_date": "2026-12-31"},
        headers=operator_a["headers"],
    )
    assert goal_res.status_code in [200, 201]
    goal = goal_res.json()
    goal_id = goal["id"]
    assert goal["title"] == "Achieve 100% Operational Dependability"

    # 4. Cross-User Scoping: Operator B cannot see Operator A's tasks, projects, or goals
    b_tasks_res = client.get("/api/v1/tasks", headers=operator_b["headers"]).json()
    b_projects_res = client.get("/api/v1/projects", headers=operator_b["headers"]).json()
    b_goals_res = client.get("/api/v1/goals", headers=operator_b["headers"]).json()

    b_task_items = b_tasks_res.get("items", [])
    b_project_items = b_projects_res.get("items", [])
    b_goal_items = b_goals_res.get("items", [])

    assert not any(t["id"] == task_id for t in b_task_items)
    assert not any(p["id"] == project_id for p in b_project_items)
    assert not any(g["id"] == goal_id for g in b_goal_items)


# ============================================================================
# 6. Private Journal Cryptographic Invariant & Quarantine
# ============================================================================

def test_private_journal_quarantine_and_isolation(operator_a, operator_b):
    """Verify that private journal entries are quarantined from assistant access and cross-tenant leakage."""
    entry_res = client.post(
        "/api/v1/journal",
        json={"content": "Top-secret personal reflection - never index into memories", "mood": "reflective"},
        headers=operator_a["headers"],
    )
    assert entry_res.status_code == 201
    entry = entry_res.json()
    entry_id = entry["id"]
    assert entry["content"] == "Top-secret personal reflection - never index into memories"

    # Retrieve entry
    get_res = client.get(f"/api/v1/journal/{entry_id}", headers=operator_a["headers"])
    assert get_res.status_code == 200
    assert get_res.json()["id"] == entry_id

    # Verify Operator B cannot access Operator A's journal entry (returns 404)
    b_entry_res = client.get(f"/api/v1/journal/{entry_id}", headers=operator_b["headers"])
    assert b_entry_res.status_code == 404

    # Verify Journal content does NOT appear in memories search
    mem_search = client.get("/api/v1/memories?query=Top-secret", headers=operator_a["headers"]).json()
    assert mem_search["total"] == 0 or not any("Top-secret" in m["content"] for m in mem_search["items"])


# ============================================================================
# 7. Cross-Domain Omnisearch
# ============================================================================

def test_omnisearch_cross_domain_query(operator_a):
    """Verify Omnisearch runs across domains for authenticated user without runtime error."""
    search_res = client.get("/api/v1/search?q=Operational", headers=operator_a["headers"])
    assert search_res.status_code == 200
    results = search_res.json()
    assert "query" in results
    assert "results" in results or "items" in results
