"""Test suite for background memory extraction worker runner and concurrency orchestration."""

import asyncio
import uuid
import asyncpg
import pytest

from app.core.config import Settings
from app.services.embeddings.factory import MockEmbeddingProvider
from app.services.llm.base import BaseLLMProvider, ChatMessage, LLMResponse
from app.services.memory.runner import WorkerRunner
from tests.test_memory_database import isolated_postgres_db, postgresql_server


class MockExtractionProvider(BaseLLMProvider):
    def __init__(self, response_json: str = "[]", fail: bool = False):
        self.response_json = response_json
        self.fail = fail

    def get_model_id(self) -> str:
        return "mock-extraction"

    async def generate_response(self, messages, **kwargs) -> LLMResponse:
        if self.fail:
            raise RuntimeError("Simulated LLM extraction model failure")
        return LLMResponse(content=self.response_json, model=self.get_model_id())

    async def stream_response(self, messages, **kwargs):
        yield self.response_json


@pytest.mark.asyncio
async def test_worker_runner_claim_and_process_lifecycle(postgresql_server):
    """Verify that WorkerRunner discovers, claims, extracts, embeds, and completes a job end-to-end."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_runner1") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-runner-success"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u1@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 1')", conv_id, user_id)

        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'I love Neovim and Rust')", user_msg_id, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Both are great developer tools!')", asst_msg_id, conv_id, user_id)

        # Complete chat request via RPC (atomic outbox enqueueing)
        fp = "a" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg_id, fp)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg_id)

        # Verify job is pending
        job_before = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE source_message_id = $1", asst_msg_id)
        assert job_before is not None
        assert job_before["status"] == "pending"

        # Create dedicated worker database user
        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'secret' IN ROLE auren_worker")

        worker_pool = await asyncpg.create_pool(
            host=postgresql_server["host"],
            port=postgresql_server["port"],
            database=db_name,
            user=worker_user,
            password="secret",
            min_size=1,
            max_size=3,
        )

        canned_extraction = """[
            {
                "content": "User prefers Neovim and Rust for development",
                "memory_type": "preference",
                "category": "technical",
                "importance": 4,
                "confidence": 0.9
            }
        ]"""
        llm = MockExtractionProvider(response_json=canned_extraction)
        emb = MockEmbeddingProvider(dimension=768)

        runner = WorkerRunner(
            worker_id="runner-unit-test",
            db_pool=worker_pool,
            llm_provider=llm,
            embedding_provider=emb,
            poll_interval=0.1,
            batch_size=5,
            lease_seconds=60,
            concurrency=2,
        )

        # Run single polling cycle
        await runner.initialize()
        async with worker_pool.acquire() as claim_conn:
            jobs = await runner._worker.claim_jobs(claim_conn)
            assert len(jobs) == 1
            for j in jobs:
                async with worker_pool.acquire() as proc_conn:
                    success = await runner._worker.process_job(proc_conn, j)
                    assert success is True

        # Verify job state in database
        job_after = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE id = $1", job_before["id"])
        assert job_after["status"] == "completed"
        assert job_after["locked_by"] is None
        assert job_after["lease_expires_at"] is None
        assert job_after["claim_token"] != job_before["claim_token"]

        # Verify memory persisted with unconfirmed status and 768-dim vector embedding
        mem = await conn.fetchrow("SELECT * FROM public.memories WHERE user_id = $1", user_id)
        assert mem is not None
        assert mem["content"] == "User prefers Neovim and Rust for development"
        assert mem["origin"] == "chat_inferred"
        assert mem["confirmation_status"] == "unconfirmed"
        assert mem["last_confirmed_at"] is None

        # Verify vector embedding was stored in memory_embeddings
        emb_row = await conn.fetchrow("SELECT * FROM public.memory_embeddings WHERE memory_id = $1", mem["id"])
        assert emb_row is not None
        assert emb_row["dimension"] == 768
        assert emb_row["embedding_768"] is not None

        await worker_pool.close()


@pytest.mark.asyncio
async def test_worker_runner_transient_failure_and_retry(postgresql_server):
    """Verify that transient extraction failure increments attempts and reschedules without falsely completing."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_runner2") as (conn, db_name):
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        idemp_key = "turn-runner-fail"

        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "u2@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv 2')", conv_id, user_id)

        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Hello')", user_msg_id, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Hi')", asst_msg_id, conv_id, user_id)

        fp = "b" * 64
        await conn.execute("SELECT public.claim_chat_request($1, $2, $3, $4)", idemp_key, conv_id, user_msg_id, fp)
        await conn.execute("SELECT public.complete_chat_request($1, $2)", idemp_key, asst_msg_id)

        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'secret' IN ROLE auren_worker")

        worker_pool = await asyncpg.create_pool(
            host=postgresql_server["host"],
            port=postgresql_server["port"],
            database=db_name,
            user=worker_user,
            password="secret",
            min_size=1,
            max_size=3,
        )

        # LLM that fails
        llm_failing = MockExtractionProvider(fail=True)
        runner = WorkerRunner(
            worker_id="runner-fail-test",
            db_pool=worker_pool,
            llm_provider=llm_failing,
            poll_interval=0.1,
            batch_size=5,
            lease_seconds=60,
        )
        await runner.initialize()

        async with worker_pool.acquire() as claim_conn:
            jobs = await runner._worker.claim_jobs(claim_conn)
            assert len(jobs) == 1
            async with worker_pool.acquire() as proc_conn:
                success = await runner._worker.process_job(proc_conn, jobs[0])
                assert success is False

        # Job must NOT be completed; must be pending for retry with attempts = 1
        job_after = await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE source_message_id = $1", asst_msg_id)
        assert job_after["status"] == "pending"
        assert job_after["attempts"] == 1
        assert "Simulated LLM extraction" in job_after["last_error"]
        assert job_after["locked_by"] is None

        # Zero memories created
        mems = await conn.fetch("SELECT * FROM public.memories WHERE user_id = $1", user_id)
        assert len(mems) == 0

        await worker_pool.close()


@pytest.mark.asyncio
async def test_worker_runner_graceful_shutdown(postgresql_server):
    """Verify that calling runner.stop() cleanly terminates the polling loop."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_runner3") as (conn, db_name):
        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD 'secret' IN ROLE auren_worker")

        worker_pool = await asyncpg.create_pool(
            host=postgresql_server["host"],
            port=postgresql_server["port"],
            database=db_name,
            user=worker_user,
            password="secret",
            min_size=1,
            max_size=2,
        )

        runner = WorkerRunner(
            worker_id="runner-shutdown-test",
            db_pool=worker_pool,
            llm_provider=MockExtractionProvider(),
            poll_interval=0.05,
        )

        run_task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.15)
        assert runner.is_running is True

        # Request stop
        runner.stop()
        await asyncio.wait_for(run_task, timeout=2.0)
        assert runner.is_running is False
        assert runner.metrics["poll_cycles"] > 0

        await worker_pool.close()
