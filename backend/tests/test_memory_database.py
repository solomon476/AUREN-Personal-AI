"""Real PostgreSQL integration tests verifying the foundational memory database schema,

security policies, lifecycle transitions, lineage integrity, vector embeddings table,
single-use journal consent ledger, and extraction job queue.
"""

from contextlib import asynccontextmanager
import glob
from pathlib import Path
import uuid

import asyncpg
import pytest

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
    END $$;
"""


@pytest.fixture(scope="session")
def postgresql_server():
    """Ensure local PostgreSQL server is running for actual database-level testing."""
    return {"host": str(PG_SOCK_DIR), "port": PG_PORT}


@asynccontextmanager
async def isolated_postgres_db(server_info, prefix="auren_mem_test", apply_all_migrations=True):
    """Context manager creating a uniquely named ephemeral database for each test,

    guaranteeing complete isolation and robust cleanup with DROP DATABASE ... WITH (FORCE).
    """
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
        if apply_all_migrations:
            migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611*.sql")))
            assert len(migration_files) >= 11, f"Expected at least 11 migration files, found {len(migration_files)}"
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


@pytest.mark.asyncio
async def test_fresh_migration_001_through_011(postgresql_server):
    """Execute complete migration sequence 001 through 011 and verify all memory tables and indexes exist."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_fresh", apply_all_migrations=True) as (conn, db_name):
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        table_names = {t["table_name"] for t in tables}

        assert "memories" in table_names
        assert "memory_embeddings" in table_names
        assert "embedding_models" in table_names
        assert "consumed_consent_tokens" in table_names
        assert "memory_extraction_jobs" in table_names

        # Verify vector columns on memory_embeddings
        cols = await conn.fetch("SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_name = 'memory_embeddings'")
        col_map = {c["column_name"]: c["udt_name"] for c in cols}
        assert "embedding_768" in col_map
        assert "embedding_1536" in col_map
        assert col_map["embedding_768"] == "vector"
        assert col_map["embedding_1536"] == "vector"

        # Verify HNSW indexes exist
        indexes = await conn.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'memory_embeddings'")
        idx_names = {idx["indexname"] for idx in indexes}
        assert "idx_memory_embeddings_768_hnsw" in idx_names
        assert "idx_memory_embeddings_1536_hnsw" in idx_names


@pytest.mark.asyncio
async def test_legacy_memory_records_migration_and_preservation(postgresql_server):
    """Verify that existing legacy memory records are preserved and mapped accurately during migration 011."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_legacy", apply_all_migrations=False) as (conn, db_name):
        # Apply 001 through 010 first
        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611*.sql")))
        for mf in migration_files:
            if "011_" in mf:
                continue
            sql = Path(mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        # Setup legacy user
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "legacy@example.com")

        # Insert legacy records across all 5 legacy categories
        legacy_data = [
            ("Legacy fact content", "fact", 4),
            ("Legacy preference content", "preference", 5),
            ("Legacy work content", "work", 3),
            ("Legacy personal content", "personal", 2),
            ("Legacy general content", "general", 1),
        ]
        legacy_ids = []
        for content, cat, imp in legacy_data:
            mid = await conn.fetchval(
                """
                INSERT INTO public.memories (user_id, content, category, importance)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                user_id, content, cat, imp,
            )
            legacy_ids.append((mid, cat))

        # Now execute Migration 011
        sql011 = Path([mf for mf in migration_files if "011_" in mf][0]).read_text(encoding="utf-8")
        await conn.execute(sql011)

        # Assert all 5 legacy records survived with exact conservative mappings
        for mid, old_cat in legacy_ids:
            row = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", mid)
            assert row is not None
            assert row["root_memory_id"] == mid
            assert row["confirmation_status"] == "confirmed"
            assert row["lifecycle_status"] == "active"
            assert row["confidence"] == 1.0
            assert row["origin"] == "explicit_user_statement"

            if old_cat == "preference":
                assert row["memory_type"] == "preference"
                assert row["category"] == "general"
            elif old_cat == "fact":
                assert row["memory_type"] == "fact"
                assert row["category"] == "general"
            elif old_cat == "work":
                assert row["memory_type"] == "fact"
                assert row["category"] == "work"
            elif old_cat == "personal":
                assert row["memory_type"] == "fact"
                assert row["category"] == "personal"
            elif old_cat == "general":
                assert row["memory_type"] == "fact"
                assert row["category"] == "general"


