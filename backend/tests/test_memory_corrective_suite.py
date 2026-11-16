"""Tests for Phase 3C.3 Corrective Milestone:
1. SEC-01: Dedicated PostgreSQL RPCs restore_memory_rpc and outdate_memory_rpc with RLS and ownership enforcement.
2. DATA-01: SQLite memory correction TOCTOU concurrency safety, multi-hop audit lineage, and atomicity.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import glob
from pathlib import Path
import tempfile
import uuid
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.services.memory.sqlite_repository import SQLiteMemoryRepository
from app.services.memory.supabase_repository import SupabaseMemoryRepository
from app.models.memory import MemoryModel

PG_SOCK_DIR = Path("/tmp/auren_pg_sock")
PG_PORT = 54329
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations"

MOCK_AUTH_SQL = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE TABLE IF NOT EXISTS auth.users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email TEXT,
        raw_user_meta_data JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS UUID AS $$
        SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::UUID;
    $$ LANGUAGE sql STABLE;
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN CREATE ROLE postgres NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker') THEN CREATE ROLE auren_worker NOLOGIN NOINHERIT; END IF;
    END $$;
"""


@pytest.fixture(scope="session")
def postgresql_server():
    """Local PostgreSQL server for real database verification."""
    return {"host": str(PG_SOCK_DIR), "port": PG_PORT}


@asynccontextmanager
async def isolated_postgres_db(server_info, prefix="auren_corr_test"):
    """Create an isolated test database with all 18 migrations applied."""
    db_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin_conn = await asyncpg.connect(
        host=server_info["host"],
        port=server_info["port"],
        database="postgres",
    )
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    conn = await asyncpg.connect(
        host=server_info["host"],
        port=server_info["port"],
        database=db_name,
    )
    try:
        await conn.execute(MOCK_AUTH_SQL)
        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611*.sql")))
        assert len(migration_files) >= 18, f"Expected at least 18 migrations, found {len(migration_files)}"
        for mf in migration_files:
            sql = Path(mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        yield conn, db_name
    finally:
        try:
            await conn.close()
        except Exception:
            pass
        admin_conn = await asyncpg.connect(
            host=server_info["host"],
            port=server_info["port"],
            database="postgres",
        )
        try:
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            await admin_conn.close()


# ============================================================================
# 1. PostgreSQL RPC Verification (SEC-01)
# ============================================================================

@pytest.mark.asyncio
async def test_postgresql_restore_and_outdate_rpcs_security_and_rls(postgresql_server):
    """Verifies that migration 018 introduces restore_memory_rpc and outdate_memory_rpc:
    - Authenticated owner can restore archived/expired memory
    - Authenticated owner can outdate active memory
    - Cross-user modifications are rejected
    - Unauthenticated callers are rejected
    - Invalid lifecycle transitions are rejected
    - Direct table UPDATE on public.memories remains denied to authenticated role under RLS
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_rpc_test") as (conn, db_name):
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        # Seed auth.users
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, 'a@example.com'), ($2, 'b@example.com')", user_a, user_b)

        # Create active memory for User A via create_memory_rpc
        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")
        mem_id_a = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content := 'User A core preference: prefers dark mode.',
                p_memory_type := 'preference',
                p_category := 'general',
                p_importance := 3
            )
            """
        )
        assert mem_id_a is not None

        # 1. Test outdate_memory_rpc as User A
        res_outdate = await conn.fetchval("SELECT public.outdate_memory_rpc($1)", mem_id_a)
        assert res_outdate is True

        row = await conn.fetchrow("SELECT lifecycle_status FROM public.memories WHERE id = $1", mem_id_a)
        assert row["lifecycle_status"] == "expired"

        # Outdating an already expired memory must fail
        with pytest.raises(asyncpg.PostgresError) as exc_info:
            await conn.fetchval("SELECT public.outdate_memory_rpc($1)", mem_id_a)
        assert "Cannot outdate memory with lifecycle status: expired" in str(exc_info.value)

        # 2. Test restore_memory_rpc as User A (expired -> active)
        res_restore = await conn.fetchval("SELECT public.restore_memory_rpc($1)", mem_id_a)
        assert res_restore is True

        row = await conn.fetchrow("SELECT lifecycle_status FROM public.memories WHERE id = $1", mem_id_a)
        assert row["lifecycle_status"] == "active"

        # Restoring an already active memory must fail
        with pytest.raises(asyncpg.PostgresError) as exc_info:
            await conn.fetchval("SELECT public.restore_memory_rpc($1)", mem_id_a)
        assert "Cannot restore memory with lifecycle status: active" in str(exc_info.value)

        # 3. Test archive -> restore flow
        await conn.fetchval("SELECT public.archive_memory_rpc($1)", mem_id_a)
        row = await conn.fetchrow("SELECT lifecycle_status FROM public.memories WHERE id = $1", mem_id_a)
        assert row["lifecycle_status"] == "archived"

        res_restore_arch = await conn.fetchval("SELECT public.restore_memory_rpc($1)", mem_id_a)
        assert res_restore_arch is True
        row = await conn.fetchrow("SELECT lifecycle_status FROM public.memories WHERE id = $1", mem_id_a)
        assert row["lifecycle_status"] == "active"

        # 4. Cross-user isolation: User B cannot outdate or restore User A's memory
        await conn.execute(f"SET request.jwt.claim.sub = '{user_b}'")
        with pytest.raises(asyncpg.PostgresError) as exc_info:
            await conn.fetchval("SELECT public.outdate_memory_rpc($1)", mem_id_a)
        assert "Memory not found or access denied" in str(exc_info.value)

        with pytest.raises(asyncpg.PostgresError) as exc_info:
            await conn.fetchval("SELECT public.restore_memory_rpc($1)", mem_id_a)
        assert "Memory not found or access denied" in str(exc_info.value)

        # 5. Unauthenticated rejection
        await conn.execute("RESET request.jwt.claim.sub")
        with pytest.raises(asyncpg.PostgresError) as exc_info:
            await conn.fetchval("SELECT public.outdate_memory_rpc($1)", mem_id_a)
        assert "Unauthorized: authenticated session required" in str(exc_info.value)

        # 6. Direct UPDATE access check: authenticated role cannot UPDATE memories table directly
        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")
        await conn.execute("SET ROLE authenticated")
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError) as exc_priv:
                await conn.execute("UPDATE public.memories SET lifecycle_status = 'expired' WHERE id = $1", mem_id_a)
            assert "permission denied for table memories" in str(exc_priv.value).lower()
        finally:
            await conn.execute("RESET ROLE")

        # 7. Role execution privilege verification
        # anon cannot EXECUTE restore_memory_rpc
        await conn.execute("SET ROLE anon")
        try:
            with pytest.raises(asyncpg.PostgresError) as exc_info:
                await conn.fetchval("SELECT public.restore_memory_rpc($1)", mem_id_a)
            assert "permission denied" in str(exc_info.value).lower()
        finally:
            await conn.execute("RESET ROLE")


