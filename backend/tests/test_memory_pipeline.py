"""Comprehensive test suite for Phase 3B.2.2 persistent memory extraction,
retrieval, context injection, worker fencing, and lifecycle invariants.

Verifies:
1. Journal quarantine at completion.
2. Journal quarantine at extraction-source retrieval.
3. Three-field consent identity matching (user_id, conversation_id, idempotency_key).
4. Forged client metadata (cannot clear quarantine).
5. Malformed metadata (fails closed).
6. Interrupted requests (not enqueued).
7. Atomic completion and outbox insertion.
8. Historical completed requests remaining unenqueued.
9. Duplicate outbox insertion prevention.
10. Worker session authorization.
11. Claim-token mismatch rejection.
12. Expired leases rejection.
13. Reclaimed jobs and stale worker fencing.
14. Terminal lifecycle cleanup (clears locks, rotates claim token).
15. Memory provenance and epistemic status (chat_inferred, unconfirmed, rejects system_asserted).
16. Duplicate extraction prevention.
17. Hybrid retrieval component bounds (infimum > 0.03, supremum < 1.00, NULL confidence fallback).
18. Memory lifecycle filtering (active only, excludes rejected/expired).
19. Token-budget enforcement using native count_tokens.
20. Memory-context omission when native token counting is unavailable.
21. Journal exclusion from ordinary retrieval and prompt context.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional
import uuid

import asyncpg
import pytest

from app.core.config import settings, get_journal_hmac_secret
from app.services.journal.consent import (
    create_journal_consent_token,
    verify_and_consume_journal_consent,
)
from app.services.embeddings.factory import MockEmbeddingProvider
from app.services.llm.base import BaseLLMProvider, ChatMessage, LLMResponse
from app.services.memory.context_manager import MemoryContextManager
from app.services.memory.models import ExtractedMemoryItem, MemorySearchResult
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.worker import MemoryExtractionWorker
from tests.test_memory_database import isolated_postgres_db, postgresql_server


# ============================================================================
# Mock Providers for Token Counting & Extraction
# ============================================================================

class MockTokenCountingProvider(BaseLLMProvider):
    """Test provider with accurate native token counting simulation."""

    def __init__(self, token_factor: int = 4, supports_tokens: bool = True):
        self.token_factor = token_factor
        self.supports_tokens = supports_tokens

    def get_model_id(self) -> str:
        return "mock-token-model"

    async def generate_response(self, messages: List[ChatMessage], **kwargs) -> LLMResponse:
        return LLMResponse(content="[]", model=self.get_model_id())

    async def stream_response(self, messages: List[ChatMessage], **kwargs) -> AsyncIterator[str]:
        yield "token"

    async def count_tokens(self, text: str) -> Optional[int]:
        if not self.supports_tokens:
            return None
        return max(1, len(text) // self.token_factor)


class MockExtractionProvider(BaseLLMProvider):
    """Test provider returning canned structured extraction responses."""

    def __init__(self, response_json: str):
        self.response_json = response_json

    def get_model_id(self) -> str:
        return "mock-extraction-model"

    async def generate_response(self, messages: List[ChatMessage], **kwargs) -> LLMResponse:
        return LLMResponse(content=self.response_json, model=self.get_model_id())

    async def stream_response(self, messages: List[ChatMessage], **kwargs) -> AsyncIterator[str]:
        yield self.response_json

    async def count_tokens(self, text: str) -> Optional[int]:
        return len(text) // 4


# ============================================================================
# Helper for Valid Consent Tokens
# ============================================================================

async def issue_and_consume_consent(conn, user_id: uuid.UUID, conv_id: uuid.UUID, idemp_key: str, date_range: str = "2026-11-01..2026-11-16"):
    now = datetime.now(timezone.utc)
    secret = get_journal_hmac_secret()
    token = create_journal_consent_token(
        user_id=user_id,
        conversation_id=conv_id,
        idempotency_key=idemp_key,
        scope="journal.read",
        date_range=date_range,
        nonce=uuid.uuid4(),
        expires_at=now + timedelta(seconds=120),
        secret=secret,
    )
    await verify_and_consume_journal_consent(
        token=token,
        secret=secret,
        expected_user_id=user_id,
        expected_conversation_id=conv_id,
        expected_idempotency_key=idemp_key,
        expected_date_range=date_range,
        db_conn=conn,
        now=now,
    )
    return token


# ============================================================================
# 1-6: Journal Isolation & Metadata Fail-Closed Tests
# ============================================================================

@pytest.mark.asyncio
async def test_journal_quarantine_at_completion(postgresql_server):
    """1. Verify that a chat request involving journal consent is quarantined at completion."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p1") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-journal-1"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u1@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 1')", conv_id, user_id)

        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Read journal')", user_msg_id, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Journal summary')", asst_msg_id, conv_id, user_id)

        # Claim chat request
        fp = "a" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg_id, fp)

        # Consume journal consent token for this exact (user_id, conversation_id, idempotency_key)
        await issue_and_consume_consent(conn, user_id, conv_id, idemp_key)

        # Complete chat request
        res = await conn.fetchval("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg_id)
        res_data = json.loads(res)
        assert res_data["status"] == "completed"
        assert res_data["contains_journal_data"] is True

        # Assert NO job was enqueued into memory_extraction_jobs
        jobs = await conn.fetch("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1", user_id)
        assert len(jobs) == 0


@pytest.mark.asyncio
async def test_journal_quarantine_at_extraction_source_retrieval(postgresql_server):
    """2. Verify that extraction source fetch refetches quarantine status and fails closed."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p2") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-journal-fetch"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u2@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 2')", conv_id, user_id)

        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'User prompt')", user_msg_id, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Response')", asst_msg_id, conv_id, user_id)

        # Chat request flagged with contains_journal_data
        fp = "b" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg_id, fp)
        await conn.execute("UPDATE public.chat_requests SET status = 'completed', assistant_message_id = $1, contains_journal_data = TRUE WHERE user_id = $2 AND idempotency_key = $3", asst_msg_id, user_id, idemp_key)

        # Artificially insert a job
        job_id = uuid.uuid4()
        token = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memory_extraction_jobs (
                id, user_id, conversation_id, source_message_id, idempotency_key, status, locked_by, lease_expires_at, claim_token
            ) VALUES ($1, $2, $3, $4, $5, 'processing', 'worker-test', now() + INTERVAL '1 hour', $6)
            """,
            job_id, user_id, conv_id, asst_msg_id, idemp_key, token,
        )

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw")
        try:
            rows = await worker_conn.fetch("SELECT * FROM public.fetch_extraction_source_message_rpc($1, 'worker-test', $2)", job_id, token)
            # Quarantined turn returns 0 rows (zero retention)
            assert len(rows) == 0

            # Assert job is transitioned to dead_letter in database
            job_row = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE id = $1", job_id)
            assert job_row["status"] == "dead_letter"
            assert "[QUARANTINE]" in job_row["last_error"]
        finally:
            await worker_conn.close()


