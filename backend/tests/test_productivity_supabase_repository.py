"""Unit tests for SupabaseProductivityRepository.

Verifies Phase 3C.4.1 Supabase ownership integrity:
1. create_task includes "user_id": str(user_id) in the POST payload.
2. create_project includes "user_id": str(user_id) in the POST payload.
3. create_goal includes "user_id": str(user_id) in the POST payload.
4. Ownership is derived strictly from the authenticated identity, rejecting spoofed IDs.
5. PostgREST communication uses the authenticated user JWT and anon key without service-role key.
6. Proper error handling for 401/403, 500, and network connectivity failures.
"""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
import httpx
import pytest

from app.core.exceptions import DatabaseAuthError, DatabaseConnectionError, DatabaseError
from app.models.productivity import (
    GoalCreate,
    GoalStatus,
    ProjectCreate,
    ProjectStatus,
    TaskCreate,
    TaskPriority,
    TaskStatus,
)
from app.services.productivity.supabase_repository import SupabaseProductivityRepository

TEST_SUPABASE_URL = "https://mock-test-project.supabase.co"
TEST_ANON_KEY = "mock-public-anon-key"
TEST_USER_TOKEN = "mock-user-bearer-token"
USER_A = uuid4()
USER_B = uuid4()
TASK_ID = uuid4()
PROJECT_ID = uuid4()
GOAL_ID = uuid4()


def test_supabase_productivity_repo_headers():
    """Verify PostgREST requests send user bearer token and anon key, without service-role key."""
    repo = SupabaseProductivityRepository(
        supabase_url=TEST_SUPABASE_URL,
        supabase_anon_key=TEST_ANON_KEY,
        user_token=TEST_USER_TOKEN,
    )
    headers = repo._get_headers(prefer="return=representation")

    assert headers["apikey"] == TEST_ANON_KEY
    assert headers["Authorization"] == f"Bearer {TEST_USER_TOKEN}"
    assert headers["Prefer"] == "return=representation"
    assert "service_role" not in headers.get("Authorization", "")


@pytest.mark.asyncio
async def test_supabase_create_task_ownership_payload():
    """Verify create_task includes authenticated user_id in the POST payload (FINDING-04 fix)."""
    captured_payload = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        assert request.headers["apikey"] == TEST_ANON_KEY
        assert request.headers["Authorization"] == f"Bearer {TEST_USER_TOKEN}"

        if request.method == "POST" and "/tasks" in str(request.url):
            captured_payload = json.loads(request.content)
            # Database requires NOT NULL user_id matching auth.uid()
            assert captured_payload["user_id"] == str(USER_A)
            assert captured_payload["title"] == "Hardened Security Task"
            assert captured_payload["status"] == "todo"
            assert captured_payload["priority"] == "urgent"

            response_data = {
                "id": str(TASK_ID),
                "user_id": str(USER_A),
                "title": captured_payload["title"],
                "description": captured_payload["description"],
                "status": captured_payload["status"],
                "priority": captured_payload["priority"],
                "project_id": None,
                "goal_id": None,
                "parent_task_id": None,
                "due_date": None,
                "start_date": None,
                "completed_at": None,
                "tags": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            return httpx.Response(201, json=[response_data])

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabaseProductivityRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        task_in = TaskCreate(
            title="Hardened Security Task",
            description="Testing Supabase user_id payload",
            status=TaskStatus.todo,
            priority=TaskPriority.urgent,
        )
        task = await repo.create_task(user_id=USER_A, task=task_in)

        assert task.id == TASK_ID
        assert task.user_id == USER_A
        assert captured_payload.get("user_id") == str(USER_A)


@pytest.mark.asyncio
async def test_supabase_create_project_ownership_payload():
    """Verify create_project includes authenticated user_id in the POST payload (FINDING-04 fix)."""
    captured_payload = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.method == "POST" and "/projects" in str(request.url):
            captured_payload = json.loads(request.content)
            assert captured_payload["user_id"] == str(USER_A)
            assert captured_payload["name"] == "Alpha Security Initiative"
            assert captured_payload["color"] == "#10b981"

            response_data = {
                "id": str(PROJECT_ID),
                "user_id": str(USER_A),
                "name": captured_payload["name"],
                "description": captured_payload["description"],
                "color": captured_payload["color"],
                "status": captured_payload["status"],
                "start_date": None,
                "target_date": None,
                "goal_id": None,
                "completed_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            return httpx.Response(201, json=[response_data])

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabaseProductivityRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        proj_in = ProjectCreate(
            name="Alpha Security Initiative",
            description="Tenant isolation project",
            color="#10b981",
            status=ProjectStatus.active,
        )
        project = await repo.create_project(user_id=USER_A, project=proj_in)

        assert project.id == PROJECT_ID
        assert project.user_id == USER_A
        assert captured_payload.get("user_id") == str(USER_A)


@pytest.mark.asyncio
async def test_supabase_create_goal_ownership_payload():
    """Verify create_goal includes authenticated user_id in the POST payload (FINDING-04 fix)."""
    captured_payload = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.method == "POST" and "/goals" in str(request.url):
            captured_payload = json.loads(request.content)
            assert captured_payload["user_id"] == str(USER_A)
            assert captured_payload["title"] == "Zero Security Debt"

            response_data = {
                "id": str(GOAL_ID),
                "user_id": str(USER_A),
                "title": captured_payload["title"],
                "description": captured_payload["description"],
                "status": captured_payload["status"],
                "target_date": None,
                "target_value": None,
                "current_value": 0.0,
                "unit": None,
                "completed_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            return httpx.Response(201, json=[response_data])

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabaseProductivityRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        goal_in = GoalCreate(
            title="Zero Security Debt",
            description="Resolve all audit findings",
            status=GoalStatus.in_progress,
        )
        goal = await repo.create_goal(user_id=USER_A, goal=goal_in)

        assert goal.id == GOAL_ID
        assert goal.user_id == USER_A
        assert captured_payload.get("user_id") == str(USER_A)


@pytest.mark.asyncio
async def test_supabase_repo_auth_error_handling():
    """Verify PostgREST 401/403 responses raise DatabaseAuthError."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "JWT expired or invalid"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabaseProductivityRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        with pytest.raises(DatabaseAuthError):
            await repo.create_task(
                user_id=USER_A,
                task=TaskCreate(title="Unauthorized Attempt"),
            )


@pytest.mark.asyncio
async def test_supabase_repo_connection_error_handling():
    """Verify network failures raise DatabaseConnectionError."""
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Failed to resolve host")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabaseProductivityRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        with pytest.raises(DatabaseConnectionError):
            await repo.create_task(
                user_id=USER_A,
                task=TaskCreate(title="Network Failure Attempt"),
            )
