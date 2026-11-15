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
    fp = "0" * 64

    await chat_repository.claim_chat_request(
        user_id=user_a,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
        request_fingerprint=fp,
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
    fp = "1" * 64

    await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
        request_fingerprint=fp,
    )

    # Transition to completed with assistant message
    asst_msg = await chat_repository.persist_assistant_message(user_id, conv.id, "Answer")
    await chat_repository.update_chat_request_status(user_id, idemp_key, status="completed", assistant_message_id=asst_msg.id)
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
    fp = "2" * 64

    await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
        request_fingerprint=fp,
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


@pytest.mark.asyncio
async def test_direct_authenticated_update_attempts_rejected_by_database():
    """Verify that direct SQL updates attempting to manipulate status or tamper with keys fail at the database level."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Direct Update Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Direct update test prompt")
    idemp_key = f"direct-upd-{uuid.uuid4()}"
    fp = "3" * 64

    await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
        request_fingerprint=fp,
    )
    asst_msg = await chat_repository.persist_assistant_message(user_id, conv.id, "Answer")
    await chat_repository.update_chat_request_status(user_id, idemp_key, status="completed", assistant_message_id=asst_msg.id)

    # Attempt to tamper with idempotency_key
    with pytest.raises(sqlite3.IntegrityError, match="idempotency_key is immutable"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "UPDATE chat_requests SET idempotency_key = 'hacked-key' WHERE user_id = ?",
                (str(user_id),),
            )

    # Attempt to tamper with user_id
    with pytest.raises(sqlite3.IntegrityError, match="user_id is immutable"):
        with chat_repository._get_connection() as conn:
            conn.execute(
                "UPDATE chat_requests SET user_id = ? WHERE idempotency_key = ?",
                (str(uuid.uuid4()), idemp_key),
            )


@pytest.mark.asyncio
async def test_invalid_lifecycle_transitions_rejected():
    """Verify the strict lifecycle transition matrix:
    Valid transitions:
      - processing -> completed
      - processing -> failed
      - processing -> interrupted
      - failed -> processing (via retry)
      - interrupted -> processing (via retry)
    Invalid transitions (strictly rejected):
      - failed -> interrupted
      - interrupted -> failed
      - failed -> completed (ordinary update)
      - interrupted -> completed (ordinary update)
      - completed -> any status
    """
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Transition Matrix Conv")

    # 1. Test terminal completed status
    msg1 = await chat_repository.persist_user_message(user_id, conv.id, "Prompt 1")
    idemp1 = f"trans-matrix-1-{uuid.uuid4()}"
    fp1 = compute_request_fingerprint(user_id, "Prompt 1", conv.id)
    await chat_repository.claim_chat_request(user_id, idemp1, conv.id, msg1.id, fp1)
    asst1 = await chat_repository.persist_assistant_message(user_id, conv.id, "Answer 1")
    await chat_repository.update_chat_request_status(user_id, idemp1, "completed", asst1.id)

    with pytest.raises(Exception):
        await chat_repository.update_chat_request_status(user_id, idemp1, "processing")
    with pytest.raises(Exception):
        await chat_repository.update_chat_request_status(user_id, idemp1, "failed")
    with pytest.raises(Exception):
        await chat_repository.update_chat_request_status(user_id, idemp1, "interrupted")

    # 2. Test failed transitions: cannot go to interrupted or completed directly
    msg2 = await chat_repository.persist_user_message(user_id, conv.id, "Prompt 2")
    idemp2 = f"trans-matrix-2-{uuid.uuid4()}"
    fp2 = compute_request_fingerprint(user_id, "Prompt 2", conv.id)
    await chat_repository.claim_chat_request(user_id, idemp2, conv.id, msg2.id, fp2)
    await chat_repository.update_chat_request_status(user_id, idemp2, "failed")

    with pytest.raises(Exception):
        await chat_repository.update_chat_request_status(user_id, idemp2, "interrupted")
    with pytest.raises(Exception):
        await chat_repository.update_chat_request_status(user_id, idemp2, "completed", asst1.id)

    # But failed -> processing via retry IS permitted
    retry_ok = await chat_repository.transition_chat_request_status(user_id, idemp2, ["failed"], "processing")
    assert retry_ok is True
    req2 = await chat_repository.get_chat_request(user_id, idemp2)
    assert req2.status == "processing"

    # 3. Test interrupted transitions: cannot go to failed or completed directly
    msg3 = await chat_repository.persist_user_message(user_id, conv.id, "Prompt 3")
    idemp3 = f"trans-matrix-3-{uuid.uuid4()}"
    fp3 = compute_request_fingerprint(user_id, "Prompt 3", conv.id)
    await chat_repository.claim_chat_request(user_id, idemp3, conv.id, msg3.id, fp3)
    await chat_repository.update_chat_request_status(user_id, idemp3, "interrupted")

    with pytest.raises(Exception):
        await chat_repository.update_chat_request_status(user_id, idemp3, "failed")
    with pytest.raises(Exception):
        await chat_repository.update_chat_request_status(user_id, idemp3, "completed", asst1.id)

    # But interrupted -> processing via retry IS permitted
    retry_ok3 = await chat_repository.transition_chat_request_status(user_id, idemp3, ["interrupted"], "processing")
    assert retry_ok3 is True
    req3 = await chat_repository.get_chat_request(user_id, idemp3)
    assert req3.status == "processing"


@pytest.mark.asyncio
async def test_reconciliation_operation_lifecycle():
    """Verify dedicated reconcile_chat_request completes an incomplete request when assistant message matches."""
    from app.core.exceptions import DatabaseOperationError
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Reconciliation Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Reconcile prompt")
    idemp = f"reconcile-{uuid.uuid4()}"
    fp = compute_request_fingerprint(user_id, "Reconcile prompt", conv.id)

    # 1. Claim request and set to failed
    await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, fp)
    await chat_repository.update_chat_request_status(user_id, idemp, "failed")

    # Persist assistant message associated with user_message_id
    asst_msg = await chat_repository.persist_assistant_message(
        user_id, conv.id, "Reconciled assistant content", metadata={"user_message_id": str(msg.id)}
    )

    # 2. Reconcile succeeds
    reconciled = await chat_repository.reconcile_chat_request(user_id, idemp, asst_msg.id)
    assert reconciled.status == "completed"
    assert reconciled.assistant_message_id == asst_msg.id

    # 3. Reconciliation with mismatched user_message_id is rejected
    idemp_bad = f"reconcile-bad-{uuid.uuid4()}"
    msg_other = await chat_repository.persist_user_message(user_id, conv.id, "Other prompt")
    await chat_repository.claim_chat_request(user_id, idemp_bad, conv.id, msg_other.id, "1" * 64)
    with pytest.raises(DatabaseOperationError, match="Assistant message"):
        await chat_repository.reconcile_chat_request(user_id, idemp_bad, asst_msg.id)


@pytest.mark.asyncio
async def test_fingerprint_hex_and_length_validation():
    """Verify fingerprint must be strictly non-null, exactly 64 characters, and hexadecimal."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Hex Validation Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Prompt")
    idemp = f"fp-val-{uuid.uuid4()}"

    # Null / empty rejected
    with pytest.raises(ValueError, match="64-character hexadecimal"):
        await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, None)

    # Length != 64 rejected
    with pytest.raises(ValueError, match="64-character hexadecimal"):
        await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, "a" * 63)

    with pytest.raises(ValueError, match="64-character hexadecimal"):
        await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, "a" * 65)

    # Non-hex characters rejected
    with pytest.raises(ValueError, match="64-character hexadecimal"):
        await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, "g" * 64)

    # Valid 64-hex succeeds
    claimed, req = await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, "a" * 64)
    assert claimed is True
    assert req.request_fingerprint == "a" * 64