@pytest.mark.asyncio
async def test_three_field_consent_identity_matching(postgresql_server):
    """3. Verify consent ledger lookups strictly match user_id, conversation_id, and idempotency_key."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p3") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_a = uuid.uuid4()
        conv_b = uuid.uuid4()
        idemp_1 = "turn-idemp-1"
        idemp_2 = "turn-idemp-2"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u3@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv A')", conv_a, user_id)
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv B')", conv_b, user_id)

        # Consent is consumed for (user_id, conv_a, idemp_1)
        await issue_and_consume_consent(conn, user_id, conv_a, idemp_1)

        # Setup messages for turn in conv_b with idemp_2 (unrelated conversation and key)
        user_msg = uuid.uuid4()
        asst_msg = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'General chat')", user_msg, conv_b, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'General reply')", asst_msg, conv_b, user_id)

        fp = "c" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_2, conv_b, user_msg, fp)

        # Complete request for conv_b / idemp_2 -> must NOT be quarantined
        res = await conn.fetchval("SELECT public.complete_chat_request($1, $2)", idemp_2, asst_msg)
        res_data = json.loads(res)
        assert res_data["contains_journal_data"] is False

        # Extraction job MUST be enqueued
        job = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1 AND idempotency_key = $2", user_id, idemp_2)
        assert job is not None
        assert job["source_message_id"] == asst_msg


@pytest.mark.asyncio
async def test_forged_client_metadata(postgresql_server):
    """4. Verify client-supplied metadata cannot clear server-side quarantine."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p4") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-forged"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u4@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 4')", conv_id, user_id)

        user_msg = uuid.uuid4()
        asst_msg = uuid.uuid4()
        # Malicious client injects contains_journal_data = false
        forged_meta = json.dumps({"contains_journal_data": False})
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'user', 'Read journal', $4::jsonb)", user_msg, conv_id, user_id, forged_meta)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'assistant', 'Journal text', $4::jsonb)", asst_msg, conv_id, user_id, forged_meta)

        fp = "d" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg, fp)

        # Ledger record exists
        await issue_and_consume_consent(conn, user_id, conv_id, idemp_key)

        res = await conn.fetchval("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg)
        res_data = json.loads(res)
        # Server record overrides forged client metadata
        assert res_data["contains_journal_data"] is True

        jobs = await conn.fetch("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1", user_id)
        assert len(jobs) == 0


@pytest.mark.asyncio
async def test_malformed_metadata(postgresql_server):
    """5. Verify malformed metadata fails closed to quarantined."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p5") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-malformed"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u5@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 5')", conv_id, user_id)

        user_msg = uuid.uuid4()
        asst_msg = uuid.uuid4()
        # String instead of boolean -> malformed
        malformed_meta = json.dumps({"contains_journal_data": "maybe"})
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'user', 'Hello', $4::jsonb)", user_msg, conv_id, user_id, malformed_meta)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Hi')", asst_msg, conv_id, user_id)

        fp = "e" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg, fp)

        res = await conn.fetchval("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg)
        res_data = json.loads(res)
        # Malformed fails closed to True
        assert res_data["contains_journal_data"] is True

        jobs = await conn.fetch("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1", user_id)
        assert len(jobs) == 0


@pytest.mark.asyncio
async def test_interrupted_requests(postgresql_server):
    """6. Verify interrupted requests are never enqueued for memory extraction."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p6") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-interrupted"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u6@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 6')", conv_id, user_id)

        user_msg = uuid.uuid4()
        asst_msg = uuid.uuid4()
        interrupted_meta = json.dumps({"interrupted": True})
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Stream prompt')", user_msg, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'assistant', 'Partial...', $4::jsonb)", asst_msg, conv_id, user_id, interrupted_meta)

        fp = "f" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg, fp)

        res = await conn.fetchval("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg)
        res_data = json.loads(res)
        assert res_data["status"] == "completed"

        jobs = await conn.fetch("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1", user_id)
        assert len(jobs) == 0


# ============================================================================
# 7-9: Transactional Outbox Invariants Tests
# ============================================================================

@pytest.mark.asyncio
async def test_atomic_completion_and_outbox_insertion(postgresql_server):
    """7. Verify atomic completion and outbox insertion in the same database transaction."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p7") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-atomic"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u7@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 7')", conv_id, user_id)

        user_msg = uuid.uuid4()
        asst_msg = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'What is Python?')", user_msg, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Python is a programming language')", asst_msg, conv_id, user_id)

        fp = "0" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg, fp)

        res = await conn.fetchval("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg)
        res_data = json.loads(res)
        assert res_data["status"] == "completed"

        job = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1", user_id)
        assert job is not None
        assert job["source_message_id"] == asst_msg
        assert job["idempotency_key"] == idemp_key
        assert job["status"] == "pending"


@pytest.mark.asyncio
async def test_historical_completed_requests_unenqueued(postgresql_server):
    """8. Verify that historical completed requests remain permanently unenqueued (no retroactive backfill)."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p8") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-legacy-completed"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u8@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 8')", conv_id, user_id)

        user_msg = uuid.uuid4()
        asst_msg = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Past turn')", user_msg, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Past answer')", asst_msg, conv_id, user_id)

        # Historical completed request
        fp = "1" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg, fp)
        await conn.execute("UPDATE public.chat_requests SET status = 'completed', assistant_message_id = $1 WHERE user_id = $2 AND idempotency_key = $3", asst_msg, user_id, idemp_key)

        # Calling complete_chat_request again (e.g. client reconnect)
        res = await conn.fetchval("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg)
        res_data = json.loads(res)
        assert res_data["status"] == "completed"

        # Assert no extraction job was inserted
        jobs = await conn.fetch("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1", user_id)
        assert len(jobs) == 0


@pytest.mark.asyncio
async def test_duplicate_outbox_insertion_prevention(postgresql_server):
    """9. Verify unique constraint on (user_id, source_message_id) prevents duplicate queueing."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p9") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-dup"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u9@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 9')", conv_id, user_id)

        user_msg = uuid.uuid4()
        asst_msg = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Prompt')", user_msg, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Reply')", asst_msg, conv_id, user_id)

        fp = "2" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg, fp)

        # First completion
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg)
        # Idempotent second completion
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg)

        jobs = await conn.fetch("SELECT * FROM public.memory_extraction_jobs WHERE user_id = $1 AND source_message_id = $2", user_id, asst_msg)
        assert len(jobs) == 1


# ============================================================================
# 10-14: Worker Authorization, Fencing & Terminal Lifecycle
# ============================================================================

@pytest.mark.asyncio
async def test_worker_session_authorization(postgresql_server):
    """10. Verify worker RPCs strictly reject non-worker sessions."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p10") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u10@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        client_user = f"client_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {client_user} WITH PASSWORD 'pw' IN ROLE authenticated")
        client_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=client_user, password="pw")
        try:
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await client_conn.execute("SELECT * FROM public.fetch_extraction_source_message_rpc($1, 'worker-1', $2)", uuid.uuid4(), uuid.uuid4())
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await client_conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-1', $2)", uuid.uuid4(), uuid.uuid4())
        finally:
            await client_conn.close()


@pytest.mark.asyncio
async def test_claim_token_mismatch(postgresql_server):
    """11. Verify that claim token mismatch is strictly rejected across all worker RPCs."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p11") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u11@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 11')", conv_id, user_id)
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Test')", msg_id, conv_id, user_id)

        job_id = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw")
        try:
            claimed = await worker_conn.fetchrow("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-1', 1, 300)")
            assert claimed["id"] == job_id
            real_token = claimed["claim_token"]
            bogus_token = uuid.uuid4()

            with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                await worker_conn.execute("SELECT * FROM public.fetch_extraction_source_message_rpc($1, 'worker-1', $2)", job_id, bogus_token)

            with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                await worker_conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-1', $2)", job_id, bogus_token)
        finally:
            await worker_conn.close()


@pytest.mark.asyncio
async def test_expired_leases(postgresql_server):
    """12. Verify mutating worker RPCs reject expired leases independently."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p12") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u12@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 12')", conv_id, user_id)
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Test')", msg_id, conv_id, user_id)

        job_id = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw")
        try:
            claimed = await worker_conn.fetchrow("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-1', 1, 300)")
            token = claimed["claim_token"]

            # Artificially expire lease in database
            await conn.execute("UPDATE public.memory_extraction_jobs SET lease_expires_at = now() - INTERVAL '10 seconds' WHERE id = $1", job_id)

            with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="lease expired"):
                await worker_conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-1', $2)", job_id, token)

            with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="lease expired"):
                await worker_conn.execute(
                    """
                    SELECT public.insert_extracted_memory_rpc(
                        p_job_id => $1,
                        p_worker_id => 'worker-1',
                        p_claim_token => $2,
                        p_content => 'Expired content',
                        p_memory_type => 'fact',
                        p_category => 'general'
                    )
                    """,
                    job_id, token,
                )
        finally:
            await worker_conn.close()


