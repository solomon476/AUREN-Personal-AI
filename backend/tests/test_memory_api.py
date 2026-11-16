"""Integration and Unit tests for Memory Explorer, Epistemic Verification, and Context Provenance APIs.

Verifies:
- Strict JWT authentication and user ownership enforcement.
- Cross-user isolation (returning 404 without existence leakage).
- Server-side search, filtering, and pagination.
- Full epistemic lifecycle state machine transitions (confirm, reject, correct, archive, restore, outdate).
- Lineage-preserving memory corrections (previous_version_id, superseded_by_id, root_memory_id).
- Context provenance tracking for assistant messages.
- Fail-safe error handling and validation constraints.
"""

import time
import uuid
from typing import Optional
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.memory import MemoryModel
from app.services.chat.repository import chat_repository
from app.services.memory.repository import memory_repository

client = TestClient(app)
TEST_JWT_SECRET = "super-secret-test-key-for-supabase-jwt-verification-unit-tests"


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """Configure settings for isolated test execution."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "CHAT_REPOSITORY_TYPE", "sqlite")


def create_test_token(user_id: str, email: str = "memory_tester@example.com") -> str:
    """Generate a signed JWT token simulating Supabase Auth."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Memory Tester"},
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


# ---------------------------------------------------------------------------
# 1. Authentication & Security Boundaries
# ---------------------------------------------------------------------------

def test_unauthenticated_memory_endpoints_rejected():
    """All memory endpoints must strictly require authenticated bearer tokens."""
    random_id = str(uuid4())
    assert client.get("/api/v1/memories").status_code == 401
    assert client.post("/api/v1/memories", json={"content": "test"}).status_code == 401
    assert client.get(f"/api/v1/memories/{random_id}").status_code == 401
    assert client.post(f"/api/v1/memories/{random_id}/confirm").status_code == 401
    assert client.post(f"/api/v1/memories/{random_id}/reject").status_code == 401
    assert client.post(f"/api/v1/memories/{random_id}/correct", json={"content": "new"}).status_code == 401
    assert client.post(f"/api/v1/memories/{random_id}/archive").status_code == 401
    assert client.post(f"/api/v1/memories/{random_id}/restore").status_code == 401
    assert client.post(f"/api/v1/memories/{random_id}/outdated").status_code == 401


# ---------------------------------------------------------------------------
# 2. Memory Creation & Validation
# ---------------------------------------------------------------------------

def test_create_memory_success(user_a):
    """User can create an explicit confirmed memory."""
    payload = {
        "content": "User prefers concise Python examples using asyncio.",
        "memory_type": "preference",
        "category": "technical",
        "importance": 4,
    }
    resp = client.post("/api/v1/memories", json=payload, headers=user_a["headers"])
    assert resp.status_code == 201
    data = resp.json()

    assert data["content"] == payload["content"]
    assert data["memory_type"] == "preference"
    assert data["category"] == "technical"
    assert data["importance"] == 4
    assert data["confirmation_status"] == "confirmed"
    assert data["lifecycle_status"] == "active"
    assert data["origin"] == "user_direct_input"
    assert data["id"] is not None