@pytest.mark.asyncio
async def test_claim_conflicting_fingerprint_rejected_via_repository():
    """Verify claim_chat_request rejects reusing the same key with conflicting fingerprint."""
    from app.core.exceptions import IdempotencyConflictError
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Claim Conflict Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Prompt")
    idemp = f"claim-conflict-{uuid.uuid4()}"
    fp1 = "a" * 64
    fp2 = "b" * 64

    # First claim succeeds
    claimed1, req1 = await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, fp1)
    assert claimed1 is True

    # Same key with same fingerprint returns existing (claimed=False)
    claimed2, req2 = await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, fp1)
    assert claimed2 is False
    assert req2.idempotency_key == idemp

    # Same key with DIFFERENT fingerprint raises IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        await chat_repository.claim_chat_request(user_id, idemp, conv.id, msg.id, fp2)


@pytest.mark.asyncio
async def test_duplicate_and_concurrent_retries_atomic():
    """Verify that concurrent retries on a failed request atomically allow exactly one transition."""
    import asyncio
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Concurrent Retry Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Concurrent prompt")
    idemp_key = f"atomic-concurrent-{uuid.uuid4()}"
    fp = "4" * 64

    await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
        request_fingerprint=fp,
    )
    await chat_repository.update_chat_request_status(user_id, idemp_key, status="failed")

    # Launch two simultaneous retry transitions
    task1 = chat_repository.transition_chat_request_status(user_id, idemp_key, ["failed"], "processing")
    task2 = chat_repository.transition_chat_request_status(user_id, idemp_key, ["failed"], "processing")

    res1, res2 = await asyncio.gather(task1, task2)

    # Exactly one must succeed, and one must fail
    assert (res1 is True and res2 is False) or (res1 is False and res2 is True)

    # Database state is strictly 'processing'
    req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert req.status == "processing"