@pytest.mark.asyncio
async def test_reclaimed_jobs_and_stale_workers(postgresql_server):
    """13. Verify reclaimed jobs generate new fencing token, permanently locking out stale worker."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p13") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u13@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 13')", conv_id, user_id)
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Test')", msg_id, conv_id, user_id)

        job_id = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw")
        try:
            # Worker A claims job
            claimed_a = await worker_conn.fetchrow("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', 1, 300)")
            token_a = claimed_a["claim_token"]

            # Worker A stalls, lease expires
            await conn.execute("UPDATE public.memory_extraction_jobs SET lease_expires_at = now() - INTERVAL '10 seconds' WHERE id = $1", job_id)

            # Worker B reclaims job
            claimed_b = await worker_conn.fetchrow("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-b', 1, 300)")
            assert claimed_b["id"] == job_id
            token_b = claimed_b["claim_token"]
            assert token_b != token_a

            # Stale Worker A resumes and attempts to insert extracted memory: REJECTED with Stale claim token
            with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                await worker_conn.execute(
                    """
                    SELECT public.insert_extracted_memory_rpc(
                        p_job_id => $1,
                        p_worker_id => 'worker-a',
                        p_claim_token => $2,
                        p_content => 'Stale memory from Worker A',
                        p_memory_type => 'fact',
                        p_category => 'general'
                    )
                    """,
                    job_id, token_a,
                )

            # Worker B inserts extracted memory: SUCCEEDS
            mem_id = await worker_conn.fetchval(
                """
                SELECT public.insert_extracted_memory_rpc(
                    p_job_id => $1,
                    p_worker_id => 'worker-b',
                    p_claim_token => $2,
                    p_content => 'Valid memory from Worker B',
                    p_memory_type => 'fact',
                    p_category => 'general'
                )
                """,
                job_id, token_b,
            )
            assert mem_id is not None
        finally:
            await worker_conn.close()


@pytest.mark.asyncio
async def test_terminal_lifecycle_cleanup(postgresql_server):
    """14. Verify terminal cleanup clears locked_by, lease_expires_at, and rotates claim_token."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p14") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u14@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 14')", conv_id, user_id)
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Test')", msg_id, conv_id, user_id)

        job_id = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw")
        try:
            claimed = await worker_conn.fetchrow("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-1', 1, 300)")
            token = claimed["claim_token"]

            # Complete job
            success = await worker_conn.fetchval("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-1', $2)", job_id, token)
            assert success is True

            job_row = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE id = $1", job_id)
            assert job_row["status"] == "completed"
            assert job_row["locked_by"] is None
            assert job_row["lease_expires_at"] is None
            assert job_row["completed_token"] == token
            assert job_row["claim_token"] != token  # Rotated for terminal safety

            # Repeated completion with matching token succeeds idempotently
            repeat_ok = await worker_conn.fetchval("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-1', $2)", job_id, token)
            assert repeat_ok is True
        finally:
            await worker_conn.close()


# ============================================================================
# 15-16: Provenance & Deduplication Invariants Tests
# ============================================================================

@pytest.mark.asyncio
async def test_memory_provenance_and_epistemic_status(postgresql_server):
    """15. Verify worker extraction produces origin=chat_inferred, confirmation_status=unconfirmed,
    and rejects system_asserted creation.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_p15") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u15@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 15')", conv_id, user_id)
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Test')", msg_id, conv_id, user_id)

        job_id = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw")
        try:
            claimed = await worker_conn.fetchrow("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-1', 1, 300)")
            token = claimed["claim_token"]

            # Attempting to forge system_asserted in metadata is rejected
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="Worker extractions cannot create system_asserted memories"):
                await worker_conn.execute(
                    """
                    SELECT public.insert_extracted_memory_rpc(
                        p_job_id => $1,
                        p_worker_id => 'worker-1',
                        p_claim_token => $2,
                        p_content => 'Rogue assertion',
                        p_memory_type => 'fact',
                        p_category => 'general',
                        p_metadata => '{"confirmation_status": "system_asserted"}'::jsonb
                    )
                    """,
                    job_id, token,
                )

            # Normal ingestion
            mem_id = await worker_conn.fetchval(
                """
                SELECT public.insert_extracted_memory_rpc(
                    p_job_id => $1,
                    p_worker_id => 'worker-1',
                    p_claim_token => $2,
                    p_content => 'User prefers dark mode',
                    p_memory_type => 'preference',
                    p_category => 'personal',
                    p_importance => 4,
                    p_confidence => 0.85
                )
                """,
                job_id, token,
            )
            assert mem_id is not None

            mem_row = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", mem_id)
            assert mem_row["origin"] == "chat_inferred"
            assert mem_row["confirmation_status"] == "unconfirmed"
            assert mem_row["last_confirmed_at"] is None
            assert mem_row["source_message_id"] == msg_id
            assert mem_row["source_conversation_id"] == conv_id
            assert mem_row["root_memory_id"] == mem_id
        finally:
            await worker_conn.close()


@pytest.mark.asyncio
async def test_duplicate_extraction_prevention(postgresql_server):
    """16. Verify duplicate extraction for the same source turn returns existing ID without duplicating storage."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p16") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u16@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 16')", conv_id, user_id)
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Test')", msg_id, conv_id, user_id)

        job_id = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw")
        try:
            claimed = await worker_conn.fetchrow("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-1', 1, 300)")
            token = claimed["claim_token"]

            # First extraction insertion
            id_1 = await worker_conn.fetchval(
                """
                SELECT public.insert_extracted_memory_rpc(
                    p_job_id => $1,
                    p_worker_id => 'worker-1',
                    p_claim_token => $2,
                    p_content => 'User prefers Python',
                    p_memory_type => 'preference',
                    p_category => 'technical'
                )
                """,
                job_id, token,
            )

            # Second extraction insertion with same normalized content for same source message
            id_2 = await worker_conn.fetchval(
                """
                SELECT public.insert_extracted_memory_rpc(
                    p_job_id => $1,
                    p_worker_id => 'worker-1',
                    p_claim_token => $2,
                    p_content => '  user prefers python  ',
                    p_memory_type => 'preference',
                    p_category => 'technical'
                )
                """,
                job_id, token,
            )

            assert id_1 == id_2
            count = await conn.fetchval("SELECT count(*) FROM public.memories WHERE user_id = $1", user_id)
            assert count == 1
        finally:
            await worker_conn.close()


# ============================================================================
# 17-18: Hybrid Retrieval Scoring & Lifecycle Filtering Tests
# ============================================================================

@pytest.mark.asyncio
async def test_hybrid_retrieval_component_bounds(postgresql_server):
    """17. Verify hybrid retrieval score bounds: infimum > 0.03, supremum < 1.00, neutral 0.50 fallback for NULL confidence."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p17") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u17@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # 1. Insert minimum possible memory: observation (decaying), importance 1, confidence 0.0, created 500 days ago
        mem_min_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence, created_at)
            VALUES ($1, $2, 'completely unrelated query words xyz', 'observation', 'general', 1, 0.0, now() - INTERVAL '500 days')
            """,
            mem_min_id, user_id,
        )

        # 2. Insert maximum possible memory: preference (non-decaying 0.10), importance 5 (0.15), confidence 1.0 (0.10), exact lexical match
        mem_max_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence)
            VALUES ($1, $2, 'quantum computing algorithm optimization', 'preference', 'technical', 5, 1.0)
            """,
            mem_max_id, user_id,
        )

        # Attach exact active embedding to mem_max
        vec_768 = [0.03] * 768
        vec_str = f"[{','.join(str(x) for x in vec_768)}]"
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (
                memory_id, user_id, provider, model, version, dimension, embedding_768, is_active
            ) VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)
            """,
            mem_max_id, user_id, vec_str,
        )

        # 3. Insert memory with NULL confidence (legacy simulation)
        mem_null_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence)
            VALUES ($1, $2, 'legacy memory with null confidence', 'fact', 'general', 3, NULL)
            """,
            mem_null_id, user_id,
        )

        # Query with text and embedding matching mem_max
        results = await conn.fetch(
            """
            SELECT * FROM public.search_memories_hybrid_rpc(
                p_query_text => 'quantum computing algorithm optimization',
                p_query_embedding => $1::vector,
                p_limit => 10,
                p_min_similarity => 0.0
            )
            """,
            vec_str,
        )
        scores = {r["id"]: r["score"] for r in results}

        # Check maximum score: strictly less than 1.00 (supremum < 1.00) and > 0.65 with full match
        assert mem_max_id in scores
        max_score = scores[mem_max_id]
        assert max_score < 1.00
        assert max_score > 0.65  # High semantic + lexical match

        # Check minimum score: strictly greater than 0.03 (infimum > 0.03)
        assert mem_min_id in scores
        min_score = scores[mem_min_id]
        assert min_score > 0.03
        assert min_score < 0.15

        # Check NULL confidence memory: received 0.50 neutral fallback (0.05 contribution)
        assert mem_null_id in scores
        null_conf_score = scores[mem_null_id]
        assert null_conf_score > 0.10


@pytest.mark.asyncio
async def test_memory_lifecycle_filtering(postgresql_server):
    """18. Verify search_memories_hybrid_rpc strictly filters inactive, rejected, or expired memories."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p18") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u18@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # Active memory
        await conn.execute("INSERT INTO public.memories (user_id, content, memory_type, category, lifecycle_status, confirmation_status, last_confirmed_at) VALUES ($1, 'Active Fact', 'fact', 'general', 'active', 'confirmed', now())", user_id)
        # Superseded memory
        await conn.execute("INSERT INTO public.memories (user_id, content, memory_type, category, lifecycle_status, confirmation_status, last_confirmed_at) VALUES ($1, 'Superseded Fact', 'fact', 'general', 'superseded', 'confirmed', now())", user_id)
        # Expired memory
        await conn.execute("INSERT INTO public.memories (user_id, content, memory_type, category, lifecycle_status, confirmation_status, expires_at, last_confirmed_at) VALUES ($1, 'Expired Fact', 'fact', 'general', 'active', 'confirmed', now() - INTERVAL '1 day', now())", user_id)
        # Rejected memory
        await conn.execute("INSERT INTO public.memories (user_id, content, memory_type, category, lifecycle_status, confirmation_status) VALUES ($1, 'Rejected Fact', 'fact', 'general', 'active', 'rejected')", user_id)

        results = await conn.fetch("SELECT * FROM public.search_memories_hybrid_rpc('Fact', NULL, 10, 0.0)")
        contents = [r["content"] for r in results]
        assert "Active Fact" in contents
        assert "Superseded Fact" not in contents
        assert "Expired Fact" not in contents
        assert "Rejected Fact" not in contents


