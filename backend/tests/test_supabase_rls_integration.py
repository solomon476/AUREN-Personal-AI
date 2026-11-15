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



@requires_live_supabase
@pytest.mark.asyncio
async def test_live_rls_isolation_conversations(postgrest_url, headers_user_a, headers_user_b, headers_anon):
    """Verify live PostgreSQL RLS isolation on conversations table."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. User A creates a conversation
        res_a = await client.post(
            f"{postgrest_url}/conversations",
            headers=headers_user_a,
            json={"title": f"User A Private Thread - {uuid.uuid4()}"},
        )
        assert res_a.status_code == 201
        conv_a_id = res_a.json()[0]["id"]

        try:
            # 2. User A can read their conversation
            read_a = await client.get(f"{postgrest_url}/conversations?id=eq.{conv_a_id}", headers=headers_user_a)
            assert read_a.status_code == 200
            assert len(read_a.json()) == 1

            # 3. User B CANNOT read User A's conversation
            read_b = await client.get(f"{postgrest_url}/conversations?id=eq.{conv_a_id}", headers=headers_user_b)
            assert read_b.status_code == 200
            assert len(read_b.json()) == 0, "Security Violation: User B read User A's conversation!"

            # 4. User B CANNOT update User A's conversation
            update_b = await client.patch(
                f"{postgrest_url}/conversations?id=eq.{conv_a_id}",
                headers=headers_user_b,
                json={"title": "Hacked Title"},
            )
            assert update_b.status_code in (200, 204)
            verify_a = await client.get(f"{postgrest_url}/conversations?id=eq.{conv_a_id}", headers=headers_user_a)
            assert verify_a.json()[0]["title"] != "Hacked Title"

            # 5. User B CANNOT delete User A's conversation
            del_b = await client.delete(f"{postgrest_url}/conversations?id=eq.{conv_a_id}", headers=headers_user_b)
            assert del_b.status_code in (200, 204)
            verify_exists = await client.get(f"{postgrest_url}/conversations?id=eq.{conv_a_id}", headers=headers_user_a)
            assert len(verify_exists.json()) == 1

            # 6. Anon CANNOT read conversation
            anon_read = await client.get(f"{postgrest_url}/conversations?id=eq.{conv_a_id}", headers=headers_anon)
            assert anon_read.status_code in (401, 200)
            if anon_read.status_code == 200:
                assert len(anon_read.json()) == 0
        finally:
            await client.delete(f"{postgrest_url}/conversations?id=eq.{conv_a_id}", headers=headers_user_a)


@requires_live_supabase
@pytest.mark.asyncio
async def test_live_rls_isolation_messages(postgrest_url, headers_user_a, headers_user_b, headers_anon):
    """Verify live PostgreSQL RLS isolation on messages table."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Setup conversation for User A
        res_conv = await client.post(
            f"{postgrest_url}/conversations",
            headers=headers_user_a,
            json={"title": "Thread for messages"},
        )
        assert res_conv.status_code == 201
        conv_id = res_conv.json()[0]["id"]

        try:
            # 1. User A creates a message
            res_msg = await client.post(
                f"{postgrest_url}/messages",
                headers=headers_user_a,
                json={"conversation_id": conv_id, "role": "user", "content": "Secret note"},
            )
            assert res_msg.status_code == 201
            msg_id = res_msg.json()[0]["id"]

            # 2. User B CANNOT read User A's message
            read_b = await client.get(f"{postgrest_url}/messages?id=eq.{msg_id}", headers=headers_user_b)
            assert read_b.status_code == 200
            assert len(read_b.json()) == 0, "Security Violation: User B read User A's message!"

            # 3. User B CANNOT inject message into User A's conversation
            inject_b = await client.post(
                f"{postgrest_url}/messages",
                headers=headers_user_b,
                json={"conversation_id": conv_id, "role": "user", "content": "Injected by B"},
            )
            assert inject_b.status_code in (400, 403, 404, 409), "Security Violation: User B inserted message into User A's conversation!"

            # 4. User B CANNOT update User A's message
            update_b = await client.patch(
                f"{postgrest_url}/messages?id=eq.{msg_id}",
                headers=headers_user_b,
                json={"content": "Hacked message content by User B"},
            )
            assert update_b.status_code in (200, 204)
            verify_a = await client.get(f"{postgrest_url}/messages?id=eq.{msg_id}", headers=headers_user_a)
            assert verify_a.json()[0]["content"] == "Secret note", "Security Violation: User B modified User A's message!"

            # 5. User B CANNOT delete User A's message
            delete_b = await client.delete(
                f"{postgrest_url}/messages?id=eq.{msg_id}",
                headers=headers_user_b,
            )
            assert delete_b.status_code in (200, 204)
            verify_exists = await client.get(f"{postgrest_url}/messages?id=eq.{msg_id}", headers=headers_user_a)
            assert len(verify_exists.json()) == 1, "Security Violation: User B deleted User A's message!"

            # 6. Anon CANNOT read message
            anon_read = await client.get(f"{postgrest_url}/messages?id=eq.{msg_id}", headers=headers_anon)
            assert anon_read.status_code in (401, 200)
            if anon_read.status_code == 200:
                assert len(anon_read.json()) == 0
        finally:
            await client.delete(f"{postgrest_url}/conversations?id=eq.{conv_id}", headers=headers_user_a)


