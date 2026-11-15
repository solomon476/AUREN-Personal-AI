"""Comprehensive tests for persistent chat, SSE streaming, idempotency,

database persistence across restarts, error sanitization, stream timeout, and user isolation.
"""

import asyncio
import time
import uuid
from typing import AsyncIterator, List, Optional
import pytest
import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.chat.repository import ChatRepository, chat_repository
from app.services.chat.chat_service import chat_service
from app.services.llm.base import BaseLLMProvider, ChatMessage, LLMResponse

client = TestClient(app)
TEST_JWT_SECRET = "super-secret-test-key-for-supabase-jwt-verification-unit-tests"


class SpyMockProvider(BaseLLMProvider):
    """Mock provider that tracks execution count and supports latency injection."""

    def __init__(self, model_id: str = "mock-spy-v1"):
        self.model_id = model_id
        self.call_count = 0
        self.delay = 0.0

    def get_model_id(self) -> str:
        return self.model_id

    async def generate_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(content="Spy response", model=self.model_id)

    async def stream_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        yield "Hello"
        yield " from"
        yield " AUREN."


spy_provider = SpyMockProvider()


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """Configure settings for isolated test execution."""
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemini-2.5-flash-test")
    # Patch provider getter to spy provider
    monkeypatch.setattr(chat_service, "_get_provider", lambda: spy_provider)


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
# 2. Disk Persistence Across Process Restart / Repository Reinitialization
# ---------------------------------------------------------------------------
def test_conversations_survive_repository_reinitialization(tmp_path):
    """Verify conversations and messages survive backend repository reinitialization using SQLite on disk."""
    test_db = tmp_path / "persistence_test.db"
    repo1 = ChatRepository(db_path=test_db)

    user_id = uuid.uuid4()
    conv = repo1.create_conversation(user_id, title="Survives Restart")
    msg1 = repo1.persist_user_message(user_id, conv.id, "Message before restart")
    repo1.persist_assistant_message(user_id, conv.id, "Response before restart")

    # Simulate process restart by instantiating a completely new ChatRepository on the same DB file
    repo2 = ChatRepository(db_path=test_db)

    conv_recovered = repo2.get_conversation(user_id, conv.id)
    assert conv_recovered is not None
    assert conv_recovered.title == "Survives Restart"

    messages_recovered = repo2.get_messages(user_id, conv.id)
    assert len(messages_recovered) == 2
    assert messages_recovered[0].content == "Message before restart"
    assert messages_recovered[1].content == "Response before restart"


# ---------------------------------------------------------------------------
# 3. Idempotency: Deduplication Without Duplicate AI Invocation
# ---------------------------------------------------------------------------
def test_duplicate_idempotency_key_does_not_invoke_ai_twice():
    """Verify re-submitting with the same idempotency key replays cached response and NEVER invokes the AI twice."""
    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idempotency_key = f"idempotent-run-{uuid.uuid4()}"

    initial_calls = spy_provider.call_count

    # First request
    res1 = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"message": "What is 2+2?", "idempotency_key": idempotency_key},
    )
    assert res1.status_code == 200
    assert "event: done" in res1.text
    assert spy_provider.call_count == initial_calls + 1

    # Second request with identical idempotency key
    res2 = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"message": "What is 2+2?", "idempotency_key": idempotency_key},
    )
    assert res2.status_code == 200
    assert "replayed_from_cache" in res2.text or "replayed" in res2.text

    # Critical Assertion: The AI provider was NOT invoked a second time!
    assert spy_provider.call_count == initial_calls + 1, "Duplicate request must not trigger a second AI provider generation!"


# ---------------------------------------------------------------------------
# 4. Cross-User Conversation Isolation
# ---------------------------------------------------------------------------
def test_user_cannot_access_or_post_to_other_users_conversation():
    """Verify User B cannot read or post to User A's conversation thread."""
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())

    token_a = create_token(user_a_id, "user_a@auren.ai")
    token_b = create_token(user_b_id, "user_b@auren.ai")

    # User A creates a conversation
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
# 5. Error Sanitization (No Sensitive Internal Leaks to Frontend)
# ---------------------------------------------------------------------------
def test_error_sanitization_no_sensitive_leaks(monkeypatch):
    """Verify internal exceptions are masked with safe client-facing messages."""
    class FailingProvider(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "failing-model"

        async def generate_response(self, messages, **kwargs):
            raise RuntimeError("CRITICAL_INTERNAL_DB_PASSWORD_LEAK: connection failure")

        async def stream_response(self, messages, **kwargs):
            raise RuntimeError("CRITICAL_INTERNAL_DB_PASSWORD_LEAK: connection failure")
            yield "never"

    monkeypatch.setattr(chat_service, "_get_provider", lambda: FailingProvider())

    user_id = str(uuid.uuid4())
    token = create_token(user_id)

    response = client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Trigger failure"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    # Sensitive internal detail must NOT be in the client event stream
    assert "CRITICAL_INTERNAL_DB_PASSWORD_LEAK" not in response.text
    assert "An unexpected error occurred" in response.text


# ---------------------------------------------------------------------------
# 6. Stream Timeout Enforcement
# ---------------------------------------------------------------------------
def test_stream_timeout_enforcement(monkeypatch):
    """Verify CHAT_STREAM_TIMEOUT_SECONDS is enforced on streaming responses."""
    monkeypatch.setattr(settings, "CHAT_STREAM_TIMEOUT_SECONDS", 1)

    class SlowProvider(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "slow-model"

        async def generate_response(self, messages, **kwargs):
            await asyncio.sleep(2)
            return LLMResponse(content="done", model="slow")

        async def stream_response(self, messages, **kwargs):
            yield "starting..."
            await asyncio.sleep(2)
            yield "too late"

    monkeypatch.setattr(chat_service, "_get_provider", lambda: SlowProvider())

    user_id = str(uuid.uuid4())
    token = create_token(user_id)

    response = client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Slow stream prompt"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "timed out" in response.text.lower()


# ---------------------------------------------------------------------------
# 7. Interrupted Stream Reconciliation
# ---------------------------------------------------------------------------
def test_interrupted_stream_preserves_partial_tokens(monkeypatch):
    """Verify that when a stream is interrupted mid-generation, partial tokens are preserved."""
    class InterruptedProvider(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "interrupted-model"

        async def generate_response(self, messages, **kwargs):
            return LLMResponse(content="done", model="interrupted")

        async def stream_response(self, messages, **kwargs):
            yield "Partial"
            yield " thoughts"
            # Simulate sudden network drop / process crash
            raise ConnectionResetError("Connection lost mid-stream")

    monkeypatch.setattr(chat_service, "_get_provider", lambda: InterruptedProvider())

    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    idempotency_key = f"interrupted-test-{uuid.uuid4()}"

    response = client.post(
        "/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Prompt before crash", "idempotency_key": idempotency_key},
    )

    assert response.status_code == 200
    assert "event: error" in response.text

    # Verify partial tokens were saved in database
    convs = chat_repository.list_conversations(uuid.UUID(user_id))
    messages = chat_repository.get_messages(uuid.UUID(user_id), convs[0].id)
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) >= 1
    assert "Partial thoughts" in assistant_msgs[0].content
    assert assistant_msgs[0].metadata.get("interrupted") is True

    # Verify chat request status is marked interrupted
    req = chat_repository.get_chat_request(uuid.UUID(user_id), idempotency_key)
    assert req is not None
    assert req.status in ("interrupted", "failed")