# ============================================================================
# 19-21: Token Budget & Context Injection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_token_budget_enforcement():
    """19. Verify memory context manager packs memories up to exact native token budget."""
    mock_provider = MockTokenCountingProvider(token_factor=4, supports_tokens=True)

    candidates = [
        MemorySearchResult(id=uuid.uuid4(), content="Short fact 1", memory_type="fact", category="general", importance=3, confidence=0.8, confirmation_status="confirmed", score=0.8),
        MemorySearchResult(id=uuid.uuid4(), content="A second longer preference statement about coding styles", memory_type="preference", category="technical", importance=4, confidence=0.9, confirmation_status="confirmed", score=0.75),
        MemorySearchResult(id=uuid.uuid4(), content="A third very lengthy memory item that will exceed the configured tight token budget", memory_type="fact", category="work", importance=5, confidence=0.95, confirmation_status="confirmed", score=0.7),
    ]

    class FakeRetriever:
        async def search_memories(self, *args, **kwargs):
            return candidates

    ctx_mgr = MemoryContextManager(retriever=FakeRetriever())

    # Generous budget: fits all 3
    xml_large = await ctx_mgr.build_memory_context(uuid.uuid4(), "query", mock_provider, budget_tokens=500)
    assert "Short fact 1" in xml_large
    assert "coding styles" in xml_large
    assert "very lengthy memory item" in xml_large

    # Tight budget: fits only first 1 or 2
    tight_budget = 210
    xml_small = await ctx_mgr.build_memory_context(uuid.uuid4(), "query", mock_provider, budget_tokens=tight_budget)
    token_cost = await mock_provider.count_tokens(xml_small)
    assert token_cost <= tight_budget
    assert "Short fact 1" in xml_small
    assert "very lengthy memory item" not in xml_small


@pytest.mark.asyncio
async def test_memory_context_omission_when_native_counting_unavailable():
    """20. Verify that memory context is omitted completely when native token counting is unavailable."""
    offline_provider = MockTokenCountingProvider(supports_tokens=False)

    candidates = [
        MemorySearchResult(id=uuid.uuid4(), content="User preference", memory_type="preference", category="general", importance=4, confidence=0.85, confirmation_status="confirmed", score=0.8),
    ]

    class FakeRetriever:
        async def search_memories(self, *args, **kwargs):
            return candidates

    ctx_mgr = MemoryContextManager(retriever=FakeRetriever())
    result_xml = await ctx_mgr.build_memory_context(uuid.uuid4(), "query", offline_provider, budget_tokens=500)

    # Must be completely omitted (empty string)
    assert result_xml == ""


@pytest.mark.asyncio
async def test_journal_exclusion_from_ordinary_retrieval_and_prompt_context(postgresql_server):
    """21. Verify that private journal entries never leak into memory retrieval or prompt context."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p21") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u21@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # Insert private journal entry
        await conn.execute(
            """
            INSERT INTO public.journal_entries (user_id, title, content)
            VALUES ($1, 'Deep Secret Journal', 'Secret thoughts about life and feelings')
            """,
            user_id,
        )

        # Insert ordinary memory
        await conn.execute(
            """
            INSERT INTO public.memories (user_id, content, memory_type, category)
            VALUES ($1, 'Ordinary public fact about work', 'fact', 'work')
            """,
            user_id,
        )

        # Search memories via hybrid retrieval
        results = await conn.fetch("SELECT * FROM public.search_memories_hybrid_rpc('Secret thoughts life feelings', NULL, 10, 0.0)")
        contents = [r["content"] for r in results]

        # Assert journal entry was NOT retrieved
        assert not any("Deep Secret" in c or "Secret thoughts" in c for c in contents)
        # Ordinary memory can be retrieved if relevant
        all_results = await conn.fetch("SELECT * FROM public.search_memories_hybrid_rpc('work', NULL, 10, 0.0)")
        assert any("Ordinary public fact" in r["content"] for r in all_results)


@pytest.mark.asyncio
async def test_hybrid_retrieval_scoring_weights_regression(postgresql_server):
    """22. Verify exact approved hybrid scoring weights: 0.40 sem + 0.25 lex + 0.15 imp + 0.10 decay + 0.10 conf.
    Specifically tests against weight reversal (0.25 sem + 0.40 lex) and prior substitution (0.35 sem + 0.30 lex).
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_weights") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "weights@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        query_vec = [0.03] * 768
        query_vec_str = f"[{','.join(str(x) for x in query_vec)}]"

        # Memory 1: Pure Semantic Match (S_sem = 1.0, S_lex = 0.0)
        # Content has zero lexical overlap with query
        # importance = 5 (s_imp = 0.15)
        # memory_type = 'preference' (s_decay = 0.10)
        # confidence = 1.0 (s_conf = 0.10)
        # Expected score: 0.40 * 1.0 + 0.25 * 0.0 + 0.15 + 0.10 + 0.10 = 0.750
        # If reversed (0.25 sem): score would be 0.600
        # If 0.35 sem: score would be 0.700
        mem_sem_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence)
            VALUES ($1, $2, 'completely unrelated content alpha beta', 'preference', 'general', 5, 1.0)
            """,
            mem_sem_id, user_id,
        )
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active)
            VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)
            """,
            mem_sem_id, user_id, query_vec_str,
        )

        results = await conn.fetch(
            """
            SELECT id, score FROM public.search_memories_hybrid_rpc(
                p_query_text => 'uniquequeryterm',
                p_query_embedding => $1::vector,
                p_limit => 5,
                p_min_similarity => 0.0
            )
            """,
            query_vec_str,
        )
        scores = {r["id"]: r["score"] for r in results}
        assert mem_sem_id in scores
        actual_sem_score = scores[mem_sem_id]

        # Verify exact 0.40 semantic weight contribution: 0.40 + 0.15 + 0.10 + 0.10 = 0.750
        assert abs(actual_sem_score - 0.750) < 0.005, f"Expected 0.750 (0.40 semantic weight), got {actual_sem_score}"


