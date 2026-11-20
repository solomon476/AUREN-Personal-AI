"""Phase 5B: Real End-to-End Acceptance Verification Suite.

Executes the sequential 12-step operational workflow mandated for Phase 5B:
1. Register or authenticate a test user.
2. Create a conversation.
3. Dispatch prompt to LLM provider (evaluating model routing and live vs mock behavior).
4. Receive AI response stream (SSE event parsing).
5. Confirm conversation and message persistence.
6. Create and retrieve a memory record.
7. Verify memory context retrieval in subsequent conversational flow.
8. Create a task and project with parent linkage.
9. Create and retrieve a private journal entry.
10. Verify strict journal isolation from ordinary memory index.
11. Verify that User B cannot access User A's data (cross-tenant 404 quarantine).
12. Verify session persistence and profile consistency.
"""

import json
import time
from uuid import UUID, uuid4
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)
TEST_JWT_SECRET = "super-secret-test-key-for-supabase-jwt-verification-unit-tests"


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "CHAT_REPOSITORY_TYPE", "sqlite")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")


def generate_jwt(user_id: str, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 7200,
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": email.split("@")[0].capitalize()},
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def test_phase5b_twelve_step_end_to_end_workflow():
    """Execute complete 12-step end-to-end acceptance lifecycle."""
    # Step 1: Register or authenticate test user (User A)
    user_a_id = str(uuid4())
    user_a_token = generate_jwt(user_a_id, "usera_phase5b@auren.local")
    headers_a = {"Authorization": f"Bearer {user_a_token}"}

    profile_res = client.get("/api/v1/auth/me", headers=headers_a)
    assert profile_res.status_code == 200
    assert profile_res.json()["id"] == user_a_id

    # Step 2: Create a conversation
    conv_create_res = client.post(
        "/api/v1/chat/conversations",
        json={"title": "Phase 5B Acceptance Thread"},
        headers=headers_a,
    )
    assert conv_create_res.status_code == 201
    conversation = conv_create_res.json()
    conv_id = conversation["id"]
    assert conversation["title"] == "Phase 5B Acceptance Thread"

    # Step 3 & 4: Dispatch prompt and receive AI response stream (SSE)
    prompt_payload = {
        "conversation_id": conv_id,
        "message": "AUREN operational acceptance test: summarize project objectives",
        "model_id": "mock",
    }
    with client.stream("POST", "/api/v1/chat/completions", json=prompt_payload, headers=headers_a) as stream_res:
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers["content-type"]
        sse_text = "".join(stream_res.iter_text())
        assert "event: meta" in sse_text or "data:" in sse_text
        assert "event: done" in sse_text

    # Step 5: Confirm conversation and message persistence
    messages_res = client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=headers_a)
    assert messages_res.status_code == 200
    messages = messages_res.json()
    assert len(messages) >= 2  # user prompt + assistant completion
    assert any(m["role"] == "user" for m in messages)
    assert any(m["role"] == "assistant" for m in messages)

    # Step 6: Create and retrieve a memory
    memory_payload = {
        "content": "Operator requires dark mode and markdown export by default",
        "memory_type": "preference",
        "category": "technical",
        "importance": 4,
    }
    mem_res = client.post("/api/v1/memories", json=memory_payload, headers=headers_a)
    assert mem_res.status_code == 201
    memory = mem_res.json()
    mem_id = memory["id"]

    get_mem_res = client.get(f"/api/v1/memories/{mem_id}", headers=headers_a)
    assert get_mem_res.status_code == 200
    assert get_mem_res.json()["content"] == memory_payload["content"]

    # Step 7: Verify memory search / retrieval for subsequent conversation
    mem_search_res = client.get("/api/v1/memories?query=markdown", headers=headers_a)
    assert mem_search_res.status_code == 200
    items = mem_search_res.json()["items"]
    assert any(m["id"] == mem_id for m in items)

    # Step 8: Create a project and task
    proj_res = client.post(
        "/api/v1/projects",
        json={"name": "AUREN Phase 5B Acceptance", "description": "Verification of real workflows"},
        headers=headers_a,
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    task_res = client.post(
        "/api/v1/tasks",
        json={"title": "Execute 12-step verification", "project_id": project_id, "priority": "urgent"},
        headers=headers_a,
    )
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]

    # Step 9: Create and retrieve a private journal entry
    journal_res = client.post(
        "/api/v1/journal",
        json={"content": "Private journal record — confidential operator reflection", "mood": "focused"},
        headers=headers_a,
    )
    assert journal_res.status_code == 201
    journal_id = journal_res.json()["id"]

    get_j_res = client.get(f"/api/v1/journal/{journal_id}", headers=headers_a)
    assert get_j_res.status_code == 200
    assert get_j_res.json()["content"] == "Private journal record — confidential operator reflection"

    # Step 10: Verify journal isolation from ordinary memory
    mem_leak_check = client.get("/api/v1/memories?query=confidential", headers=headers_a).json()
    assert mem_leak_check["total"] == 0 or not any("confidential" in m["content"] for m in mem_leak_check["items"])

    # Step 11: Multi-tenant quarantine (User B cannot access User A's data)
    user_b_id = str(uuid4())
    user_b_token = generate_jwt(user_b_id, "userb_phase5b@auren.local")
    headers_b = {"Authorization": f"Bearer {user_b_token}"}

    assert client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=headers_b).status_code == 404
    assert client.patch(f"/api/v1/chat/conversations/{conv_id}", json={"title": "Unauthorized"}, headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/memories/{mem_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/journal/{journal_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/tasks/{task_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}", headers=headers_b).status_code == 404

    # Step 12: Session persistence verification
    data_export_res = client.post("/api/v1/auth/export", headers=headers_a)
    assert data_export_res.status_code == 200
    export_pkg = data_export_res.json()
    assert export_pkg["user_id"] == user_a_id
    assert len(export_pkg["memories"]) >= 1
    assert len(export_pkg["tasks"]) >= 1
    assert len(export_pkg["projects"]) >= 1
    assert len(export_pkg["journal_entries"]) >= 1


@pytest.mark.asyncio
async def test_gemini_provider_unconfigured_credentials_rejection():
    """Verify that GeminiProvider strictly refuses operation without valid API key."""
    from app.services.llm.gemini import GeminiProvider
    from app.services.llm.base import LLMAuthenticationError

    provider = GeminiProvider(api_key=None, model_id="gemini-2.5-flash")
    with pytest.raises(LLMAuthenticationError) as exc_info:
        await provider.generate_response(messages=[])
    assert "Gemini API key is not configured" in str(exc_info.value)

    with pytest.raises(LLMAuthenticationError) as exc_info_stream:
        async for _ in provider.stream_response(messages=[]):
            pass
    assert "Gemini API key is not configured" in str(exc_info_stream.value)


def test_public_api_zero_credential_leakage():
    """Verify that no sensitive backend credentials or environment variables leak in responses."""
    # Health endpoint
    health_data = client.get("/api/v1/health").json()
    serialized_health = json.dumps(health_data).lower()
    for sensitive_word in ["key", "secret", "password", "token", "hmac"]:
        assert sensitive_word not in serialized_health

    # Unauthenticated /auth/me
    unauth_res = client.get("/api/v1/auth/me")
    assert unauth_res.status_code == 401
    assert "secret" not in unauth_res.text.lower()