@pytest.mark.asyncio
async def test_memory_ownership_isolation(postgresql_server):
    """Verify that User A cannot read, mutate, or supersede User B's memories."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_iso", apply_all_migrations=True) as (conn, db_name):
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_a, "user_a@example.com")
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_b, "user_b@example.com")

        # Act as User A to create a memory
        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")
        mem_a = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'User A secret fact',
                p_memory_type => 'fact',
                p_category => 'personal'
            )
            """
        )
        assert mem_a is not None

        # Switch to User B
        await conn.execute(f"SET request.jwt.claim.sub = '{user_b}'")
        await conn.execute("SET ROLE authenticated")

        # 1. User B direct SELECT cannot see User A's memory
        rows = await conn.fetch("SELECT * FROM public.memories")
        assert len(rows) == 0

        # 2. User B cannot supersede User A's memory
        with pytest.raises(asyncpg.exceptions.NoDataFoundError):
            await conn.execute(
                """
                SELECT public.supersede_memory_rpc(
                    p_old_memory_id => $1,
                    p_new_content => 'Tampered content'
                )
                """,
                mem_a,
            )

        # 3. User B cannot delete User A's memory
        with pytest.raises(asyncpg.exceptions.NoDataFoundError):
            await conn.execute("SELECT public.delete_memory_rpc($1)", mem_a)

        # 4. User B cannot confirm User A's memory
        with pytest.raises(asyncpg.exceptions.NoDataFoundError):
            await conn.execute("SELECT public.confirm_memory_rpc($1)", mem_a)

        await conn.execute("RESET ROLE")


@pytest.mark.asyncio
async def test_direct_client_mutation_rejection(postgresql_server):
    """Verify that direct INSERT, UPDATE, and DELETE operations are rejected by database privileges."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_priv", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "test@example.com")

        # Direct INSERT on memories rejected
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(
                """
                SET ROLE authenticated;
                INSERT INTO public.memories (user_id, content, memory_type, category)
                VALUES ('11111111-1111-1111-1111-111111111111', 'Direct insert', 'fact', 'personal');
                """
            )
        await conn.execute("RESET ROLE")

        # Create memory via RPC as superuser/service
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        mem_id = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'Pristine memory',
                p_memory_type => 'fact',
                p_category => 'personal'
            )
            """
        )

        # Direct UPDATE on memories rejected
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(
                f"""
                SET ROLE authenticated;
                UPDATE public.memories SET content = 'Tampered' WHERE id = '{mem_id}';
                """
            )
        await conn.execute("RESET ROLE")

        # Direct DELETE on memories rejected
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(
                f"""
                SET ROLE authenticated;
                DELETE FROM public.memories WHERE id = '{mem_id}';
                """
            )
        await conn.execute("RESET ROLE")