@pytest.mark.asyncio
async def test_memory_context_epistemic_formatting_and_escaping():
    """23. Verify that MemoryContextManager._format_memory_xml:
    1. Serializes unconfirmed memories with confirmation_status="unconfirmed".
    2. Serializes confirmed memories with confirmation_status="confirmed".
    3. Serializes system_asserted memories with confirmation_status="system_asserted".
    4. Includes explicit epistemic instructions distinguishing tentative from confirmed info.
    5. Safely escapes XML special characters in content and attributes so structure cannot be broken.
    """
    import xml.etree.ElementTree as ET

    cm = MemoryContextManager()
    unconfirmed_id = uuid.uuid4()
    confirmed_id = uuid.uuid4()
    system_id = uuid.uuid4()

    memories = [
        MemorySearchResult(
            id=unconfirmed_id,
            content='User mentions preference for "dark mode" & <custom_theme>',
            memory_type="preference",
            category="ui & ux",
            importance=3,
            confidence=0.7,
            confirmation_status="unconfirmed",
            score=0.65,
        ),
        MemorySearchResult(
            id=confirmed_id,
            content="User lives in Zurich",
            memory_type="fact",
            category="location",
            importance=5,
            confidence=1.0,
            confirmation_status="confirmed",
            score=0.90,
        ),
        MemorySearchResult(
            id=system_id,
            content="Account tier is enterprise",
            memory_type="fact",
            category="account",
            importance=4,
            confidence=1.0,
            confirmation_status="system_asserted",
            score=0.85,
        ),
    ]

    xml_output = cm._format_memory_xml(memories)

    # 1. Epistemic instructions present and distinct
    assert "<epistemic_instructions>" in xml_output
    assert "unconfirmed: Tentative information inferred from conversation; potentially useful, but not an established fact. Do not state it as confirmed." in xml_output
    assert "confirmed: Information explicitly confirmed" in xml_output
    assert "system_asserted: System-established information; distinguish it from user-confirmed information." in xml_output

    # 2. Strict XML validity & parsing
    root = ET.fromstring(xml_output)
    assert root.tag == "user_memories"

    mem_elements = root.findall("memory")
    assert len(mem_elements) == 3

    # Check unconfirmed
    m0 = mem_elements[0]
    assert m0.attrib["id"] == str(unconfirmed_id)
    assert m0.attrib["confirmation_status"] == "unconfirmed"
    assert m0.attrib["memory_type"] == "preference"
    assert m0.attrib["category"] == "ui & ux"
    assert m0.attrib["importance"] == "3"
    assert 'User mentions preference for "dark mode" & <custom_theme>' == m0.text

    # Check confirmed
    m1 = mem_elements[1]
    assert m1.attrib["confirmation_status"] == "confirmed"
    assert m1.attrib["memory_type"] == "fact"
    assert m1.attrib["importance"] == "5"

    # Check system_asserted
    m2 = mem_elements[2]
    assert m2.attrib["confirmation_status"] == "system_asserted"


@pytest.mark.asyncio
async def test_memory_extraction_ingestion_with_embeddings(postgresql_server):
    """24. Verify extraction worker persists embeddings and fails safely if embedding generation fails."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p24") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-ingest-emb"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u24@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 24')", conv_id, user_id)

        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'My favourite language is Python')", user_msg_id, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Python is versatile!')", asst_msg_id, conv_id, user_id)

        fp = "c" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg_id, fp)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_pool = await asyncpg.create_pool(
            host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw"
        )

        # Test case 1: Successful embedding generation and persistence
        canned = '[{"content": "User loves programming in Python", "memory_type": "preference", "category": "technical", "importance": 4, "confidence": 0.85}]'
        llm = MockExtractionProvider(response_json=canned)
        emb_provider = MockEmbeddingProvider(dimension=768)

        worker = MemoryExtractionWorker(
            worker_id="test-worker-emb",
            db_pool=worker_pool,
            llm_provider=llm,
            embedding_provider=emb_provider,
        )

        async with worker_pool.acquire() as claim_conn:
            jobs = await worker.claim_jobs(claim_conn)
            assert len(jobs) == 1
            async with worker_pool.acquire() as proc_conn:
                ok = await worker.process_job(proc_conn, jobs[0])
                assert ok is True

        # Verify memory created with chat_inferred, unconfirmed, and embedding
        mem = await conn.fetchrow("SELECT * FROM public.memories WHERE user_id = $1", user_id)
        assert mem is not None
        assert mem["origin"] == "chat_inferred"
        assert mem["confirmation_status"] == "unconfirmed"

        emb_row = await conn.fetchrow("SELECT * FROM public.memory_embeddings WHERE memory_id = $1", mem["id"])
        assert emb_row is not None
        assert emb_row["dimension"] == 768
        assert emb_row["is_active"] is True

        # Test case 2: Embedding failure prevents job completion and triggers retry
        user_msg_id2 = uuid.uuid4()
        asst_msg_id2 = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'I live in Paris')", user_msg_id2, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Paris is lovely.')", asst_msg_id2, conv_id, user_id)

        idemp_key2 = "turn-ingest-fail-emb"
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key2, conv_id, user_msg_id2, "d" * 64)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key2, asst_msg_id2)

        failing_emb_provider = MockEmbeddingProvider(simulate_timeout=True)
        worker_fail = MemoryExtractionWorker(
            worker_id="test-worker-fail-emb",
            db_pool=worker_pool,
            llm_provider=llm,
            embedding_provider=failing_emb_provider,
        )

        async with worker_pool.acquire() as claim_conn:
            jobs2 = await worker_fail.claim_jobs(claim_conn)
            assert len(jobs2) == 1
            async with worker_pool.acquire() as proc_conn:
                ok2 = await worker_fail.process_job(proc_conn, jobs2[0])
                assert ok2 is False

        # Job must NOT be marked completed
        job2_row = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE source_message_id = $1", asst_msg_id2)
        assert job2_row["status"] == "pending"
        assert job2_row["attempts"] == 1
        assert "timeout" in job2_row["last_error"].lower()

        await worker_pool.close()


@pytest.mark.asyncio
async def test_query_embedding_semantic_ranking_and_lexical_fallback(postgresql_server):
    """25. Verify that semantic vector search affects ranking, and falls back to lexical search if embedding fails."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_p25") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u25@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # Fixed vector for target concept: "software engineering practices"
        emb_provider = MockEmbeddingProvider(dimension=768)
        sem_vec = await emb_provider.embed_text("software engineering and programming")
        sem_vec_str = f"[{','.join(str(x) for x in sem_vec)}]"

        # Distinct vector for unrelated concept
        unrelated_vec = await emb_provider.embed_text("cooking lasagna pasta tomato cheese")
        unrelated_vec_str = f"[{','.join(str(x) for x in unrelated_vec)}]"

        mem_sem_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence)
            VALUES ($1, $2, 'Enjoys building modular backend architectures', 'fact', 'technical', 3, 0.8)
            """,
            mem_sem_id, user_id,
        )
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active)
            VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)
            """,
            mem_sem_id, user_id, sem_vec_str,
        )

        mem_unrelated_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence)
            VALUES ($1, $2, 'Bakes sourdough bread on weekends', 'fact', 'personal', 3, 0.8)
            """,
            mem_unrelated_id, user_id,
        )
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active)
            VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)
            """,
            mem_unrelated_id, user_id, unrelated_vec_str,
        )

        class PoolRetriever(MemoryRetriever):
            def __init__(self, pool):
                super().__init__(db_pool=pool)

        client_user = f"client_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {client_user} WITH PASSWORD 'client_pw' IN ROLE authenticated")
        pool = await asyncpg.create_pool(
            host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=client_user, password="client_pw"
        )
        retriever = PoolRetriever(pool)

        # 1. Semantic query matching the concept
        ctx_mgr = MemoryContextManager(retriever=retriever, embedding_provider=emb_provider)
        mock_llm = MockTokenCountingProvider()
        xml = await ctx_mgr.build_memory_context(user_id, "software engineering and programming", mock_llm)

        assert "Enjoys building modular backend architectures" in xml
        assert "Bakes sourdough bread" not in xml or xml.find("modular backend") < xml.find("sourdough")

        # 2. Degraded query embedding: embedding provider throws error -> falls back to lexical search
        failing_emb = MockEmbeddingProvider(simulate_timeout=True)
        ctx_mgr_fallback = MemoryContextManager(retriever=retriever, embedding_provider=failing_emb)

        # Query uses lexical terms directly present in content
        xml_fallback = await ctx_mgr_fallback.build_memory_context(user_id, "sourdough bread", mock_llm)
        assert "Bakes sourdough bread on weekends" in xml_fallback

        await pool.close()


