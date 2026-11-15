"""Unit tests for SupabasePostgresChatRepository adapter.

Verifies:
- Authenticated user JWT token and public anon key are sent in headers.
- Service-role key is never used.
- Atomic idempotency claiming handles 201 Created vs 409 Conflict.
- Conversation and message CRUD operations map correctly to PostgREST endpoints.
"""

import json
from uuid import UUID, uuid4
import httpx
import pytest

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


def test_supabase_repo_create_and_get_conversation():
    """Verify conversation creation and retrieval via mocked PostgREST."""
    conv_data = {
        "id": str(CONV_ID),
        "user_id": str(USER_ID),
        "title": "Architectural Strategy",
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:00+00:00",
    }

    def handler(request: httpx.Request) -> httpx.Response:
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
    with httpx.Client(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        conv = repo.create_conversation(USER_ID, title="Architectural Strategy")
        assert conv.id == CONV_ID
        assert conv.title == "Architectural Strategy"

        fetched = repo.get_conversation(USER_ID, CONV_ID)
        assert fetched is not None
        assert fetched.id == CONV_ID
        assert fetched.title == "Architectural Strategy"


def test_supabase_repo_claim_chat_request_atomic_success():
    """Verify atomic claim returns (True, req) when PostgREST returns 201 Created."""
    req_data = {
        "user_id": str(USER_ID),
        "idempotency_key": "idemp-atomic-1",
        "conversation_id": str(CONV_ID),
        "status": "processing",
        "user_message_id": str(uuid4()),
        "assistant_message_id": None,
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:00+00:00",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/chat_requests" in str(request.url):
            return httpx.Response(201, json=[req_data])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        claimed, req = repo.claim_chat_request(
            user_id=USER_ID,
            idempotency_key="idemp-atomic-1",
            conversation_id=CONV_ID,
            user_message_id=UUID(req_data["user_message_id"]),
        )
        assert claimed is True
        assert req.status == "processing"
        assert req.idempotency_key == "idemp-atomic-1"


def test_supabase_repo_claim_chat_request_conflict_returns_existing():
    """Verify atomic claim returns (False, existing_req) when PostgREST returns 409 Conflict."""
    existing_data = {
        "user_id": str(USER_ID),
        "idempotency_key": "idemp-atomic-conflict",
        "conversation_id": str(CONV_ID),
        "status": "processing",
        "user_message_id": str(uuid4()),
        "assistant_message_id": None,
        "created_at": "2026-11-16T00:00:00+00:00",
        "updated_at": "2026-11-16T00:00:00+00:00",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        # POST returns 409 Conflict
        if request.method == "POST" and "/chat_requests" in str(request.url):
            return httpx.Response(409, text="duplicate key value violates unique constraint")
        # GET returns existing record
        if request.method == "GET" and "/chat_requests" in str(request.url):
            return httpx.Response(200, json=[existing_data])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as mock_client:
        repo = SupabasePostgresChatRepository(
            supabase_url=TEST_SUPABASE_URL,
            supabase_anon_key=TEST_ANON_KEY,
            user_token=TEST_USER_TOKEN,
            http_client=mock_client,
        )

        claimed, req = repo.claim_chat_request(
            user_id=USER_ID,
            idempotency_key="idemp-atomic-conflict",
            conversation_id=CONV_ID,
            user_message_id=UUID(existing_data["user_message_id"]),
        )
        assert claimed is False
        assert req.status == "processing"
        assert req.idempotency_key == "idemp-atomic-conflict"