@pytest.mark.asyncio
async def test_rpc_authorization_and_unauthenticated_rejection(postgresql_server):
    """Verify that calling RPC functions without an authenticated JWT claim raises 42501 Unauthorized."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_auth", apply_all_migrations=True) as (conn, db_name):
        # Reset JWT claim to None
        await conn.execute("RESET request.jwt.claim.sub")

        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="Unauthorized: authenticated session required"):
            await conn.execute(
                """
                SELECT public.create_memory_rpc(
                    p_content => 'Unauthenticated attempt',
                    p_memory_type => 'fact',
                    p_category => 'personal'
                )
                """
            )


@pytest.mark.asyncio
async def test_supersession_and_lineage_integrity(postgresql_server):
    """Verify that supersession updates predecessor to 'superseded', links pointers, and maintains root lineage."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_lineage", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "lineage@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # Step 1: Create Memory 1 (Version 1)
        m1_id = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'Lives in Seattle',
                p_memory_type => 'fact',
                p_category => 'personal'
            )
            """
        )

        # Step 2: Supersede M1 with Memory 2 (Version 2)
        m2_id = await conn.fetchval(
            """
            SELECT public.supersede_memory_rpc(
                p_old_memory_id => $1,
                p_new_content => 'Lives in London'
            )
            """,
            m1_id,
        )

        # Verify M1 is superseded and points forward to M2
        m1 = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", m1_id)
        assert m1["lifecycle_status"] == "superseded"
        assert m1["superseded_by_id"] == m2_id
        assert m1["root_memory_id"] == m1_id

        # Verify M2 is active and points backward to M1
        m2 = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", m2_id)
        assert m2["lifecycle_status"] == "active"
        assert m2["previous_version_id"] == m1_id
        assert m2["root_memory_id"] == m1_id

        # Step 3: Supersede M2 with Memory 3 (Version 3)
        m3_id = await conn.fetchval(
            """
            SELECT public.supersede_memory_rpc(
                p_old_memory_id => $1,
                p_new_content => 'Lives in Tokyo'
            )
            """,
            m2_id,
        )

        # Verify unbroken lineage
        m3 = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", m3_id)
        assert m3["lifecycle_status"] == "active"
        assert m3["previous_version_id"] == m2_id
        assert m3["root_memory_id"] == m1_id

        # Verify active retrieval filter returns ONLY M3
        active_memories = await conn.fetch(
            "SELECT id, content FROM public.memories WHERE user_id = $1 AND lifecycle_status = 'active'",
            user_id,
        )
        assert len(active_memories) == 1
        assert active_memories[0]["id"] == m3_id
        assert active_memories[0]["content"] == "Lives in Tokyo"

        # Attempting to supersede M1 again must be rejected because M1 is already superseded
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Cannot supersede memory with lifecycle status: superseded"):
            await conn.execute(
                """
                SELECT public.supersede_memory_rpc(
                    p_old_memory_id => $1,
                    p_new_content => 'Invalid supersede on already superseded'
                )
                """,
                m1_id,
            )


@pytest.mark.asyncio
async def test_embedding_ownership_and_uniqueness(postgresql_server):
    """Verify that memory_embeddings enforces model uniqueness and cascades on memory deletion."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_vec", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "vector@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        mem_id = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'Vector test fact',
                p_memory_type => 'fact',
                p_category => 'technical'
            )
            """
        )

        # Store 768-dim embedding (Gemini text-embedding-004)
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (
                memory_id, user_id, provider, model, version, dimension, embedding_768
            ) VALUES (
                $1, $2, 'gemini', 'text-embedding-004', 'v1', 768, (SELECT array_agg(0.01::float4)::vector(768) FROM generate_series(1, 768))
            )
            """,
            mem_id, user_id,
        )

        # Attempting duplicate embedding for same model raises unique violation
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO public.memory_embeddings (
                    memory_id, user_id, provider, model, version, dimension, embedding_768
                ) VALUES (
                    $1, $2, 'gemini', 'text-embedding-004', 'v1', 768, (SELECT array_agg(0.02::float4)::vector(768) FROM generate_series(1, 768))
                )
                """,
                mem_id, user_id,
            )

        # Storing a different model embedding (OpenAI text-embedding-3-small, 1536 dims) succeeds side-by-side
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (
                memory_id, user_id, provider, model, version, dimension, embedding_1536
            ) VALUES (
                $1, $2, 'openai', 'text-embedding-3-small', 'v1', 1536, (SELECT array_agg(0.01::float4)::vector(1536) FROM generate_series(1, 1536))
            )
            """,
            mem_id, user_id,
        )

        count = await conn.fetchval("SELECT count(*) FROM public.memory_embeddings WHERE memory_id = $1", mem_id)
        assert count == 2

        # Deleting memory cascades to delete both embeddings
        await conn.execute("SELECT public.delete_memory_rpc($1)", mem_id)
        count_after = await conn.fetchval("SELECT count(*) FROM public.memory_embeddings WHERE memory_id = $1", mem_id)
        assert count_after == 0