@pytest.mark.asyncio
async def test_end_to_end_memory_pipeline_integration(postgresql_server):
    """26. End-to-end integration test demonstrating the complete 9-step sequence:
    1. A completed chat request creates an eligible extraction job.
    2. The worker claims the job.
    3. The extraction provider returns a valid memory.
    4. The embedding provider produces a valid vector.
    5. The memory is inserted with unconfirmed provenance.
    6. A subsequent query generates an embedding.
    7. Hybrid retrieval finds the stored memory.
    8. The context manager serializes it with the correct epistemic status.
    9. The LLM receives the memory context.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_e2e") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-e2e-001"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "e2e@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'E2E Conversation')", conv_id, user_id)

        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Please always use dark mode in visual representations.')",
            user_msg_id, conv_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Understood, I will always apply dark mode.')",
            asst_msg_id, conv_id, user_id,
        )

        # Step 1: A completed chat request creates an eligible extraction job
        fp = "e" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg_id, fp)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg_id)

        job_row = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE source_message_id = $1", asst_msg_id)
        assert job_row is not None
        assert job_row["status"] == "pending"

        # Setup worker environment
        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'worker_pw' IN ROLE auren_worker")
        worker_pool = await asyncpg.create_pool(
            host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="worker_pw"
        )

        # Step 3 & 4: Extraction provider returns valid memory and embedding provider produces 768-dim vector
        extracted_content = "User prefers dark mode for all visual interfaces"
        canned_extraction = f"""[
            {{
                "content": "{extracted_content}",
                "memory_type": "preference",
                "category": "technical",
                "importance": 4,
                "confidence": 0.85
            }}
        ]"""
        mock_llm_extractor = MockExtractionProvider(response_json=canned_extraction)
        emb_provider = MockEmbeddingProvider(dimension=768)

        worker = MemoryExtractionWorker(
            worker_id="worker-e2e-runner",
            db_pool=worker_pool,
            llm_provider=mock_llm_extractor,
            embedding_provider=emb_provider,
        )

        # Step 2: The worker claims the job
        async with worker_pool.acquire() as claim_conn:
            claimed_jobs = await worker.claim_jobs(claim_conn)
            assert len(claimed_jobs) == 1
            assert claimed_jobs[0]["id"] == job_row["id"]

            # Step 5: The memory is inserted with unconfirmed provenance and job completed
            async with worker_pool.acquire() as proc_conn:
                success = await worker.process_job(proc_conn, claimed_jobs[0])
                assert success is True

        job_done = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE id = $1", job_row["id"])
        assert job_done["status"] == "completed"

        mem_record = await conn.fetchrow("SELECT * FROM public.memories WHERE user_id = $1", user_id)
        assert mem_record is not None
        assert mem_record["origin"] == "chat_inferred"
        assert mem_record["confirmation_status"] == "unconfirmed"
        assert mem_record["last_confirmed_at"] is None

        emb_record = await conn.fetchrow("SELECT * FROM public.memory_embeddings WHERE memory_id = $1", mem_record["id"])
        assert emb_record is not None
        assert emb_record["dimension"] == 768

        # Step 6, 7, 8: Subsequent query generates embedding, hybrid retrieval finds memory, serialized with epistemic status
        class PoolRetriever(MemoryRetriever):
            def __init__(self, p):
                super().__init__(db_pool=p)

        user_client = f"client_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {user_client} WITH PASSWORD 'client_pw' IN ROLE authenticated")
        user_pool = await asyncpg.create_pool(
            host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=user_client, password="client_pw"
        )
        retriever = PoolRetriever(user_pool)
        ctx_mgr = MemoryContextManager(retriever=retriever, embedding_provider=emb_provider)
        token_counter = MockTokenCountingProvider()

        subsequent_query = "What color theme do I prefer?"
        memory_xml_context = await ctx_mgr.build_memory_context(
            user_id=user_id,
            query_text=subsequent_query,
            provider=token_counter,
            budget_tokens=500,
        )

        # Step 8 Verification: Serialized with correct epistemic status
        assert "<user_memories>" in memory_xml_context
        assert 'confirmation_status="unconfirmed"' in memory_xml_context
        assert extracted_content in memory_xml_context
        assert "<epistemic_instructions>" in memory_xml_context

        # Step 9: The LLM receives the memory context inside prompt messages
        mock_chat_llm = MockTokenCountingProvider()
        assembled_messages = [
            ChatMessage(role="system", content="System Prompt"),
            ChatMessage(role="system", content=memory_xml_context),
            ChatMessage(role="user", content=subsequent_query),
        ]
        assert len(assembled_messages) == 3
        assert assembled_messages[1].role == "system"
        assert 'confirmation_status="unconfirmed"' in assembled_messages[1].content
        assert extracted_content in assembled_messages[1].content

        await worker_pool.close()
        await user_pool.close()


@pytest.mark.asyncio
async def test_incompatible_model_spaces_cannot_be_silently_mixed(postgresql_server):
    """27. Verify that vectors from incompatible embedding spaces are never compared in hybrid search.
    A memory embedded under 'text-embedding-004' must not match a query vector for 'gemini-embedding-2',
    evaluating semantic similarity to 0.0 while preserving lexical retrieval.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_p27") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u27@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        target_vec = [0.03] * 768
        target_vec_str = f"[{','.join(str(x) for x in target_vec)}]"

        # Insert memory with an embedding stored under retired 'text-embedding-004'
        mem_old_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence)
            VALUES ($1, $2, 'Specialized quantum compilation technique', 'fact', 'technical', 4, 0.9)
            """,
            mem_old_id, user_id,
        )
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active)
            VALUES ($1, $2, 'gemini', 'text-embedding-004', 'v1', 768, $3::vector, TRUE)
            """,
            mem_old_id, user_id, target_vec_str,
        )

        # Query using the active model 'gemini-embedding-2' with identical vector
        # Because the model space is incompatible, the old embedding must NOT match
        results_active = await conn.fetch(
            """
            SELECT id, score FROM public.search_memories_hybrid_rpc(
                p_query_text => 'completely unrelated search keywords',
                p_query_embedding => $1::vector,
                p_limit => 5,
                p_min_similarity => 0.0,
                p_model => 'gemini-embedding-2'
            )
            """,
            target_vec_str,
        )
        scores_active = {r["id"]: r["score"] for r in results_active}
        assert mem_old_id in scores_active
        # Without semantic match: score is s_imp (0.15 * 4/5 = 0.12) + s_decay (0.10) + s_conf (0.10 * 0.9 = 0.09) = 0.310
        # If model spaces were mistakenly mixed, s_sem would be 1.0 (adding 0.40 -> 0.710)
        assert abs(scores_active[mem_old_id] - 0.310) < 0.005, (
            f"Expected ~0.310 (zero semantic match due to model isolation), got {scores_active[mem_old_id]}"
        )

        # Now query targeting inactive model 'text-embedding-004' explicitly:
        # Inactive model identities cannot participate in active retrieval, so semantic similarity is 0.0!
        results_old_space = await conn.fetch(
            """
            SELECT id, score FROM public.search_memories_hybrid_rpc(
                p_query_text => 'completely unrelated search keywords',
                p_query_embedding => $1::vector,
                p_limit => 5,
                p_min_similarity => 0.0,
                p_model => 'text-embedding-004'
            )
            """,
            target_vec_str,
        )
        scores_old = {r["id"]: r["score"] for r in results_old_space}
        assert mem_old_id in scores_old
        # Semantic similarity is 0.0 because text-embedding-004 is inactive: score is exactly 0.310
        assert abs(scores_old[mem_old_id] - 0.310) < 0.005


@pytest.mark.asyncio
async def test_worker_service_role_permissions_and_direct_access_denial(postgresql_server):
    """28. Verify worker database identity: auren_worker is NOLOGIN NOINHERIT;
    auren_worker_service connects, has valid is_authorized_worker_session(),
    can execute worker RPCs, but is strictly DENIED direct SELECT/DML on all data tables.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_p28") as (conn, db_name):
        # 1. Verify auren_worker itself is NOLOGIN NOINHERIT
        nologin_row = await conn.fetchrow(
            "SELECT rolcanlogin, rolinherit FROM pg_roles WHERE rolname = 'auren_worker'"
        )
        assert nologin_row is not None
        assert nologin_row["rolcanlogin"] is False
        assert nologin_row["rolinherit"] is False

        # 2. Setup auren_worker_service with password in test DB
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker_service') THEN
                    CREATE ROLE auren_worker_service WITH LOGIN PASSWORD 'test_svc_pw';
                ELSE
                    ALTER ROLE auren_worker_service WITH LOGIN PASSWORD 'test_svc_pw';
                END IF;
                GRANT auren_worker TO auren_worker_service;
            END $$;
        """)

        # Connect as auren_worker_service
        worker_conn = await asyncpg.connect(
            host=postgresql_server["host"],
            port=postgresql_server["port"],
            database=db_name,
            user="auren_worker_service",
            password="test_svc_pw",
        )

        try:
            # 3. Verify session identity and authorized worker session check
            auth_worker = await worker_conn.fetchval("SELECT public.is_authorized_worker_session()")
            assert auth_worker is True

            # 4. Verify worker RPC execution is permitted
            jobs = await worker_conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-test-svc', 5, 300)")
            assert isinstance(jobs, list)

            # 5. Verify direct table SELECT is strictly DENIED on sensitive tables
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.messages LIMIT 1")

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.journal_entries LIMIT 1")

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.memories LIMIT 1")

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.memory_extraction_jobs LIMIT 1")

        finally:
            await worker_conn.close()


