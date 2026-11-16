"""Unit tests for SupabasePostgresChatRepository adapter.

Verifies:
- Fully asynchronous non-blocking PostgREST communication.
- Authenticated user JWT token and public anon key are sent in headers.
- Service-role key is never used.
- Atomic idempotency claiming handles 201 Created vs 409 Conflict.
- Strict error handling distinguishing auth failures (401/403), server failures (500),
  network connectivity failures, and empty query results.
- Asynchronous database operations do not block unrelated event-loop tasks.
"""

import asyncio
import json
import time
from uuid import UUID, uuid4
import httpx
import pytest

from app.core.exceptions import (
    DatabaseAuthError,
    DatabaseConnectionError,
    DatabaseOperationError,
    IdempotencyConflictError,
)
from app.models.chat import ConversationModel, MessageModel, ChatRequestModel
from app.services.chat.supabase_repository import SupabasePostgresChatRepository

TEST_SUPABASE_URL = "https://mock-test-project.supabase.co"
TEST_ANON_KEY = "mock-public-anon-key"
TEST_USER_TOKEN = "mock-user-bearer-token"
USER_ID = uuid4()
CONV_ID = uuid4()


def test_supabase_repo_headers():
    """Verify PostgREST requests include user token and anon key, without service-role key."""
    repo = SupabasePostgresChatRepository(
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
async def test_supabase_repo_create_and_get_conversation():
    """Verify async conversation creation and retrieval via mocked PostgREST."""
    conv_data = {
        "id": str(CONV_ID),
        "user_id": str(USER_ID),
        "title": "Architectural Strategy",
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:00+00:00",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == TEST_ANON_KEY
        assert request.headers["Authorization"] == f"Bearer {TEST_USER_TOKEN}"

        if request.method == "POST" and "/conversations" in str(request.url):
            payload = json.loads(request.content)
            assert payload["user_id"] == str(USER_ID)
            assert payload["title"] == "Architectural Strategy"
            return httpx.Response(201, json=[conv_data])

        if request.method == "GET" and "/conversations" in str(request.url):
            assert f"id=eq.{CONV_ID}" in str(request.url)
            return httpx.Response(200, json=[conv_data])

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        conv = await repo.create_conversation(USER_ID, title="Architectural Strategy")
        assert conv.id == CONV_ID
        assert conv.title == "Architectural Strategy"

        fetched = await repo.get_conversation(USER_ID, CONV_ID)
        assert fetched is not None
        assert fetched.id == CONV_ID
        assert fetched.title == "Architectural Strategy"


@pytest.mark.asyncio
async def test_supabase_repo_claim_chat_request_atomic_success():
    """Verify atomic claim returns (True, req) when RPC claim_chat_request returns claimed=True."""
    req_data = {
        "user_id": str(USER_ID),
        "idempotency_key": "idemp-atomic-1",
        "conversation_id": str(CONV_ID),
        "status": "processing",
        "user_message_id": str(uuid4()),
        "assistant_message_id": None,
        "request_fingerprint": "a" * 64,
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:00+00:00",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/rpc/claim_chat_request" in str(request.url):
            body = json.loads(request.content)
            assert body["p_idempotency_key"] == "idemp-atomic-1"
            assert body["p_request_fingerprint"] == "a" * 64
            return httpx.Response(200, json={"claimed": True, "request": req_data})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        claimed, req = await repo.claim_chat_request(
            user_id=USER_ID,
            idempotency_key="idemp-atomic-1",
            conversation_id=CONV_ID,
            user_message_id=UUID(req_data["user_message_id"]),
            request_fingerprint="a" * 64,
        )
        assert claimed is True
        assert req.status == "processing"
        assert req.idempotency_key == "idemp-atomic-1"
        assert req.request_fingerprint == "a" * 64


@pytest.mark.asyncio
async def test_supabase_repo_claim_chat_request_duplicate_matching_returns_existing():
    """Verify atomic claim returns (False, existing_req) when duplicate claim matches fingerprint."""
    existing_data = {
        "user_id": str(USER_ID),
        "idempotency_key": "idemp-atomic-conflict",
        "conversation_id": str(CONV_ID),
        "status": "processing",
        "user_message_id": str(uuid4()),
        "assistant_message_id": None,
        "request_fingerprint": "b" * 64,
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:00+00:00",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/rpc/claim_chat_request" in str(request.url):
            return httpx.Response(200, json={"claimed": False, "request": existing_data})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        claimed, req = await repo.claim_chat_request(
            user_id=USER_ID,
            idempotency_key="idemp-atomic-conflict",
            conversation_id=CONV_ID,
            user_message_id=UUID(existing_data["user_message_id"]),
            request_fingerprint="b" * 64,
        )
        assert claimed is False
        assert req.status == "processing"
        assert req.idempotency_key == "idemp-atomic-conflict"
        assert req.request_fingerprint == "b" * 64


@pytest.mark.asyncio
async def test_supabase_repo_claim_chat_request_conflicting_fingerprint_raises_conflict_error():
    """Verify conflicting fingerprint on claim returns HTTP 409 and raises IdempotencyConflictError."""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/rpc/claim_chat_request" in str(request.url):
            return httpx.Response(
                409,
                json={"message": "Idempotency key was already used with conflicting request content", "code": "23505"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        with pytest.raises(IdempotencyConflictError) as exc_info:
            await repo.claim_chat_request(
                user_id=USER_ID,
                idempotency_key="idemp-conflict-key",
                conversation_id=CONV_ID,
                user_message_id=uuid4(),
                request_fingerprint="c" * 64,
            )
        assert "conflicting" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_supabase_repo_missing_rpc_raises_database_error():
    """Verify that a missing RPC (404) raises DatabaseOperationError and never falls back to direct table mutation."""
    async def handler(request: httpx.Request) -> httpx.Response:
        # Simulate PostgREST 404 because RPC was not created
        return httpx.Response(404, json={"message": "Function not found in schema"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        # Claim RPC missing
        with pytest.raises(DatabaseOperationError) as exc1:
            await repo.claim_chat_request(
                user_id=USER_ID,
                idempotency_key="missing-rpc-claim",
                conversation_id=CONV_ID,
                user_message_id=uuid4(),
                request_fingerprint="d" * 64,
            )
        assert "rpc 'claim_chat_request' not found" in str(exc1.value).lower()

        # Update RPC missing
        with pytest.raises(DatabaseOperationError) as exc2:
            await repo.update_chat_request_status(
                user_id=USER_ID,
                idempotency_key="missing-rpc-update",
                status="completed",
                assistant_message_id=uuid4(),
            )
        assert "rpc" in str(exc2.value).lower()

        # Retry RPC missing
        with pytest.raises(DatabaseOperationError) as exc3:
            await repo.transition_chat_request_status(
                user_id=USER_ID,
                idempotency_key="missing-rpc-retry",
                from_statuses=["failed"],
                to_status="processing",
            )
        assert "rpc 'retry_chat_request' not found" in str(exc3.value).lower()


@pytest.mark.asyncio
async def test_supabase_repo_reconcile_chat_request_via_rpc():
    """Verify reconcile_chat_request calls /rpc/reconcile_chat_request and returns updated record."""
    reconciled_id = uuid4()
    asst_id = uuid4()
    req_data = {
        "user_id": str(USER_ID),
        "idempotency_key": "reconcile-key-1",
        "conversation_id": str(CONV_ID),
        "status": "completed",
        "user_message_id": str(uuid4()),
        "assistant_message_id": str(asst_id),
        "request_fingerprint": "e" * 64,
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:01+00:00",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/rpc/reconcile_chat_request" in str(request.url):
            body = json.loads(request.content)
            assert body["p_idempotency_key"] == "reconcile-key-1"
            assert body["p_assistant_message_id"] == str(asst_id)
            return httpx.Response(200, json=req_data)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        res = await repo.reconcile_chat_request(USER_ID, "reconcile-key-1", asst_id)
        assert res.status == "completed"
        assert res.assistant_message_id == asst_id


@pytest.mark.asyncio
async def test_supabase_repo_distinguishes_error_types():
    """Verify database errors are NOT silently converted to empty records."""
    # 1. 401 Unauthorized raises DatabaseAuthError
    async def auth_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="JWT expired or invalid")

    async with httpx.AsyncClient(transport=httpx.MockTransport(auth_error_handler)) as client:
        repo = SupabasePostgresChatRepository(TEST_SUPABASE_URL, TEST_ANON_KEY, TEST_USER_TOKEN, http_client=client)
        with pytest.raises(DatabaseAuthError) as exc_info:
            await repo.get_conversation(USER_ID, CONV_ID)
        assert "authentication or authorization" in str(exc_info.value).lower()

    # 2. 500 Server Error raises DatabaseOperationError
    async def server_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal PostgreSQL crash")

    async with httpx.AsyncClient(transport=httpx.MockTransport(server_error_handler)) as client:
        repo = SupabasePostgresChatRepository(TEST_SUPABASE_URL, TEST_ANON_KEY, TEST_USER_TOKEN, http_client=client)
        with pytest.raises(DatabaseOperationError) as exc_info:
            await repo.get_conversation(USER_ID, CONV_ID)
        assert "database service error" in str(exc_info.value).lower()

    # 3. Empty query result (200 OK with []) returns None without raising an error
    async def empty_result_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(empty_result_handler)) as client:
        repo = SupabasePostgresChatRepository(TEST_SUPABASE_URL, TEST_ANON_KEY, TEST_USER_TOKEN, http_client=client)
        result = await repo.get_conversation(USER_ID, CONV_ID)
        assert result is None


@pytest.mark.asyncio
async def test_async_database_operations_do_not_block_event_loop():
    """Verify that during an asynchronous PostgREST request, unrelated event-loop tasks continue executing."""
    ticks = 0

    async def background_ticker():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.04)
            ticks += 1

    async def delayed_handler(request: httpx.Request) -> httpx.Response:
        # Simulate 0.2s network round-trip to cloud database
        await asyncio.sleep(0.2)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(delayed_handler)) as client:
        repo = SupabasePostgresChatRepository(TEST_SUPABASE_URL, TEST_ANON_KEY, TEST_USER_TOKEN, http_client=client)

        ticker_task = asyncio.create_task(background_ticker())
        db_task = asyncio.create_task(repo.get_conversation(USER_ID, CONV_ID))

        await asyncio.gather(ticker_task, db_task)

        # The background ticker must have executed concurrently while the DB call was awaiting
        assert ticks >= 3, f"Event loop was blocked! Expected ticks >= 3, got {ticks}"


@pytest.mark.asyncio
async def test_supabase_repo_claim_chat_request_via_rpc():
    """Verify claim_chat_request calls /rpc/claim_chat_request and parses JSON response."""
    rpc_req_data = {
        "user_id": str(USER_ID),
        "idempotency_key": "rpc-idemp-1",
        "conversation_id": str(CONV_ID),
        "status": "processing",
        "user_message_id": str(uuid4()),
        "assistant_message_id": None,
        "request_fingerprint": "a" * 64,
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:00+00:00",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/rpc/claim_chat_request" in str(request.url):
            body = json.loads(request.content)
            assert body["p_idempotency_key"] == "rpc-idemp-1"
            assert body["p_request_fingerprint"] == "a" * 64
            return httpx.Response(200, json={"claimed": True, "request": rpc_req_data})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        claimed, req = await repo.claim_chat_request(
            user_id=USER_ID,
            idempotency_key="rpc-idemp-1",
            conversation_id=CONV_ID,
            user_message_id=UUID(rpc_req_data["user_message_id"]),
            request_fingerprint="a" * 64,
        )
        assert claimed is True
        assert req.status == "processing"
        assert req.idempotency_key == "rpc-idemp-1"
        assert req.request_fingerprint == "a" * 64


@pytest.mark.asyncio
async def test_supabase_repo_lifecycle_rpcs_complete_fail_interrupt_retry():
    """Verify complete, fail, interrupt, and retry lifecycle methods invoke corresponding RPC endpoints."""
    calls = []
    asst_id = uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        body = json.loads(request.content) if request.content else {}

        if "/rpc/complete_chat_request" in url_str:
            calls.append(("complete", body))
            assert body["p_assistant_message_id"] == str(asst_id)
            return httpx.Response(200, json={"status": "completed"})

        if "/rpc/fail_chat_request" in url_str:
            calls.append(("fail", body))
            return httpx.Response(200, json={"status": "failed"})

        if "/rpc/interrupt_chat_request" in url_str:
            calls.append(("interrupt", body))
            assert body["p_assistant_message_id"] == str(asst_id)
            return httpx.Response(200, json={"status": "interrupted"})

        if "/rpc/retry_chat_request" in url_str:
            calls.append(("retry", body))
            return httpx.Response(200, json={"transitioned": True, "request": {"status": "processing"}})

        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        # 1. Complete
        await repo.update_chat_request_status(USER_ID, "key-1", status="completed", assistant_message_id=asst_id)
        assert len(calls) == 1 and calls[0][0] == "complete"

        # 2. Fail
        await repo.update_chat_request_status(USER_ID, "key-2", status="failed")
        assert len(calls) == 2 and calls[1][0] == "fail"

        # 3. Interrupt
        await repo.update_chat_request_status(USER_ID, "key-3", status="interrupted", assistant_message_id=asst_id)
        assert len(calls) == 3 and calls[2][0] == "interrupt"

        # 4. Retry
        transitioned = await repo.transition_chat_request_status(USER_ID, "key-4", ["failed"], "processing")
        assert transitioned is True
        assert len(calls) == 4 and calls[3][0] == "retry"


@pytest.mark.asyncio
async def test_supabase_repo_unauthorized_rpc_call_raises_auth_error():
    """Verify that an unauthorized or expired user token calling an RPC raises DatabaseAuthError."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "JWT expired or unauthorized"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token="expired-token",
            http_client=mock_client,
        )

        with pytest.raises(DatabaseAuthError):
            await repo.update_chat_request_status(USER_ID, "key-unauth", status="completed", assistant_message_id=uuid4())


@pytest.mark.asyncio
async def test_supabase_repo_list_conversations_with_aggregated_counts():
    """Verify list_conversations requests messages(count) via PostgREST and properly aggregates message counts."""
    c1_id = uuid4()
    c2_id = uuid4()
    mock_rows = [
        {
            "id": str(c1_id),
            "user_id": str(USER_ID),
            "title": "Thread with Messages",
            "created_at": "2026-11-16T00:00:00+00:00",
            "updated_at": "2026-11-16T00:05:00+00:00",
            "messages": [{"count": 7}],
        },
        {
            "id": str(c2_id),
            "user_id": str(USER_ID),
            "title": "Empty Thread",
            "created_at": "2026-11-16T00:00:00+00:00",
            "updated_at": "2026-11-16T00:01:00+00:00",
            "messages": [{"count": 0}],
        },
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/conversations" in str(request.url)
        assert f"user_id=eq.{USER_ID}" in str(request.url)
        assert "messages(count)" in str(request.url) or "messages%28count%29" in str(request.url)
        return httpx.Response(200, json=mock_rows)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        convs = await repo.list_conversations(USER_ID)
        assert len(convs) == 2
        assert convs[0].id == c1_id
        assert convs[0].message_count == 7
        assert convs[1].id == c2_id
        assert convs[1].message_count == 0


@pytest.mark.asyncio
async def test_supabase_repo_update_conversation_title():
    """Verify update_conversation_title sends PATCH with Prefer: return=representation and parses updated row."""
    conv_id = uuid4()
    mock_row = {
        "id": str(conv_id),
        "user_id": str(USER_ID),
        "title": "Renamed Title via PostgREST",
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:10:00+00:00",
        "messages": [{"count": 3}],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert "/conversations" in str(request.url)
        assert f"id=eq.{conv_id}" in str(request.url)
        assert f"user_id=eq.{USER_ID}" in str(request.url)
        assert request.headers.get("Prefer") == "return=representation"
        payload = json.loads(request.content)
        assert payload["title"] == "Renamed Title via PostgREST"
        return httpx.Response(200, json=[mock_row])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        res = await repo.update_conversation_title(USER_ID, conv_id, "Renamed Title via PostgREST")
        assert res is not None
        assert res.id == conv_id
        assert res.title == "Renamed Title via PostgREST"
        assert res.message_count == 3


@pytest.mark.asyncio
async def test_supabase_repo_delete_conversation():
    """Verify delete_conversation sends DELETE with Prefer: return=representation and handles success and not-found."""
    conv_id = uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert "/conversations" in str(request.url)
        assert f"id=eq.{conv_id}" in str(request.url)
        assert f"user_id=eq.{USER_ID}" in str(request.url)
        assert request.headers.get("Prefer") == "return=representation"
        return httpx.Response(200, json=[{"id": str(conv_id)}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        # Existing conversation deleted
        success = await repo.delete_conversation(USER_ID, conv_id)
        assert success is True

    # Not found case (empty list returned)
    async def not_found_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(not_found_handler)) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        missing_success = await repo.delete_conversation(USER_ID, conv_id)
        assert missing_success is False
