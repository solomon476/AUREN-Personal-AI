"""Comprehensive tests for persistent chat, SSE streaming, idempotency,

database persistence across restarts, error sanitization, stream timeout, and user isolation.
"""

import asyncio
import time
import uuid
from typing import AsyncIterator, List, Optional
import httpx
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
@pytest.mark.asyncio
async def test_conversations_survive_repository_reinitialization(tmp_path):
    """Verify conversations and messages survive backend repository reinitialization using SQLite on disk."""
    test_db = tmp_path / "persistence_test.db"
    repo1 = ChatRepository(db_path=test_db)

    user_id = uuid.uuid4()
    conv = await repo1.create_conversation(user_id, title="Survives Restart")
    msg1 = await repo1.persist_user_message(user_id, conv.id, "Message before restart")
    await repo1.persist_assistant_message(user_id, conv.id, "Response before restart")

    # Simulate process restart by instantiating a completely new ChatRepository on the same DB file
    repo2 = ChatRepository(db_path=test_db)

    conv_recovered = await repo2.get_conversation(user_id, conv.id)
    assert conv_recovered is not None
    assert conv_recovered.title == "Survives Restart"

    messages_recovered = await repo2.get_messages(user_id, conv.id)
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
@pytest.mark.asyncio
async def test_user_cannot_access_or_post_to_other_users_conversation():
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

    convs_a = await chat_repository.list_conversations(uuid.UUID(user_a_id))
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
@pytest.mark.asyncio
async def test_interrupted_stream_preserves_partial_tokens(monkeypatch):
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
    convs = await chat_repository.list_conversations(uuid.UUID(user_id))
    messages = await chat_repository.get_messages(uuid.UUID(user_id), convs[0].id)
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) >= 1
    assert "Partial thoughts" in assistant_msgs[0].content

    # Verify chat request status is marked failed (since provider crashed)
    req = await chat_repository.get_chat_request(uuid.UUID(user_id), idempotency_key)
    assert req is not None
    assert req.status == "failed"


# ---------------------------------------------------------------------------
# 8. Concurrent Simultaneous Requests & Atomic Idempotency Claiming
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_simultaneous_requests_atomic_idempotency():
    """Verify simultaneous requests with the same idempotency key claim atomically so only 1 executes the LLM."""
    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idempotency_key = f"concurrent-idemp-{uuid.uuid4()}"

    initial_calls = spy_provider.call_count

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        req1 = async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Concurrent question", "idempotency_key": idempotency_key},
        )
        req2 = async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Concurrent question", "idempotency_key": idempotency_key},
        )
        res1, res2 = await asyncio.gather(req1, req2)

    assert res1.status_code == 200
    assert res2.status_code == 200

    # Exactly one request called the provider and streamed tokens
    assert spy_provider.call_count == initial_calls + 1, (
        "Simultaneous requests with identical idempotency key must invoke provider exactly once!"
    )

    texts = [res1.text, res2.text]
    assert any("event: done" in t for t in texts)
    assert any("idempotency_in_flight" in t or "replayed" in t for t in texts)


# ---------------------------------------------------------------------------
# 9. Model Delay Over 15s Emits Heartbeat Without Cancelling Stream
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_model_delay_over_15s_emits_heartbeat_without_cancelling_stream(monkeypatch):
    """Verify when model takes >15s to produce first chunk, heartbeat fires without aborting or cancelling the stream."""
    monkeypatch.setattr(settings, "CHAT_STREAM_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(settings, "CHAT_STREAM_HEARTBEAT_SECONDS", 15.0)

    class Over15sDelayedProvider(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "delayed-over-15s-model"

        async def generate_response(self, messages, **kwargs):
            return LLMResponse(content="done", model="delayed-over-15s-model")

        async def stream_response(self, messages, **kwargs):
            # Model takes 16 seconds to produce its first chunk
            await asyncio.sleep(16.0)
            yield "Chunk received after 16 seconds."
            yield " Stream survived heartbeat!"

    delayed_provider = Over15sDelayedProvider()
    monkeypatch.setattr(chat_service, "_get_provider", lambda: delayed_provider)

    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=35.0) as async_client:
        response = await async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Test prompt for 16s delay"},
        )

    assert response.status_code == 200
    # Crucial assertion: Heartbeat event was emitted at ~15s
    assert "event: heartbeat" in response.text
    # Crucial assertion: The stream was NOT cancelled; chunks after 16s were emitted and completed!
    assert "Chunk received after 16 seconds." in response.text
    assert "Stream survived heartbeat!" in response.text
    assert "event: done" in response.text