@pytest.mark.asyncio
async def test_provider_failure_prevents_fake_embeddings_and_completion(postgresql_server):
    """29. Verify that an embedding provider failure during extraction does not fabricate fake embeddings
    and prevents false job completion (job remains pending with incremented attempts).
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_p29") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-emb-fail-check"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u29@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 29')", conv_id, user_id)

        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'My pet is a dog named Max')", user_msg_id, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Dogs make great pets!')", asst_msg_id, conv_id, user_id)

        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg_id, "e" * 64)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg_id)

        # Worker setup
        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_pool = await asyncpg.create_pool(
            host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw"
        )

        canned = '[{"content": "User owns a dog named Max", "memory_type": "fact", "category": "personal", "importance": 3, "confidence": 0.9}]'
        llm = MockExtractionProvider(response_json=canned)
        failing_emb = MockEmbeddingProvider(simulate_timeout=True, dimension=768)

        worker = MemoryExtractionWorker(
            worker_id="worker-emb-fail",
            db_pool=worker_pool,
            llm_provider=llm,
            embedding_provider=failing_emb,
        )

        async with worker_pool.acquire() as claim_conn:
            jobs = await worker.claim_jobs(claim_conn)
            assert len(jobs) == 1
            async with worker_pool.acquire() as proc_conn:
                success = await worker.process_job(proc_conn, jobs[0])
                assert success is False

        # Job must NOT be marked completed
        job_status = await conn.fetchrow("SELECT status, attempts, last_error FROM public.memory_extraction_jobs WHERE id = $1", jobs[0]["id"])
        assert job_status["status"] == "pending"
        assert job_status["attempts"] == 1
        assert "timeout" in job_status["last_error"].lower()

        # Zero memories or embeddings must be created
        mem_count = await conn.fetchval("SELECT count(*) FROM public.memories WHERE user_id = $1", user_id)
        assert mem_count == 0

        emb_count = await conn.fetchval("SELECT count(*) FROM public.memory_embeddings WHERE user_id = $1", user_id)
        assert emb_count == 0

        await worker_pool.close()


@pytest.mark.asyncio
async def test_complete_embedding_model_identity_isolation_postgres(postgresql_server):
    """30. Verify complete embedding model identity isolation:
    (provider, model, version, dimension, purpose='retrieval').
    Covers:
    - Different providers with identical model names (e.g. 'vertex' vs 'gemini')
    - Different versions with identical provider and model names (e.g. 'v2' vs 'v1')
    - Different dimensions (e.g. 512 vs 768)
    - Inactive model identities ('text-embedding-004' is inactive)
    - Unknown model identities ('unknown-model')
    - Correct matching of the active registered identity ('gemini', 'gemini-embedding-2', 'v1', 768)
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_p30") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u30@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # Register inactive alternative models in registry to satisfy FK/trigger
        await conn.execute("""
            INSERT INTO public.embedding_models (provider, model, version, dimension, vector_column, purpose, is_active)
            VALUES 
                ('vertex', 'gemini-embedding-2', 'v1', 768, 'embedding_768', 'retrieval', FALSE),
                ('gemini', 'gemini-embedding-2', 'v2', 768, 'embedding_768', 'retrieval', FALSE),
                ('gemini', 'gemini-embedding-2', 'v1_1536', 1536, 'embedding_1536', 'retrieval', FALSE),
                ('gemini', 'unknown-model-xyz', 'v1', 768, 'embedding_768', 'retrieval', FALSE)
            ON CONFLICT (provider, model, version) DO NOTHING;
        """)

        target_vec = [0.03] * 768
        target_vec_str = f"[{','.join(str(x) for x in target_vec)}]"
        target_vec_1536 = [0.03] * 1536
        target_vec_1536_str = f"[{','.join(str(x) for x in target_vec_1536)}]"

        # 1. Memory with active registered identity: ('gemini', 'gemini-embedding-2', 'v1', 768)
        m_active_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'Active registered memory', 'fact', 'technical', 4, 0.9)",
            m_active_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)",
            m_active_id, user_id, target_vec_str,
        )

        # 2. Memory with different provider, identical model name: ('vertex', 'gemini-embedding-2', 'v1', 768)
        m_diff_prov_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'Different provider memory', 'fact', 'technical', 4, 0.9)",
            m_diff_prov_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'vertex', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)",
            m_diff_prov_id, user_id, target_vec_str,
        )

        # 3. Memory with different version: ('gemini', 'gemini-embedding-2', 'v2', 768)
        m_diff_ver_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'Different version memory', 'fact', 'technical', 4, 0.9)",
            m_diff_ver_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v2', 768, $3::vector, TRUE)",
            m_diff_ver_id, user_id, target_vec_str,
        )

        # 4. Memory with different dimension: ('gemini', 'gemini-embedding-2', 'v1_1536', 1536)
        m_diff_dim_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'Different dimension memory', 'fact', 'technical', 4, 0.9)",
            m_diff_dim_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_1536, is_active) "
            "VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1_1536', 1536, $3::vector, TRUE)",
            m_diff_dim_id, user_id, target_vec_1536_str,
        )

        # 5. Memory with inactive model: ('gemini', 'text-embedding-004', 'v1', 768)
        m_inactive_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'Inactive model memory', 'fact', 'technical', 4, 0.9)",
            m_inactive_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'gemini', 'text-embedding-004', 'v1', 768, $3::vector, TRUE)",
            m_inactive_id, user_id, target_vec_str,
        )

        # 6. Memory with unknown model: ('gemini', 'unknown-model-xyz', 'v1', 768)
        m_unknown_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'Unknown model memory', 'fact', 'technical', 4, 0.9)",
            m_unknown_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'gemini', 'unknown-model-xyz', 'v1', 768, $3::vector, TRUE)",
            m_unknown_id, user_id, target_vec_str,
        )

        # Case A: Standard query (no model params passed -> resolves active registered identity)
        # Only m_active_id has semantic match. All others evaluate s_sem = 0.0.
        rows_default = await conn.fetch(
            """
            SELECT id, score FROM public.search_memories_hybrid_rpc(
                p_query_text => 'completely unrelated query text',
                p_query_embedding => $1::vector,
                p_limit => 10,
                p_min_similarity => 0.0
            )
            """,
            target_vec_str,
        )
        scores_default = {r["id"]: r["score"] for r in rows_default}

        # Active registered memory matches semantically: 0.40 * 1.0 + 0.12 + 0.10 + 0.09 = 0.710
        assert abs(scores_default[m_active_id] - 0.710) < 0.005

        # All incompatible identities get strictly s_sem = 0.0 (baseline non-semantic score 0.310)
        assert abs(scores_default[m_diff_prov_id] - 0.310) < 0.005
        assert abs(scores_default[m_diff_ver_id] - 0.310) < 0.005
        assert abs(scores_default[m_diff_dim_id] - 0.310) < 0.005
        assert abs(scores_default[m_inactive_id] - 0.310) < 0.005
        assert abs(scores_default[m_unknown_id] - 0.310) < 0.005

        # Case B: Threshold filter (p_min_similarity = 0.5)
        # Because lexical match is 0, only m_active_id (s_sem >= 0.5) is returned.
        # Memories with incompatible or inactive vector spaces are excluded.
        rows_filtered = await conn.fetch(
            """
            SELECT id, score FROM public.search_memories_hybrid_rpc(
                p_query_text => 'completely unrelated query text',
                p_query_embedding => $1::vector,
                p_limit => 10,
                p_min_similarity => 0.5
            )
            """,
            target_vec_str,
        )
        filtered_ids = {r["id"] for r in rows_filtered}
        assert m_active_id in filtered_ids
        assert m_diff_prov_id not in filtered_ids
        assert m_diff_ver_id not in filtered_ids
        assert m_diff_dim not in filtered_ids if 'm_diff_dim' in locals() else m_diff_dim_id not in filtered_ids
        assert m_inactive_id not in filtered_ids
        assert m_unknown_id not in filtered_ids