def test_create_memory_validation_failures(user_a):
    """Empty content, whitespace only, or invalid categories must be rejected with 422."""
    # Empty content
    resp = client.post("/api/v1/memories", json={"content": "   "}, headers=user_a["headers"])
    assert resp.status_code == 422

    # Invalid type
    resp = client.post("/api/v1/memories", json={"content": "Valid", "memory_type": "invalid_type"}, headers=user_a["headers"])
    assert resp.status_code == 422

    # Invalid category
    resp = client.post("/api/v1/memories", json={"content": "Valid", "category": "invalid_cat"}, headers=user_a["headers"])
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. Listing, Search, and Pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_memories_pagination_and_search(user_a):
    """Verifies server-side pagination, substring query search, and filters."""
    uid = UUID(user_a["id"])

    # Seed 5 distinct memories for User A
    m1 = await memory_repository.create_memory(uid, "Alpha work project task", memory_type="project", category="work", importance=5)
    m2 = await memory_repository.create_memory(uid, "Beta personal preference coffee", memory_type="preference", category="personal", importance=3)
    m3 = await memory_repository.create_memory(uid, "Gamma technical fact regarding PostgreSQL", memory_type="fact", category="technical", importance=4)
    m4 = await memory_repository.create_memory(uid, "Delta health and fitness routine", memory_type="goal", category="health_lifestyle", importance=2)
    m5 = await memory_repository.create_memory(uid, "Epsilon financial portfolio target", memory_type="goal", category="financial", importance=4)

    # 1. Default list
    resp = client.get("/api/v1/memories", headers=user_a["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 5
    assert len(data["items"]) >= 5

    # 2. Pagination (page_size=2)
    resp_p1 = client.get("/api/v1/memories?page=1&page_size=2", headers=user_a["headers"])
    data_p1 = resp_p1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["page"] == 1
    assert data_p1["has_more"] is True

    resp_p2 = client.get("/api/v1/memories?page=2&page_size=2", headers=user_a["headers"])
    data_p2 = resp_p2.json()
    assert len(data_p2["items"]) == 2
    assert data_p2["page"] == 2
    # Items across pages must be distinct
    p1_ids = {m["id"] for m in data_p1["items"]}
    p2_ids = {m["id"] for m in data_p2["items"]}
    assert p1_ids.isdisjoint(p2_ids)

    # 3. Content search
    resp_search = client.get("/api/v1/memories?query=PostgreSQL", headers=user_a["headers"])
    data_search = resp_search.json()
    assert data_search["total"] == 1
    assert "PostgreSQL" in data_search["items"][0]["content"]

    # 4. Filter by memory_type
    resp_filter_type = client.get("/api/v1/memories?memory_type=goal", headers=user_a["headers"])
    data_filter_type = resp_filter_type.json()
    assert all(m["memory_type"] == "goal" for m in data_filter_type["items"])
    assert data_filter_type["total"] >= 2

    # 5. Filter by category
    resp_filter_cat = client.get("/api/v1/memories?category=technical", headers=user_a["headers"])
    data_filter_cat = resp_filter_cat.json()
    assert all(m["category"] == "technical" for m in data_filter_cat["items"])


def test_list_memories_invalid_filter_rejected(user_a):
    """Invalid query filter parameters return HTTP 400 Bad Request."""
    resp = client.get("/api/v1/memories?memory_type=invalid_type", headers=user_a["headers"])
    assert resp.status_code == 400
    assert "Invalid memory_type" in resp.json()["detail"]

    resp = client.get("/api/v1/memories?category=invalid_category", headers=user_a["headers"])
    assert resp.status_code == 400
    assert "Invalid category" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Memory Detail & Cross-User Security Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_detail_and_cross_user_isolation(user_a, user_b):
    """User A cannot access or see User B's memories under any circumstance (returns 404)."""
    uid_b = UUID(user_b["id"])
    mem_b = await memory_repository.create_memory(
        uid_b,
        "User B confidential business plans and private notes.",
        memory_type="project",
        category="work",
    )

    # User B can view their own memory detail
    resp_b = client.get(f"/api/v1/memories/{mem_b.id}", headers=user_b["headers"])
    assert resp_b.status_code == 200
    assert resp_b.json()["id"] == str(mem_b.id)

    # User A attempting to view User B's memory receives 404 (no existence leakage)
    resp_a = client.get(f"/api/v1/memories/{mem_b.id}", headers=user_a["headers"])
    assert resp_a.status_code == 404
    assert "Memory not found or access denied." in resp_a.json()["detail"]

    # User A listing memories never includes User B's memories
    list_a = client.get("/api/v1/memories", headers=user_a["headers"]).json()
    assert all(item["id"] != str(mem_b.id) for item in list_a["items"])


# ---------------------------------------------------------------------------
# 5. Epistemic Verification & Lifecycle Transitions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_unconfirmed_inference(user_a):
    """Unconfirmed dialogue inference transitions to confirmed status with timestamp."""
    uid = UUID(user_a["id"])

    # Manually insert an unconfirmed inference
    with memory_repository._get_connection() as conn:
        mid = str(uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.execute(
            """
            INSERT INTO memories (
                id, user_id, content, memory_type, category, importance,
                confirmation_status, lifecycle_status, origin, root_memory_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'preference', 'general', 3, 'unconfirmed', 'active', 'chat_inferred', ?, ?, ?);
            """,
            (mid, str(uid), "Inferred user preference for tea over coffee.", mid, now, now),
        )
        conn.commit()

    # Confirm the inference
    resp = client.post(f"/api/v1/memories/{mid}/confirm", headers=user_a["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["confirmation_status"] == "confirmed"
    assert data["last_confirmed_at"] is not None


@pytest.mark.asyncio
async def test_reject_inference_terminal_state(user_a):
    """Rejecting an inference marks both confirmation_status and lifecycle_status as rejected (terminal)."""
    uid = UUID(user_a["id"])

    with memory_repository._get_connection() as conn:
        mid = str(uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.execute(
            """
            INSERT INTO memories (
                id, user_id, content, memory_type, category, importance,
                confirmation_status, lifecycle_status, origin, root_memory_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'fact', 'general', 3, 'unconfirmed', 'active', 'chat_inferred', ?, ?, ?);
            """,
            (mid, str(uid), "Incorrectly inferred user owns a dog.", mid, now, now),
        )
        conn.commit()

    # Reject
    resp = client.post(f"/api/v1/memories/{mid}/reject", headers=user_a["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["confirmation_status"] == "rejected"
    assert data["lifecycle_status"] == "rejected"

    # Invariant: Rejected memory cannot be confirmed or reactivated
    confirm_resp = client.post(f"/api/v1/memories/{mid}/confirm", headers=user_a["headers"])
    assert confirm_resp.status_code == 400
    assert "Cannot confirm previously rejected memory" in confirm_resp.json()["detail"]


@pytest.mark.asyncio
async def test_correct_memory_preserves_lineage(user_a):
    """Correcting a memory supersedes predecessor and atomically creates successor with audit links."""
    uid = UUID(user_a["id"])
    old_mem = await memory_repository.create_memory(
        uid,
        "Original outdated statement: User lives in Seattle.",
        memory_type="fact",
        category="personal",
        importance=3,
    )

    correction_payload = {
        "content": "Corrected statement: User relocated to New York.",
        "memory_type": "fact",
        "category": "personal",
        "importance": 4,
    }

    resp = client.post(f"/api/v1/memories/{old_mem.id}/correct", json=correction_payload, headers=user_a["headers"])
    assert resp.status_code == 200
    new_mem_data = resp.json()

    # Check new memory properties
    assert new_mem_data["content"] == correction_payload["content"]
    assert new_mem_data["confirmation_status"] == "confirmed"
    assert new_mem_data["lifecycle_status"] == "active"
    assert new_mem_data["origin"] == "user_direct_edit"
    assert new_mem_data["previous_version_id"] == str(old_mem.id)
    assert new_mem_data["root_memory_id"] == str(old_mem.id)

    # Check that old memory is now superseded
    old_check = await memory_repository.get_memory(uid, old_mem.id)
    assert old_check.lifecycle_status == "superseded"
    assert str(old_check.superseded_by_id) == new_mem_data["id"]

    # Invariant: Superseded memory cannot be corrected again directly
    fail_correct = client.post(
        f"/api/v1/memories/{old_mem.id}/correct",
        json={"content": "Should fail because old is superseded."},
        headers=user_a["headers"],
    )
    assert fail_correct.status_code == 400
    assert "Cannot correct memory with lifecycle status: superseded" in fail_correct.json()["detail"]


@pytest.mark.asyncio
async def test_archive_outdate_and_restore_lifecycle(user_a):
    """Verifies transitions: active -> archived -> active, and active -> expired -> active."""
    uid = UUID(user_a["id"])
    mem = await memory_repository.create_memory(uid, "Temporary active project details.", memory_type="project")

    # 1. Archive
    resp_arch = client.post(f"/api/v1/memories/{mem.id}/archive", headers=user_a["headers"])
    assert resp_arch.status_code == 200
    assert resp_arch.json()["lifecycle_status"] == "archived"

    # 2. Restore from archive
    resp_rest = client.post(f"/api/v1/memories/{mem.id}/restore", headers=user_a["headers"])
    assert resp_rest.status_code == 200
    assert resp_rest.json()["lifecycle_status"] == "active"

    # 3. Outdate (expire)
    resp_out = client.post(f"/api/v1/memories/{mem.id}/outdated", headers=user_a["headers"])
    assert resp_out.status_code == 200
    assert resp_out.json()["lifecycle_status"] == "expired"

    # 4. Restore from expired
    resp_rest2 = client.post(f"/api/v1/memories/{mem.id}/restore", headers=user_a["headers"])
    assert resp_rest2.status_code == 200
    assert resp_rest2.json()["lifecycle_status"] == "active"


# ---------------------------------------------------------------------------
# 6. Context Provenance Inspection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_message_context_provenance(user_a):
    """Context Inspector endpoint accurately returns recorded retrieved memories from assistant message metadata."""
    uid = UUID(user_a["id"])

    # Create a conversation and assistant message with recorded retrieved memories
    conv = await chat_repository.create_conversation(uid, title="Provenance Inspection Test")
    user_msg = await chat_repository.persist_user_message(uid, conv.id, "What are my preferences?")

    mock_retrieved = [
        {
            "id": str(uuid4()),
            "content": "User prefers TypeScript over JavaScript.",
            "memory_type": "preference",
            "category": "technical",
            "confirmation_status": "confirmed",
            "importance": 4,
            "score": 0.88,
        }
    ]

    assistant_msg = await chat_repository.persist_assistant_message(
        uid,
        conv.id,
        "You prefer TypeScript for frontend and backend projects.",
        metadata={
            "model": "mock-test-v1",
            "user_message_id": str(user_msg.id),
            "retrieved_memories": mock_retrieved,
        },
    )

    # Request context provenance
    resp = client.get(
        f"/api/v1/chat/conversations/{conv.id}/messages/{assistant_msg.id}/context",
        headers=user_a["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["message_id"] == str(assistant_msg.id)
    assert data["conversation_id"] == str(conv.id)
    assert data["model"] == "mock-test-v1"
    assert data["memory_count"] == 1
    assert len(data["retrieved_memories"]) == 1
    assert data["retrieved_memories"][0]["content"] == "User prefers TypeScript over JavaScript."
    assert data["retrieved_memories"][0]["score"] == 0.88
    assert data["retrieved_memories"][0]["confirmation_status"] == "confirmed"


@pytest.mark.asyncio
async def test_message_context_cross_user_isolation(user_a, user_b):
    """User B cannot inspect context provenance for User A's messages (returns 404)."""
    uid_a = UUID(user_a["id"])
    conv_a = await chat_repository.create_conversation(uid_a, title="Private Dialogue")
    user_msg_a = await chat_repository.persist_user_message(uid_a, conv_a.id, "Hello")
    asst_msg_a = await chat_repository.persist_assistant_message(
        uid_a, conv_a.id, "Hi there", metadata={"model": "test", "retrieved_memories": []}
    )

    # User B attempts to access context of User A's conversation/message
    resp = client.get(
        f"/api/v1/chat/conversations/{conv_a.id}/messages/{asst_msg_a.id}/context",
        headers=user_b["headers"],
    )
    assert resp.status_code == 404
    assert "Conversation not found or access denied." in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 7. State Transition Guardrails & Non-Existent ID Handling
# ---------------------------------------------------------------------------

def test_mutations_on_nonexistent_memory_return_404(user_a):
    """Mutations referencing non-existent IDs return 404 with standard error message."""
    fake_id = str(uuid4())
    for action in ["confirm", "reject", "archive", "restore", "outdated"]:
        resp = client.post(f"/api/v1/memories/{fake_id}/{action}", headers=user_a["headers"])
        assert resp.status_code == 404
        assert "Memory not found or access denied." in resp.json()["detail"]

    correct_resp = client.post(
        f"/api/v1/memories/{fake_id}/correct",
        json={"content": "New content"},
        headers=user_a["headers"],
    )
    assert correct_resp.status_code == 404
    assert "Memory not found or access denied." in correct_resp.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_lifecycle_transitions_rejected(user_a):
    """Verifies that invalid state transitions raise HTTP 400 Bad Request."""
    uid = UUID(user_a["id"])

    # 1. Create an active memory
    mem = await memory_repository.create_memory(uid, "Active fact for transition tests.")

    # Restoring an already-active memory is invalid
    resp_restore = client.post(f"/api/v1/memories/{mem.id}/restore", headers=user_a["headers"])
    assert resp_restore.status_code == 400
    assert "Cannot restore memory with lifecycle status: active" in resp_restore.json()["detail"]

    # 2. Archive memory
    await memory_repository.archive_memory(uid, mem.id)

    # Confirming an archived memory is invalid
    resp_confirm_arch = client.post(f"/api/v1/memories/{mem.id}/confirm", headers=user_a["headers"])
    assert resp_confirm_arch.status_code == 400
    assert "Cannot confirm memory with lifecycle status: archived" in resp_confirm_arch.json()["detail"]

    # Outdating an archived memory is invalid
    resp_outdate_arch = client.post(f"/api/v1/memories/{mem.id}/outdated", headers=user_a["headers"])
    assert resp_outdate_arch.status_code == 400
    assert "Cannot outdate memory with lifecycle status: archived" in resp_outdate_arch.json()["detail"]


# ---------------------------------------------------------------------------
# 8. Journal Isolation Enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_journal_isolation_in_memory_explorer(user_a):
    """Memory Explorer endpoints strictly query the memories repository and never leak raw journal records."""
    uid = UUID(user_a["id"])

    # List memories
    resp = client.get("/api/v1/memories", headers=user_a["headers"])
    assert resp.status_code == 200
    data = resp.json()

    # None of the items can have journal fields or raw journal content
    for item in data["items"]:
        assert "journal_entry_id" not in item
        assert "encrypted_entry" not in item
        assert "hmac_signature" not in item