@requires_live_supabase
@pytest.mark.asyncio
async def test_live_rls_isolation_chat_requests(postgrest_url, headers_user_a, headers_user_b, headers_anon):
    """Verify live PostgreSQL RLS isolation, exclusive RPC claiming, and lifecycle enforcement."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Setup conversation and message for User A
        res_conv = await client.post(f"{postgrest_url}/conversations", headers=headers_user_a, json={"title": "Req thread"})
        conv_id = res_conv.json()[0]["id"]
        res_msg = await client.post(f"{postgrest_url}/messages", headers=headers_user_a, json={"conversation_id": conv_id, "role": "user", "content": "Prompt"})
        msg_id = res_msg.json()[0]["id"]

        idemp_key = f"live-idemp-{uuid.uuid4()}"
        fp_a = "a" * 64
        fp_conflict = "b" * 64

        try:
            # 1. Direct authenticated INSERT is forbidden (exclusive RPC creation path)
            res_direct_insert = await client.post(
                f"{postgrest_url}/chat_requests",
                headers=headers_user_a,
                json={"idempotency_key": idemp_key, "conversation_id": conv_id, "user_message_id": msg_id, "status": "processing", "request_fingerprint": fp_a},
            )
            assert res_direct_insert.status_code in (401, 403), f"Expected permission-denied (401/403), got {res_direct_insert.status_code}: {res_direct_insert.text}"
            assert "permission denied" in res_direct_insert.text.lower() or "42501" in res_direct_insert.text

            # 2. Legitimate claim proceeds exclusively via RPC claim_chat_request
            res_rpc_claim = await client.post(
                f"{postgrest_url}/rpc/claim_chat_request",
                headers=headers_user_a,
                json={
                    "p_idempotency_key": idemp_key,
                    "p_conversation_id": conv_id,
                    "p_user_message_id": msg_id,
                    "p_request_fingerprint": fp_a,
                },
            )
            assert res_rpc_claim.status_code in (200, 201), f"Claim RPC failed: {res_rpc_claim.text}"
            data_claim = res_rpc_claim.json()
            assert data_claim["claimed"] is True
            assert data_claim["request"]["status"] == "processing"

            # 3. Duplicate claim with matching fingerprint returns existing record (claimed=False)
            res_duplicate_match = await client.post(
                f"{postgrest_url}/rpc/claim_chat_request",
                headers=headers_user_a,
                json={
                    "p_idempotency_key": idemp_key,
                    "p_conversation_id": conv_id,
                    "p_user_message_id": msg_id,
                    "p_request_fingerprint": fp_a,
                },
            )
            assert res_duplicate_match.status_code in (200, 201)
            assert res_duplicate_match.json()["claimed"] is False

            # 4. Duplicate claim with CONFLICTING fingerprint returns HTTP 409 Conflict
            res_conflict = await client.post(
                f"{postgrest_url}/rpc/claim_chat_request",
                headers=headers_user_a,
                json={
                    "p_idempotency_key": idemp_key,
                    "p_conversation_id": conv_id,
                    "p_user_message_id": msg_id,
                    "p_request_fingerprint": fp_conflict,
                },
            )
            assert res_conflict.status_code in (409, 400), "Security Violation: Conflicting fingerprint was not rejected!"
            assert "conflicting" in res_conflict.text.lower() or "23505" in res_conflict.text

            # 5. Invalid fingerprint format rejected by claim_chat_request
            res_invalid_fp = await client.post(
                f"{postgrest_url}/rpc/claim_chat_request",
                headers=headers_user_a,
                json={
                    "p_idempotency_key": f"bad-fp-{uuid.uuid4()}",
                    "p_conversation_id": conv_id,
                    "p_user_message_id": msg_id,
                    "p_request_fingerprint": "not-a-valid-hex-64-character-fingerprint",
                },
            )
            assert res_invalid_fp.status_code in (400, 403), "Security Violation: Invalid fingerprint format was accepted!"
            assert "64-character hexadecimal" in res_invalid_fp.text

            # 6. User B CANNOT read User A's chat request
            read_b = await client.get(f"{postgrest_url}/chat_requests?idempotency_key=eq.{idemp_key}", headers=headers_user_b)
            assert read_b.status_code == 200
            assert len(read_b.json()) == 0, "Security Violation: User B read User A's chat_request!"

            # 7. Direct UPDATE is forbidden on chat_requests (privilege revoked)
            patch_a = await client.patch(
                f"{postgrest_url}/chat_requests?idempotency_key=eq.{idemp_key}",
                headers=headers_user_a,
                json={"status": "completed"},
            )
            assert patch_a.status_code in (401, 403), f"Expected permission-denied (401/403), got {patch_a.status_code}: {patch_a.text}"
            assert "permission denied" in patch_a.text.lower() or "42501" in patch_a.text
            # Verify record remains unchanged
            verify_direct = await client.get(f"{postgrest_url}/chat_requests?idempotency_key=eq.{idemp_key}", headers=headers_user_a)
            assert verify_direct.json()[0]["status"] == "processing", "Security Violation: Record status was altered!"

            # 8. Direct status and assistant_message_id manipulation by User B rejected with permission denied
            patch_b = await client.patch(
                f"{postgrest_url}/chat_requests?idempotency_key=eq.{idemp_key}",
                headers=headers_user_b,
                json={"status": "completed", "assistant_message_id": str(uuid.uuid4())},
            )
            assert patch_b.status_code in (401, 403), f"Expected permission-denied (401/403), got {patch_b.status_code}: {patch_b.text}"
            assert "permission denied" in patch_b.text.lower() or "42501" in patch_b.text

            # 9. User B CANNOT invoke RPC complete_chat_request on User A's request
            rpc_b = await client.post(
                f"{postgrest_url}/rpc/complete_chat_request",
                headers=headers_user_b,
                json={"p_idempotency_key": idemp_key, "p_assistant_message_id": str(uuid.uuid4())},
            )
            assert rpc_b.status_code in (400, 401, 403, 404), "Security Violation: User B completed User A's chat request!"

            # 10. User B CANNOT invoke RPC fail, interrupt, retry, or reconcile on User A's request
            for rpc_name in ("fail_chat_request", "interrupt_chat_request", "retry_chat_request", "reconcile_chat_request"):
                payload = {"p_idempotency_key": idemp_key}
                if "reconcile" in rpc_name:
                    payload["p_assistant_message_id"] = str(uuid.uuid4())
                res_b_rpc = await client.post(f"{postgrest_url}/rpc/{rpc_name}", headers=headers_user_b, json=payload)
                assert res_b_rpc.status_code in (400, 401, 403, 404), f"Security Violation: User B executed {rpc_name} on User A's request!"

            # 11. Direct DELETE on chat_requests is forbidden
            del_a = await client.delete(f"{postgrest_url}/chat_requests?idempotency_key=eq.{idemp_key}", headers=headers_user_a)
            assert del_a.status_code in (401, 403), f"Expected permission-denied (401/403), got {del_a.status_code}: {del_a.text}"
            assert "permission denied" in del_a.text.lower() or "42501" in del_a.text
            # Verify record still exists
            verify_still_exists = await client.get(f"{postgrest_url}/chat_requests?idempotency_key=eq.{idemp_key}", headers=headers_user_a)
            assert len(verify_still_exists.json()) == 1, "Security Violation: Record was deleted via direct DELETE!"

            # 12. Anon CANNOT invoke RPCs or read chat requests
            anon_rpc = await client.post(f"{postgrest_url}/rpc/claim_chat_request", headers=headers_anon, json={})
            assert anon_rpc.status_code in (401, 403)
            anon_read = await client.get(f"{postgrest_url}/chat_requests?idempotency_key=eq.{idemp_key}", headers=headers_anon)
            assert anon_read.status_code in (401, 200)
            if anon_read.status_code == 200:
                assert len(anon_read.json()) == 0

            # 13. Ordinary completion cannot complete failed or interrupted requests
            # Setup a separate failed request
            idemp_failed = f"failed-test-{uuid.uuid4()}"
            msg_f = await client.post(f"{postgrest_url}/messages", headers=headers_user_a, json={"conversation_id": conv_id, "role": "user", "content": "Fail prompt"})
            msg_f_id = msg_f.json()[0]["id"]
            await client.post(
                f"{postgrest_url}/rpc/claim_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_failed, "p_conversation_id": conv_id, "p_user_message_id": msg_f_id, "p_request_fingerprint": "c" * 64},
            )
            await client.post(f"{postgrest_url}/rpc/fail_chat_request", headers=headers_user_a, json={"p_idempotency_key": idemp_failed})

            asst_f = await client.post(
                f"{postgrest_url}/messages",
                headers=headers_user_a,
                json={"conversation_id": conv_id, "role": "assistant", "content": "Ans", "metadata": {"user_message_id": msg_f_id}},
            )
            asst_f_id = asst_f.json()[0]["id"]

            # Ordinary complete on failed request must be rejected
            res_complete_failed = await client.post(
                f"{postgrest_url}/rpc/complete_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_failed, "p_assistant_message_id": asst_f_id},
            )
            assert res_complete_failed.status_code in (400, 403), "Security Violation: Ordinary completion succeeded on failed request!"
            assert "cannot complete request with status failed" in res_complete_failed.text

            # 14. Reconciliation cannot use assistant message associated with a different user message
            res_bad_recon = await client.post(
                f"{postgrest_url}/rpc/reconcile_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_failed, "p_assistant_message_id": asst_id}, # asst_id belongs to msg_id, not msg_f_id!
            )
            assert res_bad_recon.status_code in (400, 403), "Security Violation: Reconcile accepted mismatched assistant message!"
            assert "not generated for this user message" in res_bad_recon.text

            # Valid reconciliation on failed request succeeds with matching assistant message
            res_good_recon = await client.post(
                f"{postgrest_url}/rpc/reconcile_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_failed, "p_assistant_message_id": asst_f_id},
            )
            assert res_good_recon.status_code in (200, 201)

            # 15. Valid completion through RPC requires valid assistant message in same conversation
            # Try completing with fake assistant message ID: rejected
            fake_asst = await client.post(
                f"{postgrest_url}/rpc/complete_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_key, "p_assistant_message_id": str(uuid.uuid4())},
            )
            assert fake_asst.status_code in (400, 401, 403, 404), "Security Violation: complete accepted unverified assistant message!"

            # Create legitimate assistant message in thread
            res_asst = await client.post(
                f"{postgrest_url}/messages",
                headers=headers_user_a,
                json={"conversation_id": conv_id, "role": "assistant", "content": "Assistant answer", "metadata": {"user_message_id": msg_id}},
            )
            asst_id = res_asst.json()[0]["id"]

            # Complete with legitimate assistant message: SUCCEEDS
            res_complete = await client.post(
                f"{postgrest_url}/rpc/complete_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_key, "p_assistant_message_id": asst_id},
            )
            assert res_complete.status_code in (200, 201)

            # 16. Terminal state: Completed request CANNOT be failed or retried
            res_fail_after_complete = await client.post(
                f"{postgrest_url}/rpc/fail_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_key},
            )
            assert res_fail_after_complete.status_code in (400, 403)

            res_retry_after_complete = await client.post(
                f"{postgrest_url}/rpc/retry_chat_request",
                headers=headers_user_a,
                json={"p_idempotency_key": idemp_key},
            )
            assert res_retry_after_complete.status_code in (400, 403)
        finally:
            await client.delete(f"{postgrest_url}/conversations?id=eq.{conv_id}", headers=headers_user_a)
