"""PostgreSQL Row Level Security (RLS) Integration Tests.

These tests execute actual HTTP PostgREST / Supabase queries using standard authenticated
user sessions (User A and User B) to verify database-level RLS policies.

IMPORTANT:
- Tests do NOT use the service-role key (service-role key bypasses RLS).
- Uses standard anon key + User A / User B access tokens.
- Verifies:
  1. User A can access own records.
  2. User B can access own records.
  3. User A cannot read User B's records.
  4. User A cannot update or delete User B's records.
  5. Unauthenticated requests cannot read private records.
"""

import os
import uuid
import pytest
import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
USER_A_TOKEN = os.getenv("SUPABASE_USER_A_TOKEN")
USER_B_TOKEN = os.getenv("SUPABASE_USER_B_TOKEN")

requires_live_supabase = pytest.mark.skipif(
    not (SUPABASE_URL and SUPABASE_ANON_KEY and USER_A_TOKEN and USER_B_TOKEN),
    reason=(
        "Live Supabase integration credentials not configured in environment. "
        "Set SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_USER_A_TOKEN, and SUPABASE_USER_B_TOKEN "
        "to run actual database RLS integration tests."
    ),
)


@pytest.fixture
def postgrest_url():
    return f"{SUPABASE_URL.rstrip('/')}/rest/v1"


@pytest.fixture
def headers_user_a():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {USER_A_TOKEN}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


@pytest.fixture
def headers_user_b():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {USER_B_TOKEN}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


@pytest.fixture
def headers_anon():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }


@requires_live_supabase
@pytest.mark.asyncio
async def test_live_rls_isolation_tasks(postgrest_url, headers_user_a, headers_user_b, headers_anon):
    """Verify live PostgreSQL RLS isolation between User A and User B on the tasks table."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. User A inserts a task
        task_a_title = f"Task User A - {uuid.uuid4()}"
        res_create_a = await client.post(
            f"{postgrest_url}/tasks",
            headers=headers_user_a,
            json={"title": task_a_title, "status": "todo", "priority": "high"},
        )
        assert res_create_a.status_code == 201, f"Failed to create User A task: {res_create_a.text}"
        task_a = res_create_a.json()[0]
        task_a_id = task_a["id"]

        # 2. User B inserts a task
        task_b_title = f"Task User B - {uuid.uuid4()}"
        res_create_b = await client.post(
            f"{postgrest_url}/tasks",
            headers=headers_user_b,
            json={"title": task_b_title, "status": "todo", "priority": "medium"},
        )
        assert res_create_b.status_code == 201, f"Failed to create User B task: {res_create_b.text}"
        task_b = res_create_b.json()[0]
        task_b_id = task_b["id"]

        try:
            # 3. User A can read their own task
            res_read_a = await client.get(
                f"{postgrest_url}/tasks?id=eq.{task_a_id}",
                headers=headers_user_a,
            )
            assert res_read_a.status_code == 200
            assert len(res_read_a.json()) == 1
            assert res_read_a.json()[0]["title"] == task_a_title

            # 4. User B can read their own task
            res_read_b = await client.get(
                f"{postgrest_url}/tasks?id=eq.{task_b_id}",
                headers=headers_user_b,
            )
            assert res_read_b.status_code == 200
            assert len(res_read_b.json()) == 1
            assert res_read_b.json()[0]["title"] == task_b_title

            # 5. User A CANNOT read User B's task (RLS returns empty array)
            res_a_read_b = await client.get(
                f"{postgrest_url}/tasks?id=eq.{task_b_id}",
                headers=headers_user_a,
            )
            assert res_a_read_b.status_code == 200
            assert len(res_a_read_b.json()) == 0, "Security Violation: User A was able to read User B's task!"

            # 6. User A CANNOT update User B's task (RLS denies update, affects 0 rows)
            res_a_update_b = await client.patch(
                f"{postgrest_url}/tasks?id=eq.{task_b_id}",
                headers=headers_user_a,
                json={"title": "Hacked by User A"},
            )
            assert res_a_update_b.status_code in (200, 204)
            # Verify User B's task remains unchanged
            verify_b = await client.get(
                f"{postgrest_url}/tasks?id=eq.{task_b_id}",
                headers=headers_user_b,
            )
            assert verify_b.json()[0]["title"] == task_b_title, "Security Violation: User A modified User B's task!"

            # 7. User A CANNOT delete User B's task
            res_a_delete_b = await client.delete(
                f"{postgrest_url}/tasks?id=eq.{task_b_id}",
                headers=headers_user_a,
            )
            assert res_a_delete_b.status_code in (200, 204)
            # Verify task still exists for User B
            verify_b_exists = await client.get(
                f"{postgrest_url}/tasks?id=eq.{task_b_id}",
                headers=headers_user_b,
            )
            assert len(verify_b_exists.json()) == 1, "Security Violation: User A deleted User B's task!"

            # 8. Unauthenticated requests CANNOT read private records
            res_anon_read = await client.get(
                f"{postgrest_url}/tasks?id=eq.{task_a_id}",
                headers=headers_anon,
            )
            assert res_anon_read.status_code in (401, 200)
            if res_anon_read.status_code == 200:
                assert len(res_anon_read.json()) == 0, "Security Violation: Anon read private user task!"

        finally:
            # Cleanup records
            await client.delete(f"{postgrest_url}/tasks?id=eq.{task_a_id}", headers=headers_user_a)
            await client.delete(f"{postgrest_url}/tasks?id=eq.{task_b_id}", headers=headers_user_b)


@requires_live_supabase
@pytest.mark.asyncio
async def test_live_rls_isolation_journal_entries(postgrest_url, headers_user_a, headers_user_b):
    """Verify live PostgreSQL RLS isolation on private journal entries."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # User B creates private journal entry
        secret_content = f"Deeply confidential thoughts - {uuid.uuid4()}"
        res_create = await client.post(
            f"{postgrest_url}/journal_entries",
            headers=headers_user_b,
            json={"title": "Private Diary", "content": secret_content, "is_private": True},
        )
        assert res_create.status_code == 201
        journal_id = res_create.json()[0]["id"]

        try:
            # User A attempts to read User B's journal entry directly
            res_spy = await client.get(
                f"{postgrest_url}/journal_entries?id=eq.{journal_id}",
                headers=headers_user_a,
            )
            assert res_spy.status_code == 200
            assert len(res_spy.json()) == 0, "Critical Security Violation: User A read User B's private journal!"
        finally:
            await client.delete(f"{postgrest_url}/journal_entries?id=eq.{journal_id}", headers=headers_user_b)