# ============================================================================
# 2. SQLite Concurrency & Lineage Verification (DATA-01)
# ============================================================================

@pytest.fixture
def temp_sqlite_repo():
    """Create an ephemeral SQLite memory repository with isolated DB file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_memory_corr.db"
        repo = SQLiteMemoryRepository(db_path=db_path)
        yield repo


@pytest.mark.asyncio
async def test_sqlite_concurrent_corrections_toctou_prevention(temp_sqlite_repo):
    """Demonstrate that BEGIN IMMEDIATE serializes concurrent correction attempts:
    - When two concurrent tasks race to correct the same active memory:
    - Exactly one task succeeds, producing a superseded predecessor and a new active memory.
    - The losing task fails cleanly with ValueError('Cannot correct memory with lifecycle status: superseded').
    - Zero orphaned records or duplicate active replacements exist.
    """
    user_id = uuid4()
    original_mem = await temp_sqlite_repo.create_memory(
        user_id=user_id,
        content="Original statement before race: User loves green tea.",
        memory_type="preference",
        category="personal",
        importance=3,
    )
    assert original_mem.lifecycle_status == "active"

    # Define two competing correction tasks
    async def attempt_correction(new_content: str):
        try:
            return await temp_sqlite_repo.correct_memory(
                user_id=user_id,
                memory_id=original_mem.id,
                content=new_content,
            )
        except ValueError as e:
            return e

    # Launch both simultaneously
    results = await asyncio.gather(
        attempt_correction("Race correction 1: User prefers black coffee."),
        attempt_correction("Race correction 2: User prefers herbal chamomile."),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, MemoryModel)]
    failures = [r for r in results if isinstance(r, ValueError)]

    # Exactly one succeeded and one failed
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}"
    assert "Cannot correct memory with lifecycle status: superseded" in str(failures[0])

    # Verify database state
    predecessor = await temp_sqlite_repo.get_memory(user_id, original_mem.id)
    assert predecessor.lifecycle_status == "superseded"
    assert predecessor.superseded_by_id == successes[0].id

    # Verify only one replacement is active
    successor = await temp_sqlite_repo.get_memory(user_id, successes[0].id)
    assert successor.lifecycle_status == "active"
    assert successor.previous_version_id == original_mem.id
    assert successor.root_memory_id == original_mem.id


@pytest.mark.asyncio
async def test_sqlite_multi_hop_successive_corrections(temp_sqlite_repo):
    """Verify that multi-hop corrections preserve the entire version tree:
    Generation 1: Memory A (root)
    Generation 2: Memory B (previous=A, root=A, A.superseded_by=B)
    Generation 3: Memory C (previous=B, root=A, B.superseded_by=C)
    """
    user_id = uuid4()

    # Gen 1
    mem_a = await temp_sqlite_repo.create_memory(
        user_id=user_id,
        content="Gen 1: User lives in Seattle.",
        memory_type="fact",
        category="personal",
        importance=3,
    )
    assert mem_a.root_memory_id == mem_a.id  # Root points to self as root ancestor

    # Gen 2 (Correct A -> B)
    mem_b = await temp_sqlite_repo.correct_memory(
        user_id=user_id,
        memory_id=mem_a.id,
        content="Gen 2: User moved to Austin.",
    )
    assert mem_b.previous_version_id == mem_a.id
    assert mem_b.root_memory_id == mem_a.id
    assert mem_b.lifecycle_status == "active"

    # Check Gen 1 is superseded
    check_a = await temp_sqlite_repo.get_memory(user_id, mem_a.id)
    assert check_a.lifecycle_status == "superseded"
    assert check_a.superseded_by_id == mem_b.id

    # Gen 3 (Correct B -> C)
    mem_c = await temp_sqlite_repo.correct_memory(
        user_id=user_id,
        memory_id=mem_b.id,
        content="Gen 3: User relocated to New York.",
    )
    assert mem_c.previous_version_id == mem_b.id
    assert mem_c.root_memory_id == mem_a.id  # Root propagates from earliest ancestor
    assert mem_c.lifecycle_status == "active"

    # Check Gen 2 is now superseded
    check_b = await temp_sqlite_repo.get_memory(user_id, mem_b.id)
    assert check_b.lifecycle_status == "superseded"
    assert check_b.superseded_by_id == mem_c.id
    assert check_b.previous_version_id == mem_a.id
    assert check_b.root_memory_id == mem_a.id


@pytest.mark.asyncio
async def test_sqlite_cross_user_correction_rejection(temp_sqlite_repo):
    """User B cannot correct User A's memory."""
    user_a = uuid4()
    user_b = uuid4()

    mem_a = await temp_sqlite_repo.create_memory(
        user_id=user_a,
        content="User A private note.",
    )

    # User B attempts to correct User A's memory
    result = await temp_sqlite_repo.correct_memory(
        user_id=user_b,
        memory_id=mem_a.id,
        content="Malicious overwrite by User B.",
    )
    # Must return None (mapped to 404 in API layer)
    assert result is None

    # Verify User A's memory remains active and unchanged
    unchanged = await temp_sqlite_repo.get_memory(user_a, mem_a.id)
    assert unchanged.lifecycle_status == "active"
    assert unchanged.content == "User A private note."
    assert unchanged.superseded_by_id is None


@pytest.mark.asyncio
async def test_sqlite_failed_correction_rollback_atomicity(temp_sqlite_repo):
    """When a correction encounters an invalid status or error, transaction rolls back with zero partial writes."""
    user_id = uuid4()
    mem = await temp_sqlite_repo.create_memory(
        user_id=user_id,
        content="Stable state fact.",
    )

    # 1. Archive memory so it is ineligible for correction
    await temp_sqlite_repo.archive_memory(user_id, mem.id)

    # 2. Attempt correction - should fail with ValueError
    with pytest.raises(ValueError) as exc_info:
        await temp_sqlite_repo.correct_memory(
            user_id=user_id,
            memory_id=mem.id,
            content="Attempted correction of archived memory.",
        )
    assert "Cannot correct memory with lifecycle status: archived" in str(exc_info.value)

    # 3. Verify predecessor remained archived, not superseded, no replacement created
    items, total = await temp_sqlite_repo.list_memories(user_id=user_id, lifecycle_status="active")
    assert total == 0  # No active memories created

    archived_mem = await temp_sqlite_repo.get_memory(user_id, mem.id)
    assert archived_mem.lifecycle_status == "archived"
    assert archived_mem.superseded_by_id is None