@pytest.mark.asyncio
async def test_valid_backend_lifecycle_operations_succeed():
    """Verify that valid backend lifecycle sequence (claim -> complete with assistant_message) succeeds completely."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Legitimate Lifecycle Conv")
    msg = await chat_repository.persist_user_message(user_id, conv.id, "Legitimate Prompt")
    idemp_key = f"legit-lifecycle-{uuid.uuid4()}"
    fp = compute_request_fingerprint(user_id, "Legitimate Prompt", conv.id)

    # 1. Claim
    claimed, req = await chat_repository.claim_chat_request(
        user_id=user_id,
        idempotency_key=idemp_key,
        conversation_id=conv.id,
        user_message_id=msg.id,
        request_fingerprint=fp,
    )
    assert claimed is True
    assert req.status == "processing"

    # 2. Persist assistant message
    asst_msg = await chat_repository.persist_assistant_message(
        user_id=user_id,
        conversation_id=conv.id,
        content="Legitimate assistant answer",
    )

    # 3. Complete
    await chat_repository.update_chat_request_status(
        user_id=user_id,
        idempotency_key=idemp_key,
        status="completed",
        assistant_message_id=asst_msg.id,
    )

    final_req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert final_req.status == "completed"
    assert final_req.assistant_message_id == asst_msg.id
    assert final_req.request_fingerprint == fp


@pytest.mark.asyncio
async def test_correctly_reconstructed_legacy_fingerprint():
    """Verify legacy NULL fingerprints are reconstructed using exact application normalization."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Legacy Reconstruct Conv")
    raw_content = "  Line 1   \r\n\r\n  Line 2  \t \nLine 3   \n\n"
    msg = await chat_repository.persist_user_message(user_id, conv.id, raw_content)
    idemp_key = f"legacy-recon-{uuid.uuid4()}"

    # Insert a legacy request row with NULL fingerprint
    with chat_repository._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint, created_at, updated_at)
            VALUES (?, ?, ?, 'processing', ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (str(user_id), idemp_key, str(conv.id), str(msg.id)),
        )

    # Reconstruct fingerprint from source message
    reconstructed_fp = compute_request_fingerprint(user_id, msg.content, conv.id)
    with chat_repository._get_connection() as conn:
        conn.execute(
            "UPDATE chat_requests SET request_fingerprint = ? WHERE user_id = ? AND idempotency_key = ?",
            (reconstructed_fp, str(user_id), idemp_key),
        )

    persisted = await chat_repository.get_chat_request(user_id, idemp_key)
    assert persisted is not None
    assert persisted.request_fingerprint == reconstructed_fp
    assert len(persisted.request_fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in persisted.request_fingerprint)


@pytest.mark.asyncio
async def test_legacy_request_replay_with_matching_content():
    """Verify legacy request with reconstructed fingerprint cleanly replays completed response on identical retry."""
    user_id = str(uuid.uuid4())
    user_uuid = uuid.UUID(user_id)
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idemp_key = f"legacy-replay-{uuid.uuid4()}"
    prompt_text = "What is the architectural foundation of AUREN?"

    conv = await chat_repository.create_conversation(user_uuid, title="Legacy Replay Conv")
    msg = await chat_repository.persist_user_message(user_uuid, conv.id, prompt_text, idempotency_key=idemp_key)
    asst_msg = await chat_repository.persist_assistant_message(
        user_uuid, conv.id, "AUREN is built on PostgreSQL with RLS and strict least-privilege.",
        metadata={"user_message_id": str(msg.id)}
    )

    # Reconstruct fingerprint and mark completed
    reconstructed_fp = compute_request_fingerprint(user_uuid, prompt_text, conv.id)
    with chat_repository._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, assistant_message_id, request_fingerprint, created_at, updated_at)
            VALUES (?, ?, ?, 'completed', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (str(user_uuid), idemp_key, str(conv.id), str(msg.id), str(asst_msg.id), reconstructed_fp),
        )

    # Replay request via API with matching content
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        res = await async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": prompt_text, "conversation_id": str(conv.id), "idempotency_key": idemp_key},
        )

    assert res.status_code == 200
    assert "event: metadata" in res.text
    assert '"replayed": true' in res.text
    assert "AUREN is built on PostgreSQL" in res.text
    assert "replayed_from_cache" in res.text


