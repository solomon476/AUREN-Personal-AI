"""Comprehensive tests for persistent chat, SSE streaming, idempotency, and user isolation."""

import time
import uuid
import pytest
import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.chat.repository import chat_repository
from app.services.llm.factory import get_llm_provider

client = TestClient(app)
TEST_JWT_SECRET = "super-secret-test-key-for-supabase-jwt-verification-unit-tests"


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """Configure settings for isolated test execution using mock LLM provider."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemini-2.5-flash-test")


def create_token(user_id: str, email: str = "test@auren.ai") -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Test User"},
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# 1. Unauthenticated Access Protection
# ---------------------------------------------------------------------------
def test_unauthenticated_chat_rejected():
    """Verify chat completions endpoint rejects calls without valid JWT."""
    response = client.post("/api/v1/chat/completions", json={"message": "Hello AUREN"})
    assert response.status_code == 401


def test_unauthenticated_conversations_rejected():
    """Verify listing conversations requires authentication."""
    response = client.get("/api/v1/chat/conversations")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Dynamic Model Selection & Factory Check
# ---------------------------------------------------------------------------
def test_dynamic_model_id_configured(monkeypatch):
    """Verify provider dynamically uses the configured LLM_MODEL."""
    test_model = "gemini-2.5-pro-experimental"
    monkeypatch.setattr(settings, "LLM_MODEL", test_model)
    provider = get_llm_provider(settings)
    assert provider.get_model_id() == test_model


# ---------------------------------------------------------------------------
# 3. Successful Persistent Chat Streaming
# ---------------------------------------------------------------------------
def test_streaming_chat_completion_persists_messages():
    """Verify SSE streaming produces metadata, tokens, done event and persists messages."""
    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    prompt = "What is the status of project Auren?"
    response = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"message": prompt},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    body = response.text
    assert "event: metadata" in body
    assert "event: token" in body
    assert "event: done" in body

    # Verify conversation was persisted
    convs = chat_repository.list_conversations(uuid.UUID(user_id))
    assert len(convs) >= 1
    active_conv = convs[0]

    # Verify messages in conversation
    messages = chat_repository.get_messages(uuid.UUID(user_id), active_conv.id)
    assert len(messages) == 2  # user message + assistant response
    assert messages[0].role == "user"
    assert messages[0].content == prompt
    assert messages[1].role == "assistant"
    assert len(messages[1].content) > 0


# ---------------------------------------------------------------------------
# 4. Message Idempotency Verification
# ---------------------------------------------------------------------------
def test_idempotency_prevents_duplicate_messages():
    """Verify re-submitting with the same idempotency key does not duplicate the message."""
    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idempotency_key = f"client-req-{uuid.uuid4()}"

    # First request
    res1 = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"message": "Repeat message", "idempotency_key": idempotency_key},
    )
    assert res1.status_code == 200

    # Second request with identical idempotency_key
    res2 = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"message": "Repeat message", "idempotency_key": idempotency_key},
    )
    assert res2.status_code == 200

    # Check repository to ensure user message was deduplicated
    convs = chat_repository.list_conversations(uuid.UUID(user_id))
    messages = chat_repository.get_messages(uuid.UUID(user_id), convs[0].id)
    user_messages = [m for m in messages if m.role == "user" and m.idempotency_key == idempotency_key]
    assert len(user_messages) == 1, "Idempotent user message must not be duplicated!"


# ---------------------------------------------------------------------------
# 5. Cross-User Conversation Isolation
# ---------------------------------------------------------------------------
def test_user_cannot_access_or_post_to_other_users_conversation():
    """Verify User B cannot read or post to User A's conversation thread."""
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())

    token_a = create_token(user_a_id, "user_a@auren.ai")
    token_b = create_token(user_b_id, "user_b@auren.ai")

    # User A creates a conversation and posts a message
    res_a = client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"message": "Secret thread of User A"},
    )
    assert res_a.status_code == 200

    convs_a = chat_repository.list_conversations(uuid.UUID(user_a_id))
    conv_a_id = str(convs_a[0].id)

    # 1. User B attempts to read User A's conversation messages -> 404
    res_b_read = client.get(
        f"/api/v1/chat/conversations/{conv_a_id}/messages",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b_read.status_code == 404

    # 2. User B attempts to inject a message into User A's conversation thread -> 404
    res_b_post = client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"message": "Injected by User B", "conversation_id": conv_a_id},
    )
    assert res_b_post.status_code == 404


# ---------------------------------------------------------------------------
# 6. Request Size Limit Enforcement
# ---------------------------------------------------------------------------
def test_excessive_message_length_rejected():
    """Verify messages exceeding length limits are rejected before processing."""
    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    oversized_prompt = "A" * (settings.CHAT_MAX_MESSAGE_LENGTH + 10)

    response = client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": oversized_prompt},
    )
    assert response.status_code in (413, 422)
