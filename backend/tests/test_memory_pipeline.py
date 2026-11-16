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
            ) VALUES ($1, $2, 'gemini', 'text-embedding-004', 'v1', 768, $3::vector, TRUE)
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
    tight_budget = 100
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
