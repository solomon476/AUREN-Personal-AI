"""Tests for database-level request fingerprint immutability, ownership protection,

lifecycle transition integrity, and RLS privilege restrictions on chat_requests.
"""

import sqlite3
import uuid
import httpx
import jwt
import pytest

from app.core.config import settings
from app.main import app
from app.models.chat import compute_request_fingerprint
from app.services.chat.chat_service import chat_service
from app.services.chat.repository import chat_repository
from app.services.llm.base import BaseLLMProvider, LLMResponse

TEST_JWT_SECRET = "super-secret-test-key-for-supabase-jwt-verification-unit-tests"


class SpyProvider(BaseLLMProvider):
    def get_model_id(self) -> str:
        return "mock-spy-v1"

    async def generate_response(self, messages, **kwargs):
        return LLMResponse(content="Response", model="mock-spy-v1")

    async def stream_response(self, messages, **kwargs):
        yield "Response token"


spy_provider = SpyProvider()


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """Configure settings for isolated test execution."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(chat_service, "_get_provider", lambda: spy_provider)


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "email": f"user-{user_id[:8]}@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": 9999999999,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.mark.asyncio
async def test_update_existing_fingerprint_rejected():
    """Verify that database-level trigger prevents updating an existing request_fingerprint."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Immutability Test Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Test Prompt")
    idemp_key = f"immut-fp-{uuid.uuid4()}"
    orig_fp = compute_request_fingerprint(user_id, "Test Prompt", conv.id)

    # Claim request with initial fingerprint
    claimed, req = await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
        request_fingerprint=orig_fp,
    )
    assert claimed is True
    assert req.request_fingerprint == orig_fp

    # Attempt direct SQL update modifying request_fingerprint
    with pytest.raises(sqlite3.IntegrityError, match="request_fingerprint is immutable"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "UPDATE chat_requests SET request_fingerprint = ? WHERE user_id = ? AND idempotency_key = ?",
                ("tampered_fingerprint_value", str(user_id), idemp_key),
            )

    # Verify original record remains completely intact
    persisted = await chat_repository.get_chat_request(user_id, idemp_key)
    assert persisted is not None
    assert persisted.request_fingerprint == orig_fp


@pytest.mark.asyncio
async def test_replace_fingerprint_with_different_value_and_null_backfill_policy():
    """Verify legacy NULL fingerprints can be set once (migration policy), but cannot be replaced thereafter."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Backfill Policy Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Backfill Prompt")
    idemp_key = f"backfill-fp-{uuid.uuid4()}"

    # Insert a legacy record with NULL fingerprint
    with chat_repository._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint, created_at, updated_at)
            VALUES (?, ?, ?, 'processing', ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (str(user_id), idemp_key, str(conv.id), str(msg.id)),
        )

    legacy_req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert legacy_req.request_fingerprint is None

    # Step 1: Setting fingerprint on a NULL record SUCCEEDS (migration / backfill path)
    initial_fp = compute_request_fingerprint(user_id, "Backfill Prompt", conv.id)
    with chat_repository._get_connection() as conn:
        conn.execute(
            "UPDATE chat_requests SET request_fingerprint = ? WHERE user_id = ? AND idempotency_key = ?",
            (initial_fp, str(user_id), idemp_key),
        )

    updated_req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert updated_req.request_fingerprint == initial_fp

    # Step 2: Attempting to replace the now-assigned fingerprint is REJECTED
    with pytest.raises(sqlite3.IntegrityError, match="request_fingerprint is immutable"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "UPDATE chat_requests SET request_fingerprint = ? WHERE user_id = ? AND idempotency_key = ?",
                ("second_replacement_fp", str(user_id), idemp_key),
            )

    # Verify original assigned fingerprint remains intact
    verified_req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert verified_req.request_fingerprint == initial_fp


@pytest.mark.asyncio
async def test_change_request_owner_rejected():
    """Verify that database trigger strictly prevents changing user_id (request owner)."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_a, title="Owner Protection Conv")
    msg = await chat_repository.persist_user_message(user_a, conv.id, "Owner Test")
    idemp_key = f"owner-protect-{uuid.uuid4()}"

    await chat_repository.claim_chat_request(
        user_id=user_a,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
    )

    # Attempt to change owner from User A to User B
    with pytest.raises(sqlite3.IntegrityError, match="user_id is immutable"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "UPDATE chat_requests SET user_id = ? WHERE idempotency_key = ?",
                (str(user_b), idemp_key),
            )

    # Verify User A still owns the request
    req_a = await chat_repository.get_chat_request(user_a, idemp_key)
    assert req_a is not None
    assert req_a.user_id == user_a

    # User B does not own the request
    req_b = await chat_repository.get_chat_request(user_b, idemp_key)
    assert req_b is None