@pytest.mark.asyncio
async def test_single_use_journal_consent_and_replay_prevention(postgresql_server):
    """Verify that consume_journal_consent_rpc enforces single-use consumption and rejects replayed nonces."""
    async with isolated_postgres_db(postgresql_server, prefix="mem_consent", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "consent@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Consent Conv')", conv_id, user_id)
        nonce = uuid.uuid4()

        # First consumption succeeds
        res = await conn.fetchval(
            """
            SELECT public.consume_journal_consent_rpc(
                p_nonce => $1,
                p_conversation_id => $2,
                p_idempotency_key => 'idemp-key-1',
                p_scope => 'journal:read',
                p_expires_at => now() + INTERVAL '60 seconds'
            )
            """,
            nonce, conv_id,
        )
        assert res is True

        # Replaying exact same nonce triggers unique violation
        with pytest.raises(asyncpg.exceptions.UniqueViolationError, match="Consent token has already been consumed"):
            await conn.execute(
                """
                SELECT public.consume_journal_consent_rpc(
                    p_nonce => $1,
                    p_conversation_id => $2,
                    p_idempotency_key => 'idemp-key-1',
                    p_scope => 'journal:read',
                    p_expires_at => now() + INTERVAL '60 seconds'
                )
                """,
                nonce, conv_id,
            )

        # Consuming an expired token raises exception
        expired_nonce = uuid.uuid4()
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Consent token has expired"):
            await conn.execute(
                """
                SELECT public.consume_journal_consent_rpc(
                    p_nonce => $1,
                    p_conversation_id => $2,
                    p_idempotency_key => 'idemp-key-2',
                    p_scope => 'journal:read',
                    p_expires_at => now() - INTERVAL '10 seconds'
                )
                """,
                expired_nonce, conv_id,
            )


@pytest.mark.asyncio
async def test_cascading_deletion_and_purge_all(postgresql_server):
    """Verify that source-message deletion sets source_message_id to NULL on memories,

    cascades on extraction jobs, and purge_all_memories_rpc completely purges user memory data.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_purge", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "purge@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Purge Conv')", conv_id, user_id)
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'My dog Barnaby')", msg_id, conv_id, user_id)

        # Create memory referencing message
        mem_id = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'Has a dog Barnaby',
                p_memory_type => 'fact',
                p_category => 'personal',
                p_source_message_id => $1,
                p_source_conversation_id => $2
            )
            """,
            msg_id, conv_id,
        )

        # Create extraction job referencing message
        job_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memory_extraction_jobs (id, user_id, conversation_id, source_message_id)
            VALUES ($1, $2, $3, $4)
            """,
            job_id, user_id, conv_id, msg_id,
        )

        # Delete message
        await conn.execute("DELETE FROM public.messages WHERE id = $1", msg_id)

        # Assert extraction job was deleted (ON DELETE CASCADE)
        assert await conn.fetchrow("SELECT * FROM public.memory_extraction_jobs WHERE id = $1", job_id) is None

        # Assert memory still exists, but source_message_id is now NULL (ON DELETE SET NULL)
        mem = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", mem_id)
        assert mem is not None
        assert mem["source_message_id"] is None
        assert mem["content"] == "Has a dog Barnaby"

        # Now test purge_all_memories_rpc
        purged_count = await conn.fetchval("SELECT public.purge_all_memories_rpc()")
        assert purged_count == 1
        assert await conn.fetchval("SELECT count(*) FROM public.memories WHERE user_id = $1", user_id) == 0