# ---------------------------------------------------------------------------
# 10. Client Disconnect Leaves Request Interrupted (Never Completed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_client_disconnect_marks_request_interrupted_never_completed(monkeypatch):
    """Verify that when client disconnects mid-stream, status is set to 'interrupted' and NEVER 'completed'."""
    user_id = uuid.uuid4()
    idempotency_key = f"disconnect-test-{uuid.uuid4()}"

    class MockDisconnectedRequest:
        def __init__(self):
            self.checks = 0

        async def is_disconnected(self):
            self.checks += 1
            # Return True on subsequent check to simulate disconnect after starting
            return self.checks >= 2

    class TwoTokenProvider(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "two-token-model"

        async def generate_response(self, messages, **kwargs):
            return LLMResponse(content="two tokens", model="two-token-model")

        async def stream_response(self, messages, **kwargs):
            yield "Token 1"
            await asyncio.sleep(0.05)
            yield "Token 2"

    monkeypatch.setattr(chat_service, "_get_provider", lambda: TwoTokenProvider())

    from app.models.user import AuthenticatedUser
    from app.models.chat import ChatCompletionRequest

    test_user = AuthenticatedUser(id=user_id, email="disc@auren.ai")
    test_conv = await chat_repository.create_conversation(user_id, title="Disconnect Conv")
    test_req = ChatCompletionRequest(message="Disconnect test", idempotency_key=idempotency_key)

    events = []
    async for event in chat_service.stream_chat_completion(
        user=test_user,
        conversation=test_conv,
        request=test_req,
        raw_request=MockDisconnectedRequest(),
    ):
        events.append(event)

    full_output = "".join(events)
    # Crucial assertion: Done event is NOT emitted because stream was interrupted!
    assert "event: done" not in full_output

    # Crucial assertion: Database request lifecycle status is 'interrupted', NEVER 'completed'!
    req_status = await chat_repository.get_chat_request(user_id, idempotency_key)
    assert req_status is not None
    assert req_status.status == "interrupted"
    assert req_status.status != "completed"

    # Crucial assertion: Message is saved with interrupted metadata
    messages = await chat_repository.get_messages(user_id, test_conv.id)
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].metadata.get("interrupted") is True