@pytest.mark.asyncio
async def test_unauthorized_lifecycle_status_transition_rejected():
    """Verify that once a request is completed, database triggers forbid transitioning out of completed."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Status Transition Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Status Test")
    idemp_key = f"status-protect-{uuid.uuid4()}"

    await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
    )

    # Transition to completed
    await chat_repository.update_chat_request_status(user_id, idemp_key, status="completed")
    req_completed = await chat_repository.get_chat_request(user_id, idemp_key)
    assert req_completed.status == "completed"

    # Attempt unauthorized transition from completed back to failed
    with pytest.raises(sqlite3.IntegrityError, match="Completed chat requests cannot be transitioned"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "UPDATE chat_requests SET status = 'failed' WHERE user_id = ? AND idempotency_key = ?",
                (str(user_id), idemp_key),
            )

    # Attempt unauthorized transition from completed back to processing
    with pytest.raises(sqlite3.IntegrityError, match="Completed chat requests cannot be transitioned"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "UPDATE chat_requests SET status = 'processing' WHERE user_id = ? AND idempotency_key = ?",
                (str(user_id), idemp_key),
            )

    # Verify status is strictly preserved as 'completed'
    verified_req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert verified_req.status == "completed"


@pytest.mark.asyncio
async def test_direct_delete_on_chat_requests_rejected():
    """Verify that direct DELETE on chat_requests is forbidden, while cascade deletion from conversation succeeds."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Direct Delete Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Delete Test")
    idemp_key = f"delete-protect-{uuid.uuid4()}"

    await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
    )

    # Attempt direct DELETE on chat_requests while conversation exists
    with pytest.raises(sqlite3.IntegrityError, match="Direct DELETE on chat_requests is forbidden"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "DELETE FROM chat_requests WHERE user_id = ? AND idempotency_key = ?",
                (str(user_id), idemp_key),
            )

    # Verify record still exists
    persisted = await chat_repository.get_chat_request(user_id, idemp_key)
    assert persisted is not None

    # Delete conversation: foreign key CASCADE deletes the chat_request cleanly
    with chat_repository._get_connection() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (str(conv.id), str(user_id)))

    # Verify chat_request was deleted via cascade
    cascaded_req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert cascaded_req is None


@pytest.mark.asyncio
async def test_reusing_idempotency_key_with_different_content_rejected_via_api():
    """Verify that reusing an existing idempotency key with conflicting content is rejected via HTTP 409

    and leaves the original user message and request lifecycle record unaltered.
    """
    user_id = str(uuid.uuid4())
    user_uuid = uuid.UUID(user_id)
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idemp_key = f"api-conflict-{uuid.uuid4()}"

    # 1. Initial valid request
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        res1 = await async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Legitimate Initial Prompt", "idempotency_key": idemp_key},
        )
    assert res1.status_code == 200
    assert "event: done" in res1.text

    initial_req = await chat_repository.get_chat_request(user_uuid, idemp_key)
    assert initial_req is not None
    assert initial_req.status == "completed"

    orig_user_msg = await chat_repository.get_message_by_id(user_uuid, initial_req.user_message_id)
    assert orig_user_msg.content == "Legitimate Initial Prompt"

    # 2. Conflicting reuse with different content
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        res2 = await async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Tampered Conflicting Prompt", "idempotency_key": idemp_key},
        )
    assert res2.status_code == 409

    # 3. Assert original record remains completely untouched
    final_req = await chat_repository.get_chat_request(user_uuid, idemp_key)
    assert final_req.status == "completed"
    assert final_req.user_message_id == initial_req.user_message_id
    assert final_req.assistant_message_id == initial_req.assistant_message_id
    assert final_req.request_fingerprint == initial_req.request_fingerprint

    # 4. Assert original user message in DB is NOT modified
    persisted_user_msg = await chat_repository.get_message_by_id(user_uuid, initial_req.user_message_id)
    assert persisted_user_msg.content == "Legitimate Initial Prompt"