@pytest.mark.asyncio
async def test_legacy_request_reuse_with_conflicting_content():
    """Verify legacy request with reconstructed fingerprint rejects reuse with conflicting content."""
    user_id = str(uuid.uuid4())
    user_uuid = uuid.UUID(user_id)
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idemp_key = f"legacy-conflict-{uuid.uuid4()}"
    original_prompt = "Original legacy prompt"

    conv = await chat_repository.create_conversation(user_uuid, title="Legacy Conflict Conv")
    msg = await chat_repository.persist_user_message(user_uuid, conv.id, original_prompt, idempotency_key=idemp_key)
    asst_msg = await chat_repository.persist_assistant_message(
        user_uuid, conv.id, "Original answer", metadata={"user_message_id": str(msg.id)}
    )

    reconstructed_fp = compute_request_fingerprint(user_uuid, original_prompt, conv.id)
    with chat_repository._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, assistant_message_id, request_fingerprint, created_at, updated_at)
            VALUES (?, ?, ?, 'completed', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (str(user_uuid), idemp_key, str(conv.id), str(msg.id), str(asst_msg.id), reconstructed_fp),
        )

    # Attempt reuse with conflicting content
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        res = await async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Completely different conflicting prompt", "conversation_id": str(conv.id), "idempotency_key": idemp_key},
        )

    assert res.status_code == 409
    assert "idempotency_conflict" in res.text or "conflicting" in res.text.lower()


@pytest.mark.asyncio
async def test_missing_or_deleted_source_message_policy():
    """Verify compatibility policy for unreconstructable records: orphaned records without source messages are purged."""
    user_id = uuid.uuid4()
    conv = await chat_repository.create_conversation(user_id, title="Orphan Purge Conv")
    fake_msg_id = uuid.uuid4()
    idemp_key = f"orphan-{uuid.uuid4()}"

    # Insert an orphaned legacy request referencing a non-existent message with NULL fingerprint
    with chat_repository._get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            INSERT INTO chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint, created_at, updated_at)
            VALUES (?, ?, ?, 'failed', ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (str(user_id), idemp_key, str(conv.id), str(fake_msg_id)),
        )
        conn.execute("PRAGMA foreign_keys = ON")

    # Apply migration compatibility purge:
    with chat_repository._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM chat_requests
            WHERE request_fingerprint IS NULL
              AND user_message_id NOT IN (SELECT id FROM messages)
            """
        )
        assert cursor.rowcount >= 1

    # Assert orphan record was purged
    purged_req = await chat_repository.get_chat_request(user_id, idemp_key)
    assert purged_req is None

    # Now a client using that idempotency key with a new user message can claim it cleanly
    new_msg = await chat_repository.persist_user_message(user_id, conv.id, "Fresh prompt")
    new_fp = compute_request_fingerprint(user_id, "Fresh prompt", conv.id)
    claimed, fresh_req = await chat_repository.claim_chat_request(user_id, idemp_key, conv.id, new_msg.id, new_fp)
    assert claimed is True
    assert fresh_req.status == "processing"


@pytest.mark.asyncio
async def test_migration_behaviour_when_no_legacy_records_exist():
    """Verify migration backfill behaves safely when 0 legacy NULL records exist."""
    # Count rows with NULL fingerprint (should be 0)
    with chat_repository._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM chat_requests WHERE request_fingerprint IS NULL")
        null_count = cursor.fetchone()[0]

    assert null_count == 0

    # Run the backfill update query: affects 0 rows and raises 0 errors
    with chat_repository._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE chat_requests
            SET request_fingerprint = '0000000000000000000000000000000000000000000000000000000000000000'
            WHERE request_fingerprint IS NULL
            """
        )
        assert cursor.rowcount == 0