# ---------------------------------------------------------------------------
# 11. Simultaneous Duplicate Submissions Without Conversation ID
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_simultaneous_duplicate_submissions_without_conversation_id():
    """Verify concurrent requests with NO conversation_id resolve to the exact same conversation,

    store exactly 1 user message, 1 assistant message, 1 chat_request, and execute the provider once.
    """
    user_id = str(uuid.uuid4())
    user_uuid = uuid.UUID(user_id)
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idempotency_key = f"new-conv-race-{uuid.uuid4()}"

    initial_calls = spy_provider.call_count

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        req1 = async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "First prompt in new thread without conv_id", "idempotency_key": idempotency_key},
        )
        req2 = async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "First prompt in new thread without conv_id", "idempotency_key": idempotency_key},
        )
        res1, res2 = await asyncio.gather(req1, req2)

    assert res1.status_code == 200
    assert res2.status_code == 200
    # Crucial assertion: provider invoked exactly once
    assert spy_provider.call_count == initial_calls + 1

    # Database Consistency Assertions:
    all_convs = await chat_repository.list_conversations(user_uuid)
    # Exactly ONE conversation created (no orphan conversation!)
    assert len(all_convs) == 1, f"Expected exactly 1 conversation created, got {len(all_convs)}"
    target_conv_id = all_convs[0].id

    # Exactly ONE user message and ONE assistant message exist
    messages = await chat_repository.get_messages(user_uuid, target_conv_id)
    assert len(messages) == 2, f"Expected 2 messages (1 user, 1 assistant), got {len(messages)}"
    assert messages[0].role == "user"
    assert messages[0].content == "First prompt in new thread without conv_id"
    assert messages[1].role == "assistant"

    # Chat request belongs to the exact same conversation
    chat_req = await chat_repository.get_chat_request(user_uuid, idempotency_key)
    assert chat_req is not None
    assert chat_req.conversation_id == target_conv_id
    assert chat_req.user_message_id == messages[0].id
    assert chat_req.assistant_message_id == messages[1].id
    assert chat_req.status == "completed"


# ---------------------------------------------------------------------------
# 12. Provider Failure After Partial Tokens Remains 'failed'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provider_failure_after_partial_tokens_remains_failed(monkeypatch):
    """Verify that when a provider fails after emitting partial tokens, status remains 'failed' (never overwritten to 'interrupted')."""
    class PartialFailingProvider(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "partial-failing-model"

        async def generate_response(self, messages, **kwargs):
            return LLMResponse(content="fail", model="partial-failing-model")

        async def stream_response(self, messages, **kwargs):
            yield "Token before"
            yield " crash"
            await asyncio.sleep(0.02)
            raise RuntimeError("Mid-generation upstream API crash!")

    monkeypatch.setattr(chat_service, "_get_provider", lambda: PartialFailingProvider())

    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idempotency_key = f"fail-after-partial-{uuid.uuid4()}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        response = await async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Trigger failure after partial", "idempotency_key": idempotency_key},
        )

    assert response.status_code == 200
    assert "event: token" in response.text
    assert "event: error" in response.text

    # Database lifecycle record MUST be 'failed', NEVER 'interrupted'!
    req = await chat_repository.get_chat_request(uuid.UUID(user_id), idempotency_key)
    assert req is not None
    assert req.status == "failed", f"Expected status 'failed', but got '{req.status}'!"


# ---------------------------------------------------------------------------
# 13. Stream Timeout After Partial Tokens Remains 'failed'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stream_timeout_after_partial_tokens_remains_failed(monkeypatch):
    """Verify that when stream times out after emitting partial tokens, status remains 'failed' (never overwritten to 'interrupted')."""
    monkeypatch.setattr(settings, "CHAT_STREAM_TIMEOUT_SECONDS", 1)

    class PartialTimeoutProvider(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "partial-timeout-model"

        async def generate_response(self, messages, **kwargs):
            return LLMResponse(content="timeout", model="partial-timeout-model")

        async def stream_response(self, messages, **kwargs):
            yield "Initial words"
            await asyncio.sleep(1.5)
            yield "Too late"

    monkeypatch.setattr(chat_service, "_get_provider", lambda: PartialTimeoutProvider())

    user_id = str(uuid.uuid4())
    token = create_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    idempotency_key = f"timeout-after-partial-{uuid.uuid4()}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
        response = await async_client.post(
            "/api/v1/chat/completions",
            headers=headers,
            json={"message": "Timeout prompt", "idempotency_key": idempotency_key},
        )

    assert response.status_code == 200
    assert "event: error" in response.text

    # Database lifecycle record MUST be 'failed', NEVER 'interrupted'!
    req = await chat_repository.get_chat_request(uuid.UUID(user_id), idempotency_key)
    assert req is not None
    assert req.status == "failed", f"Expected status 'failed', but got '{req.status}'!"
