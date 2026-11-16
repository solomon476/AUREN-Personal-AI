"""Integration and unit tests for Productivity API endpoints:
Tasks, Projects, Goals, Dashboard, and Conversational Context.
"""

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
    """Configure settings for isolated test execution."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "CHAT_REPOSITORY_TYPE", "sqlite")


def create_test_token(user_id: str, email: str = "prod_tester@example.com") -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Productivity Tester"},
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def user_a():
    uid = str(uuid4())
    token = create_test_token(uid, "user_a@example.com")
    return {"id": uid, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def user_b():
    uid = str(uuid4())
    token = create_test_token(uid, "user_b@example.com")
    return {"id": uid, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


# ============================================================================
# 1. Unauthenticated Access Rejection
# ============================================================================

def test_unauthenticated_requests_rejected():
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.post("/api/v1/tasks", json={"title": "foo"}).status_code == 401
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/goals").status_code == 401
    assert client.get("/api/v1/productivity/dashboard").status_code == 401
    assert client.get("/api/v1/productivity/context").status_code == 401


# ============================================================================
# 2. Tasks API Endpoints & Lifecycle
# ============================================================================

def test_task_api_crud_and_status(user_a, user_b):
    # Create task
    create_payload = {
        "title": "Build UI Mockups",
        "description": "Figma design for dashboard",
        "status": "todo",
        "priority": "high",
        "tags": ["design", "ui"],
    }
    res = client.post("/api/v1/tasks", json=create_payload, headers=user_a["headers"])
    assert res.status_code == 201
    task = res.json()
    task_id = task["id"]
    assert task["title"] == "Build UI Mockups"
    assert task["status"] == "todo"
    assert task["completed_at"] is None

    # Get task as User A
    res_get = client.get(f"/api/v1/tasks/{task_id}", headers=user_a["headers"])
    assert res_get.status_code == 200
    assert res_get.json()["id"] == task_id

    # Cross-user isolation: User B cannot get User A's task -> 404
    res_b = client.get(f"/api/v1/tasks/{task_id}", headers=user_b["headers"])
    assert res_b.status_code == 404

    # Update task status to completed
    res_status = client.post(
        f"/api/v1/tasks/{task_id}/status?new_status=completed",
        headers=user_a["headers"],
    )
    assert res_status.status_code == 200
    updated = res_status.json()
    assert updated["status"] == "completed"
    assert updated["completed_at"] is not None

    # Filter tasks by status
    res_list = client.get("/api/v1/tasks?status=completed", headers=user_a["headers"])
    assert res_list.status_code == 200
    data = res_list.json()
    assert any(t["id"] == task_id for t in data["items"])

    # Delete task
    res_del = client.delete(f"/api/v1/tasks/{task_id}", headers=user_a["headers"])
    assert res_del.status_code == 204
    assert client.get(f"/api/v1/tasks/{task_id}", headers=user_a["headers"]).status_code == 404


# ============================================================================
# 3. Projects API Endpoints & Derived Progress
# ============================================================================

def test_project_api_with_tasks_and_derived_progress(user_a, user_b):
    # Create project
    proj_res = client.post(
        "/api/v1/projects",
        json={"name": "Frontend Overhaul", "description": "Migrate to Vite 6", "color": "#10b981"},
        headers=user_a["headers"],
    )
    assert proj_res.status_code == 201
    proj = proj_res.json()
    proj_id = proj["id"]
    assert proj["progress_percentage"] == 0.0

    # Add two tasks
    t1_res = client.post(
        "/api/v1/tasks",
        json={"title": "Setup tooling", "project_id": proj_id, "status": "completed"},
        headers=user_a["headers"],
    )
    assert t1_res.status_code == 201

    t2_res = client.post(
        "/api/v1/tasks",
        json={"title": "Refactor router", "project_id": proj_id, "status": "todo"},
        headers=user_a["headers"],
    )
    assert t2_res.status_code == 201

    # Get project detail -> 1 completed out of 2 tasks = 50.0%
    detail_res = client.get(f"/api/v1/projects/{proj_id}", headers=user_a["headers"])
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["task_count"] == 2
    assert detail["completed_task_count"] == 1
    assert detail["progress_percentage"] == 50.0
    assert len(detail["tasks"]) == 2

    # Cross-user isolation: User B cannot access User A's project
    assert client.get(f"/api/v1/projects/{proj_id}", headers=user_b["headers"]).status_code == 404

    # Delete project with default delete_tasks=False
    del_res = client.delete(f"/api/v1/projects/{proj_id}", headers=user_a["headers"])
    assert del_res.status_code == 204

    # Verify project deleted but tasks unlinked (project_id is None)
    t2_check = client.get(f"/api/v1/tasks/{t2_res.json()['id']}", headers=user_a["headers"])
    assert t2_check.status_code == 200
    assert t2_check.json()["project_id"] is None


# ============================================================================
# 4. Goals API Endpoints & Measurable Progress
# ============================================================================

def test_goal_api_progress_and_relationships(user_a):
    # Create goal with measurable target
    goal_res = client.post(
        "/api/v1/goals",
        json={
            "title": "Read 12 Technical Books",
            "target_value": 12.0,
            "current_value": 3.0,
            "unit": "books",
            "status": "in_progress",
        },
        headers=user_a["headers"],
    )
    assert goal_res.status_code == 201
    goal = goal_res.json()
    goal_id = goal["id"]
    assert goal["progress_percentage"] == 25.0

    # Link a project to this goal
    p_res = client.post(
        "/api/v1/projects",
        json={"name": "Distributed Systems Reading", "goal_id": goal_id},
        headers=user_a["headers"],
    )
    assert p_res.status_code == 201

    # Link a task to this goal
    t_res = client.post(
        "/api/v1/tasks",
        json={"title": "Finish Chapter 4", "goal_id": goal_id},
        headers=user_a["headers"],
    )
    assert t_res.status_code == 201

    # Get goal detail -> verify projects and tasks are populated
    detail_res = client.get(f"/api/v1/goals/{goal_id}", headers=user_a["headers"])
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert len(detail["projects"]) == 1
    assert len(detail["tasks"]) == 1
    assert detail["project_count"] == 1
    assert detail["task_count"] == 1

    # Delete goal -> project and task are unlinked (goal_id is None)
    client.delete(f"/api/v1/goals/{goal_id}", headers=user_a["headers"])
    p_check = client.get(f"/api/v1/projects/{p_res.json()['id']}", headers=user_a["headers"])
    assert p_check.json()["goal_id"] is None


# ============================================================================
# 5. Productivity Dashboard & Conversational Context
# ============================================================================

def test_productivity_dashboard_and_context_endpoints(user_a):
    # Seed a project and task
    client.post(
        "/api/v1/projects",
        json={"name": "Kernel Tuning", "status": "active"},
        headers=user_a["headers"],
    )
    client.post(
        "/api/v1/tasks",
        json={"title": "Benchmark I/O throughput", "status": "in_progress", "priority": "urgent"},
        headers=user_a["headers"],
    )

    # Dashboard endpoint
    dash_res = client.get("/api/v1/productivity/dashboard", headers=user_a["headers"])
    assert dash_res.status_code == 200
    dash = dash_res.json()
    assert dash["active_tasks_count"] >= 1
    assert dash["active_projects_count"] >= 1
    assert len(dash["upcoming_tasks"]) >= 1

    # Context endpoint (read-only conversational AI summary)
    ctx_res = client.get("/api/v1/productivity/context", headers=user_a["headers"])
    assert ctx_res.status_code == 200
    ctx = ctx_res.json()
    assert ctx["total_active_tasks"] >= 1
    assert ctx["total_active_projects"] >= 1
    assert any("Kernel Tuning" in p for p in ctx["active_projects_summary"])
    assert any("Benchmark I/O throughput" in t for t in ctx["pending_tasks_summary"])