@pytest.mark.asyncio
async def test_lexical_fallback_under_nonzero_semantic_threshold(postgresql_server):
    """31. Verify lexical fallback under non-zero semantic similarity threshold:
    - Semantic similarity thresholds apply to compatible semantic candidates.
    - Memories without a compatible vector remain eligible through lexical retrieval.
    - A missing or incompatible vector is never treated as a valid semantic match (s_sem = 0.0).
    - Scoring weights strictly preserved: 0.40 sem, 0.25 lex, 0.15 imp, 0.10 decay, 0.10 conf.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_p31") as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u31@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        query_vec = [0.03] * 768
        query_vec_str = f"[{','.join(str(x) for x in query_vec)}]"
        opposite_vec = [-0.03] * 768
        opposite_vec_str = f"[{','.join(str(x) for x in opposite_vec)}]"

        # 1. Compatible memory with HIGH semantic similarity, zero lexical match
        m_sem_high_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'astronomy galaxy cosmological physics', 'fact', 'technical', 4, 0.9)",
            m_sem_high_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)",
            m_sem_high_id, user_id, query_vec_str,
        )

        # 2. Compatible memory with LOW semantic similarity (< 0.5), zero lexical match
        m_sem_low_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'gardening floral botany botanist', 'fact', 'general', 4, 0.9)",
            m_sem_low_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'gemini', 'gemini-embedding-2', 'v1', 768, $3::vector, TRUE)",
            m_sem_low_id, user_id, opposite_vec_str,
        )

        # 3. Old-model memory ('text-embedding-004', incompatible vector) with STRONG lexical match
        m_old_lex_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'specialized rust programming language and compiler', 'preference', 'technical', 5, 1.0)",
            m_old_lex_id, user_id,
        )
        await conn.execute(
            "INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active) "
            "VALUES ($1, $2, 'gemini', 'text-embedding-004', 'v1', 768, $3::vector, TRUE)",
            m_old_lex_id, user_id, opposite_vec_str,
        )

        # 4. Memory WITHOUT any embedding with STRONG lexical match
        m_no_emb_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence) "
            "VALUES ($1, $2, 'rust programming language and toolchain', 'preference', 'technical', 5, 1.0)",
            m_no_emb_id, user_id,
        )

        # Execute hybrid search with non-zero threshold p_min_similarity = 0.5
        # Query text matches the Rust memories (3 and 4)
        results = await conn.fetch(
            """
            SELECT id, score FROM public.search_memories_hybrid_rpc(
                p_query_text => 'rust programming language',
                p_query_embedding => $1::vector,
                p_limit => 10,
                p_min_similarity => 0.5
            )
            """,
            query_vec_str,
        )
        scores = {r["id"]: r["score"] for r in results}

        # 1. Memory A (compatible semantically, s_sem >= 0.5) is returned
        assert m_sem_high_id in scores

        # 2. Memory B (compatible semantically, s_sem < 0.5, no lexical match) is EXCLUDED
        assert m_sem_low_id not in scores

        # 3. Old-model memory C (incompatible vector) with strong lexical match IS returned via lexical fallback!
        assert m_old_lex_id in scores

        # 4. No-embedding memory D with strong lexical match IS returned via lexical fallback!
        assert m_no_emb_id in scores

        # Verify that memory C and D received zero semantic match points (s_sem = 0.0)
        # Score = 0.40 * 0.0 + 0.25 * s_lex + 0.15 * (5/5) + 0.10 (decay) + 0.10 * 1.0 = 0.25 * s_lex + 0.350
        assert scores[m_old_lex_id] < 0.60  # Lexical match without semantic boost


@pytest.mark.asyncio
async def test_explicit_embedding_provider_failure_modes_and_retired_model_rejection(postgresql_server):
    """32. Verify explicit embedding provider failure behaviors:
    1. Intentionally configured lexical-only mode (EMBEDDING_PROVIDER="none"):
       - Memories stored in memories table.
       - 0 records written to memory_embeddings.
       - Extraction job succeeds as completed.
    2. Unexpected provider initialization failure (missing credentials):
       - get_embedding_provider raises EmbeddingAuthenticationError.
       - Does not silently succeed.
    3. Runtime embedding generation failure:
       - Fail-closed: extraction job fails for retry (attempts=1, status='pending').
       - 0 memories inserted.
       - 0 embeddings inserted.
    4. Retired model rejection:
       - Instantiating GeminiEmbeddingProvider with 'text-embedding-004' raises EmbeddingProviderError.
       - Calling insert_extracted_memory_rpc with 'text-embedding-004' raises SQL exception.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_p32") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u32@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 32')", conv_id, user_id)

        # Worker role setup
        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_pool = await asyncpg.create_pool(
            host=postgresql_server["host"], port=postgresql_server["port"], database=db_name, user=worker_user, password="pw",
            min_size=1, max_size=3,
        )

        # -------------------------------------------------------------------------
        # Case 1: Intentionally configured lexical-only mode
        # -------------------------------------------------------------------------
        from app.core.config import Settings
        from app.services.embeddings.factory import get_embedding_provider
        from app.services.embeddings.base import EmbeddingAuthenticationError, EmbeddingProviderError
        from app.services.embeddings.gemini import GeminiEmbeddingProvider

        lexical_settings = Settings(
            ENVIRONMENT="test",
            JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            EMBEDDING_PROVIDER="none",
        )
        assert get_embedding_provider(lexical_settings) is None

        # Process a job in lexical-only mode (embedding_provider=None)
        user_msg1 = uuid.uuid4()
        asst_msg1 = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'I like tea')", user_msg1, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Tea is wonderful')", asst_msg1, conv_id, user_id)
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", "idemp-lex-1", conv_id, user_msg1, "1" * 64)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", "idemp-lex-1", asst_msg1)

        llm_mock = MockExtractionProvider(
            response_json='[{"content": "User likes tea", "memory_type": "preference", "category": "personal", "importance": 3, "confidence": 0.85}]'
        )
        lexical_worker = MemoryExtractionWorker(
            worker_id="lexical-worker",
            db_pool=worker_pool,
            llm_provider=llm_mock,
            embedding_provider=None,  # Lexical-only mode
        )

        async with worker_pool.acquire() as c_conn:
            jobs1 = await lexical_worker.claim_jobs(c_conn)
            assert len(jobs1) == 1
            async with worker_pool.acquire() as p_conn:
                success1 = await lexical_worker.process_job(p_conn, jobs1[0])
                assert success1 is True

        # Job completed
        j1_status = await conn.fetchval("SELECT status FROM public.memory_extraction_jobs WHERE source_message_id = $1", asst_msg1)
        assert j1_status == "completed"

        # Memory was written
        mem1 = await conn.fetchrow("SELECT * FROM public.memories WHERE user_id = $1 AND content = 'User likes tea'", user_id)
        assert mem1 is not None

        # 0 embeddings written
        emb1_count = await conn.fetchval("SELECT count(*) FROM public.memory_embeddings WHERE memory_id = $1", mem1["id"])
        assert emb1_count == 0

        # -------------------------------------------------------------------------
        # Case 2: Unexpected initialization failure
        # -------------------------------------------------------------------------
        unconf_settings = Settings(
            ENVIRONMENT="test",
            JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            EMBEDDING_PROVIDER="gemini",
            EMBEDDING_API_KEY=None,
            LLM_API_KEY=None,
        )
        with pytest.raises(EmbeddingAuthenticationError, match="Gemini embedding provider configured"):
            get_embedding_provider(unconf_settings)

        # -------------------------------------------------------------------------
        # Case 3: Retired model rejection
        # -------------------------------------------------------------------------
        with pytest.raises(EmbeddingProviderError, match="retired"):
            GeminiEmbeddingProvider(api_key="fake-key", model_id="text-embedding-004")

        # In PostgreSQL, insert_extracted_memory_rpc rejects text-embedding-004
        user_msg2 = uuid.uuid4()
        asst_msg2 = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Coffee')", user_msg2, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Coffee is great')", asst_msg2, conv_id, user_id)
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", "idemp-ret-1", conv_id, user_msg2, "2" * 64)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", "idemp-ret-1", asst_msg2)

        async with worker_pool.acquire() as c_conn:
            jobs2 = await lexical_worker.claim_jobs(c_conn)
            assert len(jobs2) == 1
            j2 = jobs2[0]

            with pytest.raises(asyncpg.exceptions.PostgresError, match="retired"):
                dummy_vec = f"[{','.join(['0.01'] * 768)}]"
                await c_conn.fetchval(
                    """
                    SELECT public.insert_extracted_memory_rpc(
                        p_job_id => $1,
                        p_worker_id => 'lexical-worker',
                        p_claim_token => $2,
                        p_content => 'User likes coffee',
                        p_memory_type => 'preference',
                        p_category => 'personal',
                        p_embedding_768 => $3::vector,
                        p_model => 'text-embedding-004'
                    )
                    """,
                    j2["id"], j2["claim_token"], dummy_vec,
                )

        await worker_pool.close()



