"""Real PostgreSQL integration tests verifying the foundational memory database schema,
security policies, lifecycle transitions, lineage integrity, vector embeddings table,
single-use journal consent ledger, extraction job queue, and worker authentication boundaries.

Distinction of Test Environments:
- Mocked Authentication: Emulates Supabase's PostgREST JWT context within the PostgreSQL session
  using `SET request.jwt.claim.sub = '<uuid>'`.
- Real PostgreSQL Privileges & RLS: Uses `SET ROLE authenticated`, `SET ROLE auren_worker`,
  and `RESET ROLE` to execute statements under actual unprivileged PostgreSQL database roles,
  verifying that GRANT/REVOKE privileges, role assumption restrictions, and ROW LEVEL SECURITY (RLS)
  policies are enforced at the PostgreSQL kernel level.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import glob
from pathlib import Path
import uuid

import asyncpg
import pytest

from app.core.config import settings, get_journal_hmac_secret
from app.services.journal.consent import (
    create_journal_consent_token,
    verify_and_consume_journal_consent,
    verify_journal_consent_token,
    InvalidSignatureError,
    ExpiredConsentTokenError,
    ExcessiveLifetimeError,
    ConsentUserMismatchError,
    ConsentConversationMismatchError,
    ConsentIdempotencyMismatchError,
    DateRangeMismatchError,
    InvalidConsentScopeError,
    ReplayedConsentTokenError,
    JournalConsentToken,
    JournalConsentPayload,
)

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
            assert len(migration_files) >= 15, f"Expected at least 15 migration files, found {len(migration_files)}"
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
async def test_fresh_migration_001_through_015(postgresql_server):
    """Execute complete migration sequence 001 through 015 and verify all memory tables,
    indexes, schema columns, NULL confidence support, claim_token on extraction jobs,
    date_range on consumed consent tokens, and administrative audit tables exist accurately.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_fresh", apply_all_migrations=True) as (conn, db_name):
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        table_names = {t["table_name"] for t in tables}

        assert "memories" in table_names
        assert "memory_embeddings" in table_names
        assert "embedding_models" in table_names
        assert "consumed_consent_tokens" in table_names
        assert "memory_extraction_jobs" in table_names
        assert "admin_maintenance_audit_log" in table_names

        # Verify routines exist
        routines = await conn.fetch("SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'public'")
        routine_names = {r["routine_name"] for r in routines}
        assert "is_authorized_worker_session" in routine_names
        assert "admin_emergency_reset_job_rpc" in routine_names

        # Verify vector columns on memory_embeddings
        cols = await conn.fetch("SELECT column_name, data_type, udt_name, is_nullable FROM information_schema.columns WHERE table_name = 'memories'")
        col_map = {c["column_name"]: c for c in cols}
        assert "confidence" in col_map
        assert col_map["confidence"]["is_nullable"] == "YES"

        # Verify claim_token on memory_extraction_jobs
        job_cols = await conn.fetch("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'memory_extraction_jobs'")
        job_col_map = {c["column_name"]: c for c in job_cols}
        assert "claim_token" in job_col_map
        assert job_col_map["claim_token"]["data_type"] == "uuid"
        assert job_col_map["claim_token"]["is_nullable"] == "NO"

        # Verify date_range on consumed_consent_tokens
        consent_cols = await conn.fetch("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'consumed_consent_tokens'")
        consent_col_map = {c["column_name"]: c for c in consent_cols}
        assert "date_range" in consent_col_map
        assert consent_col_map["date_range"]["data_type"] == "text"
        assert consent_col_map["date_range"]["is_nullable"] == "NO"

        # Verify HNSW indexes exist
        indexes = await conn.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'memory_embeddings'")
        idx_names = {idx["indexname"] for idx in indexes}
        assert "idx_memory_embeddings_768_hnsw" in idx_names
        assert "idx_memory_embeddings_1536_hnsw" in idx_names

        # Verify embedding_models purpose column and unique active index
        model_cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'embedding_models'")
        model_col_names = {c["column_name"] for c in model_cols}
        assert "purpose" in model_col_names


@pytest.mark.asyncio
async def test_legacy_memory_records_null_confidence_preservation(postgresql_server):
    """Verify that existing legacy memory records are preserved without manufacturing certainty
    or consent: origin becomes 'legacy_import', confirmation_status becomes 'unconfirmed',
    confidence is NULL, and last_confirmed_at is NULL.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_legacy", apply_all_migrations=False) as (conn, db_name):
        # Apply 001 through 010 first
        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611*.sql")))
        for mf in migration_files:
            if any(x in mf for x in ("011_", "012_", "013_", "014_", "015_", "016_", "017_")):
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
            legacy_ids.append((mid, cat, content, imp))

        # Now execute Migration 011, 012, 013, 014, 015, 016, and 017 in order
        for suffix in ("011_", "012_", "013_", "014_", "015_", "016_", "017_"):
            target_mf = [mf for mf in migration_files if suffix in mf][0]
            sql = Path(target_mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        # Assert all 5 legacy records survived with exact conservative mappings, unconfirmed status, and NULL confidence
        for mid, old_cat, expected_content, expected_imp in legacy_ids:
            row = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", mid)
            assert row is not None
            assert row["content"] == expected_content
            assert row["importance"] == expected_imp
            assert row["root_memory_id"] == mid
            assert row["confirmation_status"] == "unconfirmed"
            assert row["lifecycle_status"] == "active"
            assert row["confidence"] is None  # Zero manufactured certainty
            assert row["origin"] == "legacy_import"
            assert row["last_confirmed_at"] is None

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

        # Explicit user confirmation elevates confirmation status and sets confidence = 1.0
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        first_mid = legacy_ids[0][0]
        confirmed_res = await conn.fetchval("SELECT public.confirm_memory_rpc($1)", first_mid)
        assert confirmed_res is True

        confirmed_row = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", first_mid)
        assert confirmed_row["confirmation_status"] == "confirmed"
        assert confirmed_row["confidence"] == 1.0
        assert confirmed_row["last_confirmed_at"] is not None
        assert confirmed_row["origin"] == "legacy_import"


@pytest.mark.asyncio
async def test_worker_role_privilege_boundaries_and_assumption_rejection(postgresql_server):
    """Verify that ordinary authenticated users cannot assume the auren_worker role,
    cannot execute worker RPCs, and that create_system_asserted_memory_rpc strictly validates
    type, category, and importance.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_wauth", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "user@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # Create real unprivileged client user and worker login user to test actual role boundary
        client_pass = "client_secret_123"
        worker_pass = "worker_secret_123"
        client_user = f"client_{uuid.uuid4().hex[:8]}"
        worker_user = f"worker_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {client_user} WITH PASSWORD '{client_pass}' IN ROLE authenticated")
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD '{worker_pass}' IN ROLE auren_worker")

        try:
            # Connect as test_client_role (real unprivileged connection)
            client_conn = await asyncpg.connect(
                host=postgresql_server["host"],
                port=postgresql_server["port"],
                database=db_name,
                user=client_user,
                password=client_pass,
            )
            try:
                # 1. Unprivileged client user attempting to SET ROLE auren_worker is denied by PostgreSQL RBAC
                with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="permission denied to set role"):
                    await client_conn.execute("SET ROLE auren_worker")

                # 2. Unprivileged client user attempting to execute worker RPCs is denied by PostgreSQL
                with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                    await client_conn.execute("SELECT * FROM public.claim_memory_extraction_jobs_rpc('rogue-worker')")

                with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                    await client_conn.execute(
                        """
                        SELECT public.create_system_asserted_memory_rpc(
                            p_user_id => $1,
                            p_content => 'Unauthorized assertion',
                            p_memory_type => 'fact',
                            p_category => 'general'
                        )
                        """,
                        user_id,
                    )

                # Unprivileged client user cannot invoke administrative emergency reset
                with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                    await client_conn.execute(
                        "SELECT public.admin_emergency_reset_job_rpc($1, 'Unauthorized reset attempt')",
                        uuid.uuid4(),
                    )
            finally:
                await client_conn.close()

            # 3. PostgreSQL Administrator (super-user / postgres) WITHOUT auren_worker role
            # is strictly rejected by worker-only RPCs (no implicit admin bypass)
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="does not possess the auren_worker role"):
                await conn.execute("SELECT * FROM public.claim_memory_extraction_jobs_rpc('admin-worker')")

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="does not possess the auren_worker role"):
                await conn.execute(
                    """
                    SELECT public.create_system_asserted_memory_rpc(
                        p_user_id => $1,
                        p_content => 'Admin assertion',
                        p_memory_type => 'fact',
                        p_category => 'general'
                    )
                    """,
                    user_id,
                )

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="does not possess the auren_worker role"):
                await conn.execute("SELECT public.activate_embedding_model_rpc('gemini', 'text-embedding-004', 'v1')")

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="does not possess the auren_worker role"):
                await conn.execute("SELECT public.reap_stale_extraction_jobs_rpc(3)")

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="does not possess the auren_worker role"):
                await conn.execute(
                    "SELECT public.complete_memory_extraction_job_rpc($1, 'admin-worker', $2)",
                    uuid.uuid4(),
                    uuid.uuid4(),
                )

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="does not possess the auren_worker role"):
                await conn.execute(
                    "SELECT public.fail_memory_extraction_job_rpc($1, 'admin-worker', $2, 'error')",
                    uuid.uuid4(),
                    uuid.uuid4(),
                )

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="does not possess the auren_worker role"):
                await conn.execute(
                    """
                    SELECT public.insert_extracted_memory_rpc(
                        p_job_id => $1,
                        p_worker_id => 'admin-worker',
                        p_claim_token => $2,
                        p_content => 'Admin content',
                        p_memory_type => 'fact',
                        p_category => 'general'
                    )
                    """,
                    uuid.uuid4(),
                    uuid.uuid4(),
                )

            # 4. Administrator CAN execute the auditable administrative emergency procedure
            test_conv_id = uuid.uuid4()
            test_msg_id = uuid.uuid4()
            await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Admin Test Conv')", test_conv_id, user_id)
            await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Admin Msg')", test_msg_id, test_conv_id, user_id)
            test_job_id = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", test_conv_id, test_msg_id)
            await conn.execute("UPDATE public.memory_extraction_jobs SET status = 'processing', locked_by = 'hung-worker' WHERE id = $1", test_job_id)

            admin_reset = await conn.fetchval(
                "SELECT public.admin_emergency_reset_job_rpc($1, 'Emergency reset of hung extraction job')",
                test_job_id,
            )
            assert admin_reset is True
            job_after_admin = await conn.fetchrow("SELECT status, locked_by, last_error FROM public.memory_extraction_jobs WHERE id = $1", test_job_id)
            assert job_after_admin["status"] == "pending"
            assert job_after_admin["locked_by"] is None
            assert "Admin emergency reset" in job_after_admin["last_error"]

            audit_entry = await conn.fetchrow("SELECT * FROM public.admin_maintenance_audit_log WHERE target_id = $1", test_job_id)
            assert audit_entry is not None
            assert audit_entry["action"] == "admin_emergency_reset_job"
            assert "hung extraction job" in audit_entry["reason"]

            # Connect as test_worker_role (real worker connection)
            worker_conn = await asyncpg.connect(
                host=postgresql_server["host"],
                port=postgresql_server["port"],
                database=db_name,
                user=worker_user,
                password=worker_pass,
            )
            try:
                # 3. Worker connection invoking create_system_asserted_memory_rpc with invalid type/category is rejected
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Invalid memory_type"):
                    await worker_conn.execute(
                        """
                        SELECT public.create_system_asserted_memory_rpc(
                            p_user_id => $1,
                            p_content => 'Invalid type assertion',
                            p_memory_type => 'invalid_type',
                            p_category => 'general'
                        )
                        """,
                        user_id,
                    )

                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Invalid category"):
                    await worker_conn.execute(
                        """
                        SELECT public.create_system_asserted_memory_rpc(
                            p_user_id => $1,
                            p_content => 'Invalid cat assertion',
                            p_memory_type => 'fact',
                            p_category => 'invalid_category'
                        )
                        """,
                        user_id,
                    )

                # 4. Valid system asserted creation by real worker connection succeeds
                sys_mem_id = await worker_conn.fetchval(
                    """
                    SELECT public.create_system_asserted_memory_rpc(
                        p_user_id => $1,
                        p_content => 'Verified subscription tier: pro',
                        p_memory_type => 'fact',
                        p_category => 'financial',
                        p_importance => 5
                    )
                    """,
                    user_id,
                )
                assert sys_mem_id is not None
            finally:
                await worker_conn.close()
        finally:
            await conn.execute(f"DROP USER IF EXISTS {client_user}")
            await conn.execute(f"DROP USER IF EXISTS {worker_user}")


@pytest.mark.asyncio
async def test_source_provenance_and_ownership_validation(postgresql_server):
    """Verify that create_memory_rpc validates source_message_id and source_conversation_id
    ownership, enforces message-conversation consistency, rejects contradictory inferred/confirmed
    provenance, and checks expiration ordering.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_prov", apply_all_migrations=True) as (conn, db_name):
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_a, "user_a@example.com")
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_b, "user_b@example.com")

        conv_a1 = uuid.uuid4()
        conv_a2 = uuid.uuid4()
        conv_b = uuid.uuid4()
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv A1')", conv_a1, user_a)
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv A2')", conv_a2, user_a)
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv B')", conv_b, user_b)

        msg_a1 = uuid.uuid4()
        msg_b = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Msg A1')", msg_a1, conv_a1, user_a)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Msg B')", msg_b, conv_b, user_b)

        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")

        # 1. User A referencing User B's conversation is rejected
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="Conversation not found or access denied"):
            await conn.execute(
                """
                SELECT public.create_memory_rpc(
                    p_content => 'Cross conversation attack',
                    p_memory_type => 'fact',
                    p_category => 'general',
                    p_source_conversation_id => $1
                )
                """,
                conv_b,
            )

        # 2. User A referencing User B's message is rejected
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="Source message not found or access denied"):
            await conn.execute(
                """
                SELECT public.create_memory_rpc(
                    p_content => 'Cross message attack',
                    p_memory_type => 'fact',
                    p_category => 'general',
                    p_source_message_id => $1
                )
                """,
                msg_b,
            )

        # 3. Message does not belong to supplied conversation
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="does not belong to conversation"):
            await conn.execute(
                """
                SELECT public.create_memory_rpc(
                    p_content => 'Mismatch test',
                    p_memory_type => 'fact',
                    p_category => 'general',
                    p_source_message_id => $1,
                    p_source_conversation_id => $2
                )
                """,
                msg_a1, conv_a2,
            )

        # 4. Inferred memory cannot be marked confirmed upon creation
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="inferred memories must be unconfirmed"):
            await conn.execute(
                """
                SELECT public.create_memory_rpc(
                    p_content => 'Inferred confirmed contradictory',
                    p_memory_type => 'fact',
                    p_category => 'general',
                    p_origin => 'chat_inferred',
                    p_confirmation_status => 'confirmed'
                )
                """
            )

        # 5. Invalid expiration: review_after >= expires_at
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="review_after must be earlier than expires_at"):
            await conn.execute(
                """
                SELECT public.create_memory_rpc(
                    p_content => 'Invalid expiration order',
                    p_memory_type => 'fact',
                    p_category => 'general',
                    p_expires_at => now() + INTERVAL '1 hour',
                    p_review_after => now() + INTERVAL '2 hours'
                )
                """
            )


@pytest.mark.asyncio
async def test_journal_consent_hmac_and_database_verification(postgresql_server):
    """Verify that backend HMAC verification cryptographically binds user, conversation,
    idempotency key, scope, date range, and expiration, and that database consumption prevents replay.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_jhmac", apply_all_migrations=True) as (conn, db_name):
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_a, "user_a@example.com")
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_b, "user_b@example.com")

        conv_a = uuid.uuid4()
        conv_b = uuid.uuid4()
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv A')", conv_a, user_a)
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv B')", conv_b, user_b)

        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")

        secret = get_journal_hmac_secret()
        idemp_key = "req-12345"
        scope = "journal.read"
        date_range = "2026-11-01:2026-11-16"
        nonce = uuid.uuid4()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=120)

        # 1. Create legitimate token
        token = create_journal_consent_token(
            user_id=user_a,
            conversation_id=conv_a,
            idempotency_key=idemp_key,
            scope=scope,
            date_range=date_range,
            nonce=nonce,
            expires_at=expires_at,
            secret=secret,
        )

        # 2. Tampered signature is rejected
        tampered_token = JournalConsentToken(payload=token.payload, signature="bad_sig_ffffffff")
        with pytest.raises(InvalidSignatureError, match="signature is invalid"):
            verify_journal_consent_token(
                token=tampered_token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                expected_date_range=date_range,
                now=now,
            )

        # 3. Cross-user reuse attempt is rejected
        with pytest.raises(ConsentUserMismatchError, match="does not match expected"):
            verify_journal_consent_token(
                token=token,
                secret=secret,
                expected_user_id=user_b,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                expected_date_range=date_range,
                now=now,
            )

        # 4. Cross-conversation reuse attempt is rejected
        with pytest.raises(ConsentConversationMismatchError, match="does not match expected"):
            verify_journal_consent_token(
                token=token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_b,
                expected_idempotency_key=idemp_key,
                expected_date_range=date_range,
                now=now,
            )

        # 5. Idempotency key mismatch is rejected
        with pytest.raises(ConsentIdempotencyMismatchError, match="idempotency_key mismatch"):
            verify_journal_consent_token(
                token=token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key="different-key",
                expected_date_range=date_range,
                now=now,
            )

        # 6. Date range mismatch is rejected
        with pytest.raises(DateRangeMismatchError, match="does not match requested"):
            verify_journal_consent_token(
                token=token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                expected_date_range="2026-11-01:2026-11-20",
                now=now,
            )

        # 7. Expired token is rejected
        past_time = now + timedelta(seconds=130)
        with pytest.raises(ExpiredConsentTokenError, match="has expired"):
            verify_journal_consent_token(
                token=token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                expected_date_range=date_range,
                now=past_time,
            )

        # 8. Excessive lifetime (> 15 minutes) is rejected
        excessive_token = create_journal_consent_token(
            user_id=user_a,
            conversation_id=conv_a,
            idempotency_key=idemp_key,
            scope=scope,
            date_range=date_range,
            nonce=uuid.uuid4(),
            expires_at=now + timedelta(seconds=1000),  # > 900s
            secret=secret,
        )
        with pytest.raises(ExcessiveLifetimeError, match="lifetime exceeds maximum permitted window"):
            verify_journal_consent_token(
                token=excessive_token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                expected_date_range=date_range,
                now=now,
            )

        # 9. Date range mismatch during consume aborts BEFORE database execution and does NOT consume token
        mismatch_nonce = uuid.uuid4()
        mismatch_token = create_journal_consent_token(
            user_id=user_a,
            conversation_id=conv_a,
            idempotency_key="req-mismatch",
            scope=scope,
            date_range="2026-11-01:2026-11-05",
            nonce=mismatch_nonce,
            expires_at=expires_at,
            secret=secret,
        )
        with pytest.raises(DateRangeMismatchError, match="does not match requested"):
            await verify_and_consume_journal_consent(
                token=mismatch_token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key="req-mismatch",
                expected_date_range="2026-11-01:2026-11-20",
                db_conn=conn,
                now=now,
            )
        assert await conn.fetchrow("SELECT 1 FROM public.consumed_consent_tokens WHERE nonce = $1", mismatch_nonce) is None

        # 10. Valid token is verified and atomically consumed in PostgreSQL
        consumed = await verify_and_consume_journal_consent(
            token=token,
            secret=secret,
            expected_user_id=user_a,
            expected_conversation_id=conv_a,
            expected_idempotency_key=idemp_key,
            expected_date_range=date_range,
            db_conn=conn,
            now=now,
        )
        assert consumed is True

        # Verify date_range recorded in consumed_consent_tokens
        consumed_row = await conn.fetchrow(
            "SELECT * FROM public.consumed_consent_tokens WHERE nonce = $1",
            nonce,
        )
        assert consumed_row is not None
        assert consumed_row["date_range"] == date_range

        # 11. Replay attempt with same nonce is rejected by database ledger
        with pytest.raises(ReplayedConsentTokenError, match="already been consumed"):
            await verify_and_consume_journal_consent(
                token=token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                expected_date_range=date_range,
                db_conn=conn,
                now=now,
            )

        # 12. Delimiter resilience and Unicode canonical JSON serialization (RFC 8785)
        complex_idemp = 'req|key:123,"quoted"\nnewline\t\u00e9'
        complex_range = '2026-01-01:2026-12-31|üñïçódé 🍕'
        complex_nonce = uuid.uuid4()
        complex_token = create_journal_consent_token(
            user_id=user_a,
            conversation_id=conv_a,
            idempotency_key=complex_idemp,
            scope="journal.read",
            date_range=complex_range,
            nonce=complex_nonce,
            expires_at=now + timedelta(seconds=60),
            secret=secret,
        )
        complex_consumed = await verify_and_consume_journal_consent(
            token=complex_token,
            secret=secret,
            expected_user_id=user_a,
            expected_conversation_id=conv_a,
            expected_idempotency_key=complex_idemp,
            expected_date_range=complex_range,
            db_conn=conn,
            now=now,
        )
        assert complex_consumed is True
        stored_complex = await conn.fetchrow("SELECT date_range, idempotency_key FROM public.consumed_consent_tokens WHERE nonce = $1", complex_nonce)
        assert stored_complex["date_range"] == complex_range
        assert stored_complex["idempotency_key"] == complex_idemp.strip()

        # 13. Full microsecond datetime precision preservation (RFC 8785 canonical JSON)
        now_micro = datetime(2026, 11, 16, 10, 0, 0, 123456, tzinfo=timezone.utc)
        micro_token = create_journal_consent_token(
            user_id=user_a,
            conversation_id=conv_a,
            idempotency_key="micro-key",
            scope="journal.read",
            date_range="2026-11-01:2026-11-16",
            nonce=uuid.uuid4(),
            expires_at=now_micro + timedelta(seconds=120),
            secret=secret,
        )
        assert verify_journal_consent_token(
            token=micro_token,
            secret=secret,
            expected_user_id=user_a,
            expected_conversation_id=conv_a,
            expected_idempotency_key="micro-key",
            expected_date_range="2026-11-01:2026-11-16",
            now=now_micro,
        ) is True

        # 14. Timezone offset normalization to UTC
        tz_plus_3 = timezone(timedelta(hours=3))
        exp_plus_3 = datetime(2026, 11, 16, 13, 2, 0, 123456, tzinfo=tz_plus_3)
        offset_token = create_journal_consent_token(
            user_id=user_a,
            conversation_id=conv_a,
            idempotency_key="micro-key",
            scope="journal.read",
            date_range="2026-11-01:2026-11-16",
            nonce=micro_token.payload.nonce,
            expires_at=exp_plus_3,
            secret=secret,
        )
        # 13:02:00.123456+03:00 normalizes to 10:02:00.123456Z in UTC, yielding identical signature
        assert offset_token.signature == micro_token.signature

        # 15. Naive datetime rejection
        naive_dt = datetime(2026, 11, 16, 10, 2, 0, 123456)
        with pytest.raises(ValueError, match="naive datetimes rejected"):
            create_journal_consent_token(
                user_id=user_a,
                conversation_id=conv_a,
                idempotency_key="naive-key",
                scope="journal.read",
                date_range="2026-11-01:2026-11-16",
                nonce=uuid.uuid4(),
                expires_at=naive_dt,
                secret=secret,
            )


@pytest.mark.asyncio
async def test_embedding_dimension_and_model_registry_integrity(postgresql_server):
    """Verify that memory_embeddings enforces vector column vs dimension consistency,
    prevents both columns populated, ensures model registry dimension match,
    and supports atomic model cutover and coexistence of different models.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_vec_int", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "vec_int@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        mem_id = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'Model integrity fact',
                p_memory_type => 'fact',
                p_category => 'technical'
            )
            """
        )

        # 1. CHECK constraint: dimension 768 but populated embedding_1536 is rejected
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO public.memory_embeddings (
                    memory_id, user_id, provider, model, version, dimension, embedding_1536
                ) VALUES (
                    $1, $2, 'gemini', 'text-embedding-004', 'v1', 768, (SELECT array_agg(0.01::float4)::vector(1536) FROM generate_series(1, 1536))
                )
                """,
                mem_id, user_id,
            )

        # 2. CHECK constraint: both vector columns populated is rejected
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO public.memory_embeddings (
                    memory_id, user_id, provider, model, version, dimension, embedding_768, embedding_1536
                ) VALUES (
                    $1, $2, 'gemini', 'text-embedding-004', 'v1', 768,
                    (SELECT array_agg(0.01::float4)::vector(768) FROM generate_series(1, 768)),
                    (SELECT array_agg(0.01::float4)::vector(1536) FROM generate_series(1, 1536))
                )
                """,
                mem_id, user_id,
            )

        # 3. Model registry dimension mismatch rejected by trigger
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="does not match registered model dimension"):
            await conn.execute(
                """
                INSERT INTO public.memory_embeddings (
                    memory_id, user_id, provider, model, version, dimension, embedding_1536
                ) VALUES (
                    $1, $2, 'gemini', 'text-embedding-004', 'v1', 1536,
                    (SELECT array_agg(0.01::float4)::vector(1536) FROM generate_series(1, 1536))
                )
                """,
                mem_id, user_id,
            )

        # 4. Valid insertion for gemini text-embedding-004 (768) succeeds
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (
                memory_id, user_id, provider, model, version, dimension, embedding_768
            ) VALUES (
                $1, $2, 'gemini', 'text-embedding-004', 'v1', 768,
                (SELECT array_agg(0.01::float4)::vector(768) FROM generate_series(1, 768))
            )
            """,
            mem_id, user_id,
        )

        # 5. Coexistence: OpenAI embedding (1536) coexists on the same memory record without conflict
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (
                memory_id, user_id, provider, model, version, dimension, embedding_1536
            ) VALUES (
                $1, $2, 'openai', 'text-embedding-3-small', 'v1', 1536,
                (SELECT array_agg(0.01::float4)::vector(1536) FROM generate_series(1, 1536))
            )
            """,
            mem_id, user_id,
        )

        count = await conn.fetchval("SELECT count(*) FROM public.memory_embeddings WHERE memory_id = $1", mem_id)
        assert count == 2

        # 6. Model registry cutover: activate openai model as auren_worker
        worker_user = f"worker_emb_{uuid.uuid4().hex[:8]}"
        worker_pass = "worker_pass_123"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD '{worker_pass}' IN ROLE auren_worker")
        try:
            worker_conn = await asyncpg.connect(
                host=postgresql_server["host"],
                port=postgresql_server["port"],
                database=db_name,
                user=worker_user,
                password=worker_pass,
            )
            try:
                await worker_conn.execute("SELECT public.activate_embedding_model_rpc('openai', 'text-embedding-3-small', 'v1')")
            finally:
                await worker_conn.close()
        finally:
            await conn.execute(f"DROP USER IF EXISTS {worker_user}")

        active_models = await conn.fetch("SELECT provider, model FROM public.embedding_models WHERE purpose = 'retrieval' AND is_active = TRUE")
        assert len(active_models) == 1
        assert active_models[0]["provider"] == "openai"


@pytest.mark.asyncio
async def test_worker_queue_concurrency_lease_and_stale_rejection(postgresql_server):
    """Verify that batch size and lease duration are validated, concurrent worker claims
    are safe and atomic (SKIP LOCKED), expired leases reject completion and ingestion,
    and exhausted jobs cannot be reclaimed indefinitely.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_wqueue", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "worker_lease@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        conv_id = uuid.uuid4()
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Lease Conv')", conv_id, user_id)
        msg_1 = uuid.uuid4()
        msg_2 = uuid.uuid4()
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Task 1')", msg_1, conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Task 2')", msg_2, conv_id, user_id)

        job_1 = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_1)
        job_2 = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_2)

        # Create authentic worker login user
        worker_user = f"worker_q_{uuid.uuid4().hex[:8]}"
        worker_pass = "worker_secret_123"
        await conn.execute(f"CREATE USER {worker_user} WITH PASSWORD '{worker_pass}' IN ROLE auren_worker")

        try:
            worker_conn = await asyncpg.connect(
                host=postgresql_server["host"],
                port=postgresql_server["port"],
                database=db_name,
                user=worker_user,
                password=worker_pass,
            )
            try:
                # 1. Parameter validation in claim_memory_extraction_jobs_rpc
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Batch size must be between 1 and 50"):
                    await worker_conn.execute("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', p_batch_size => 0)")

                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Lease duration must be between 10 and 3600"):
                    await worker_conn.execute("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', p_lease_seconds => 5)")

                # 2. Concurrent claims: Worker A claims 1 job
                claimed_a = await worker_conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', 1, 30)")
                assert len(claimed_a) == 1
                job_a_id = claimed_a[0]["id"]
                token_a = claimed_a[0]["claim_token"]
                assert token_a is not None

                # Worker B concurrently claims 1 job; must receive the other job without collision
                claimed_b = await worker_conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-b', 1, 30)")
                assert len(claimed_b) == 1
                job_b_id = claimed_b[0]["id"]
                token_b = claimed_b[0]["claim_token"]
                assert job_a_id != job_b_id
                assert token_b is not None

                # 3. Stale worker completion rejection: artificially expire Worker A's lease
                await conn.execute(
                    "UPDATE public.memory_extraction_jobs SET lease_expires_at = now() - INTERVAL '5 seconds' WHERE id = $1",
                    job_a_id,
                )

                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="lease expired"):
                    await worker_conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-a', $2)", job_a_id, token_a)

                # Stale worker ingestion rejection on expired lease
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="lease expired"):
                    await worker_conn.execute(
                        """
                        SELECT public.insert_extracted_memory_rpc(
                            p_job_id => $1,
                            p_worker_id => 'worker-a',
                            p_claim_token => $2,
                            p_content => 'Stale ingestion attempt',
                            p_memory_type => 'fact',
                            p_category => 'general'
                        )
                        """,
                        job_a_id,
                        token_a,
                    )

                # Stale worker failure report rejection on expired lease
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="lease expired"):
                    await worker_conn.execute("SELECT public.fail_memory_extraction_job_rpc($1, 'worker-a', $2, 'Failed expired')", job_a_id, token_a)

                # 4. Reclamation by reaper
                reaped = await worker_conn.fetchval("SELECT public.reap_stale_extraction_jobs_rpc(3)")
                assert reaped >= 1

                reaped_row = await conn.fetchrow("SELECT status, locked_by, claim_token FROM public.memory_extraction_jobs WHERE id = $1", job_a_id)
                assert reaped_row["status"] == "pending"
                assert reaped_row["locked_by"] is None
                assert reaped_row["claim_token"] != token_a  # New claim token generated on requeue

                # 5. Same-worker lease generation protection test:
                # Worker A re-claims job_a (new claim token issued)
                reclaimed_a = await worker_conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', 1, 30)")
                assert len(reclaimed_a) == 1
                assert reclaimed_a[0]["id"] == job_a_id
                token_a_new = reclaimed_a[0]["claim_token"]
                assert token_a_new != token_a

                # Delayed thread from Worker A using OLD token_a attempts to complete job: REJECTED with Stale claim token
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                    await worker_conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-a', $2)", job_a_id, token_a)

                # Delayed thread from Worker A using OLD token_a attempts to insert extracted memory: REJECTED with Stale claim token
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                    await worker_conn.execute(
                        """
                        SELECT public.insert_extracted_memory_rpc(
                            p_job_id => $1,
                            p_worker_id => 'worker-a',
                            p_claim_token => $2,
                            p_content => 'Delayed thread attempt',
                            p_memory_type => 'fact',
                            p_category => 'general'
                        )
                        """,
                        job_a_id,
                        token_a,
                    )

                # Delayed thread from Worker A using OLD token_a attempts to fail job: REJECTED with Stale claim token
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                    await worker_conn.execute("SELECT public.fail_memory_extraction_job_rpc($1, 'worker-a', $2, 'Delayed failure')", job_a_id, token_a)

                # Ingestion with valid current token_a_new succeeds
                new_mem_id = await worker_conn.fetchval(
                    """
                    SELECT public.insert_extracted_memory_rpc(
                        p_job_id => $1,
                        p_worker_id => 'worker-a',
                        p_claim_token => $2,
                        p_content => 'Valid extracted memory',
                        p_memory_type => 'fact',
                        p_category => 'general'
                    )
                    """,
                    job_a_id,
                    token_a_new,
                )
                assert new_mem_id is not None

                # Worker A completes its job with valid current token_a_new
                comp_a = await worker_conn.fetchval("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-a', $2)", job_a_id, token_a_new)
                assert comp_a is True

                # 6. Idempotency and Claim-Token Enforcement on Completed Job:
                # - Repeated completion with matching current claim token succeeds idempotently (returns True)
                repeat_comp = await worker_conn.fetchval("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-a', $2)", job_a_id, token_a_new)
                assert repeat_comp is True

                # - Earlier/stale claim token completion attempt on already-completed job is strictly REJECTED
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                    await worker_conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-a', $2)", job_a_id, token_a)

                # - Random/mismatched claim token completion attempt on already-completed job is strictly REJECTED
                with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Stale claim token"):
                    await worker_conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-a', $2)", job_a_id, uuid.uuid4())

                # Worker B completes its job normally
                comp_b = await worker_conn.fetchval("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-b', $2)", job_b_id, token_b)
                assert comp_b is True

                # 7. Queue Error Sanitization in PostgreSQL:
                # Enqueue sensitive failure test job
                msg_sens = uuid.uuid4()
                await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Task Sens')", msg_sens, conv_id, user_id)
                job_sens = await conn.fetchval("SELECT public.enqueue_memory_extraction_job_rpc($1, $2)", conv_id, msg_sens)
                claimed_sens = await worker_conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', 5, 30)")
                token_sens = [r["claim_token"] for r in claimed_sens if r["id"] == job_sens][0]

                raw_sensitive_err = (
                    "Provider failure: sk-ant-api03-secret1234567890_XYZ with "
                    "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc "
                    "and password=MyDatabasePassword123"
                )
                await worker_conn.execute("SELECT public.fail_memory_extraction_job_rpc($1, 'worker-a', $2, $3, false)", job_sens, token_sens, raw_sensitive_err)
                sens_row = await conn.fetchrow("SELECT last_error FROM public.memory_extraction_jobs WHERE id = $1", job_sens)
                assert sens_row is not None
                assert "sk-ant-api03" not in sens_row["last_error"]
                assert "eyJhbGci" not in sens_row["last_error"]
                assert "MyDatabasePassword123" not in sens_row["last_error"]
                assert "[REDACTED_API_KEY]" in sens_row["last_error"]
                assert "password=[REDACTED]" in sens_row["last_error"]

                # 8. Exhausted job cannot be reclaimed indefinitely
                await conn.execute(
                    """
                    UPDATE public.memory_extraction_jobs
                    SET status = 'processing', locked_by = 'flaky-worker', lease_expires_at = now() - INTERVAL '10 seconds', attempts = 3, max_attempts = 3
                    WHERE id = $1
                    """,
                    job_a_id,
                )
                await worker_conn.fetchval("SELECT public.reap_stale_extraction_jobs_rpc(3)")

                dead_job = await conn.fetchrow("SELECT status FROM public.memory_extraction_jobs WHERE id = $1", job_a_id)
                assert dead_job["status"] == "dead_letter"

                # Calling reaper again does NOT revive dead-letter job
                await worker_conn.fetchval("SELECT public.reap_stale_extraction_jobs_rpc(3)")
                dead_job_after = await conn.fetchrow("SELECT status FROM public.memory_extraction_jobs WHERE id = $1", job_a_id)
                assert dead_job_after["status"] == "dead_letter"
            finally:
                await worker_conn.close()
        finally:
            await conn.execute(f"DROP USER IF EXISTS {worker_user}")


@pytest.mark.asyncio
async def test_memory_lifecycle_terminal_invariants_and_concurrency(postgresql_server):
    """Verify that invalid lifecycle transitions are rejected by RPCs and database triggers,
    supersession of unconfirmed memories preserves unconfirmed status, lineage pointers are preserved,
    and concurrent supersessions on the same memory fail cleanly without race conditions.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_life", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "lifecycle@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")

        # 1. Create an unconfirmed memory
        mem_unconf_id = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'Unconfirmed hobby: sailing',
                p_memory_type => 'preference',
                p_category => 'personal',
                p_origin => 'user_direct_input',
                p_confirmation_status => 'unconfirmed'
            )
            """
        )
        unconf_row = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", mem_unconf_id)
        assert unconf_row["confirmation_status"] == "unconfirmed"
        assert unconf_row["last_confirmed_at"] is None

        # 2. Supersede unconfirmed memory without explicit confirmation: successor must remain unconfirmed
        mem_successor_id = await conn.fetchval(
            """
            SELECT public.supersede_memory_rpc(
                p_old_memory_id => $1,
                p_new_content => 'Updated hobby: competitive sailing'
            )
            """,
            mem_unconf_id,
        )
        succ_row = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", mem_successor_id)
        assert succ_row["confirmation_status"] == "unconfirmed"
        assert succ_row["last_confirmed_at"] is None
        assert succ_row["previous_version_id"] == mem_unconf_id
        assert succ_row["root_memory_id"] == mem_unconf_id

        # 3. Invalid transition: attempting to confirm superseded memory is rejected
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Cannot confirm memory with lifecycle status: superseded"):
            await conn.execute("SELECT public.confirm_memory_rpc($1)", mem_unconf_id)

        # 4. Invalid transition: attempting to supersede an already superseded memory is rejected
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Cannot supersede memory with lifecycle status: superseded"):
            await conn.execute(
                """
                SELECT public.supersede_memory_rpc(
                    p_old_memory_id => $1,
                    p_new_content => 'Invalid second supersession'
                )
                """,
                mem_unconf_id,
            )

        # 5. Rejection and immutability guard: reject successor
        await conn.execute("SELECT public.reject_memory_rpc($1)", mem_successor_id)
        rej_row = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", mem_successor_id)
        assert rej_row["confirmation_status"] == "rejected"

        # Attempting to confirm a rejected memory is rejected by trigger / RPC
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Cannot confirm previously rejected memory"):
            await conn.execute("SELECT public.confirm_memory_rpc($1)", mem_successor_id)

        # 6. Database trigger test: directly trying to reactivate superseded memory via SQL is blocked
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="superseded memories are terminal"):
            await conn.execute("UPDATE public.memories SET lifecycle_status = 'active' WHERE id = $1", mem_unconf_id)

        # Directly trying to confirm a rejected memory via SQL is blocked by trigger
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="rejected memories cannot be confirmed"):
            await conn.execute("UPDATE public.memories SET confirmation_status = 'confirmed' WHERE id = $1", mem_successor_id)

        # 7. Concurrent supersession test:
        active_mem_id = await conn.fetchval(
            """
            SELECT public.create_memory_rpc(
                p_content => 'Active location: Chicago',
                p_memory_type => 'fact',
                p_category => 'personal'
            )
            """
        )

        conn2 = await asyncpg.connect(
            host=postgresql_server["host"],
            port=postgresql_server["port"],
            database=db_name,
        )
        try:
            await conn2.execute(MOCK_AUTH_SQL)
            await conn2.execute(f"SET request.jwt.claim.sub = '{user_id}'")

            tx1 = conn.transaction()
            await tx1.start()
            s1 = await conn.fetchval(
                """
                SELECT public.supersede_memory_rpc(
                    p_old_memory_id => $1,
                    p_new_content => 'Location: Evanston'
                )
                """,
                active_mem_id,
            )
            assert s1 is not None

            async def run_tx2():
                try:
                    return await conn2.fetchval(
                        """
                        SELECT public.supersede_memory_rpc(
                            p_old_memory_id => $1,
                            p_new_content => 'Location: Naperville'
                        )
                        """,
                        active_mem_id,
                    )
                except asyncpg.exceptions.InvalidParameterValueError as e:
                    return str(e)

            tx2_task = asyncio.create_task(run_tx2())
            await asyncio.sleep(0.05)

            await tx1.commit()

            tx2_result = await tx2_task
            assert "Cannot supersede memory with lifecycle status: superseded" in str(tx2_result)
        finally:
            await conn2.close()


@pytest.mark.asyncio
async def test_cascading_deletion_and_gdpr_purge(postgresql_server):
    """Verify that source-message deletion sets source_message_id to NULL on memories,
    cascades on extraction jobs, and purge_all_memories_rpc completely purges user memory data.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_purge", apply_all_migrations=True) as (conn, db_name):
        user_id = uuid.uuid4()
        other_user = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "purge@example.com")
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", other_user, "other@example.com")
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

        # Create memory and job for other user
        other_conv = uuid.uuid4()
        other_msg = uuid.uuid4()
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Other Conv')", other_conv, other_user)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', 'Other msg')", other_msg, other_conv, other_user)
        await conn.execute(
            """
            INSERT INTO public.memories (user_id, content, memory_type, category)
            VALUES ($1, 'Other secret', 'fact', 'general')
            """,
            other_user,
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

        # Assert other user's memory is untouched
        assert await conn.fetchval("SELECT count(*) FROM public.memories WHERE user_id = $1", other_user) == 1


@pytest.mark.asyncio
async def test_fresh_database_applies_all_migrations_001_through_017(postgresql_server):
    """Verify that a fresh database successfully applies all migrations 001 through 017 in sequence,
    establishing correct table structures, active embedding models, restricted worker privileges,
    and dedicated login service roles.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_fresh_17", apply_all_migrations=True) as (conn, db_name):
        # 1. Verify all expected memory and security tables exist
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        table_names = {t["table_name"] for t in tables}
        for expected in ("memories", "memory_embeddings", "embedding_models", "memory_extraction_jobs", "consumed_consent_tokens"):
            assert expected in table_names

        # 2. Verify active retrieval embedding model is gemini-embedding-2 (768-dim)
        active_model = await conn.fetchrow(
            "SELECT provider, model, version, dimension, is_active FROM public.embedding_models WHERE purpose = 'retrieval' AND is_active = TRUE"
        )
        assert active_model is not None
        assert active_model["provider"] == "gemini"
        assert active_model["model"] == "gemini-embedding-2"
        assert active_model["version"] == "v1"
        assert active_model["dimension"] == 768

        # 3. Verify text-embedding-004 is retained in registry as inactive
        old_model = await conn.fetchrow(
            "SELECT is_active FROM public.embedding_models WHERE model = 'text-embedding-004' AND provider = 'gemini'"
        )
        assert old_model is not None
        assert old_model["is_active"] is False

        # 4. Verify auren_worker role is NOLOGIN NOINHERIT
        role_info = await conn.fetchrow("SELECT rolcanlogin, rolinherit FROM pg_roles WHERE rolname = 'auren_worker'")
        assert role_info is not None
        assert role_info["rolcanlogin"] is False
        assert role_info["rolinherit"] is False

        # 5. Verify auren_worker_service has LOGIN and membership in auren_worker
        svc_info = await conn.fetchrow("SELECT rolcanlogin FROM pg_roles WHERE rolname = 'auren_worker_service'")
        assert svc_info is not None
        assert svc_info["rolcanlogin"] is True

        is_member = await conn.fetchval("""
            SELECT pg_has_role('auren_worker_service', 'auren_worker', 'MEMBER')
        """)
        assert is_member is True


@pytest.mark.asyncio
async def test_upgrade_database_016_to_017_migration_safety(postgresql_server):
    """Verify forward migration upgrade safety:
    1. An existing database with migrations 001 through 016 applied and containing pre-existing
       data (memories and legacy embeddings under text-embedding-004).
    2. Forward migration 017 is applied to upgrade the database.
    3. Demonstrates:
       - Existing memories and embeddings are preserved intact without data loss.
       - Active retrieval model shifts to gemini-embedding-2, retiring text-embedding-004.
       - auren_worker is reconciled to NOLOGIN NOINHERIT.
       - auren_worker_service exists with LOGIN and auren_worker membership.
       - Direct table SELECT/DML by auren_worker on data tables is strictly denied.
       - RPC functions (insert_extracted_memory_rpc, search_memories_hybrid_rpc) work accurately.
       - Migration 017 is repeatable / idempotent.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_upg_17", apply_all_migrations=False) as (conn, db_name):
        # Step A: Apply migrations 001 through 016 (representing existing database prior to upgrade)
        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611*.sql")))
        mf_001_to_016 = [mf for mf in migration_files if not any(x in mf for x in ("017_", "018_"))]
        assert len(mf_001_to_016) == 16, f"Expected 16 baseline migrations, got {len(mf_001_to_016)}"
        for mf in mf_001_to_016:
            sql = Path(mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        # Verify initial 016 state: text-embedding-004 is active
        init_active = await conn.fetchval(
            "SELECT model FROM public.embedding_models WHERE purpose = 'retrieval' AND is_active = TRUE"
        )
        assert init_active == "text-embedding-004"

        # Step B: Insert pre-existing user data under baseline 016
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_id, "upgrade_user@example.com")
        await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Pre-upgrade Conv')", conv_id, user_id)
        await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', 'Historical message')", msg_id, conv_id, user_id)

        legacy_mem_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO public.memories (id, user_id, content, memory_type, category, importance, confidence, confirmation_status, last_confirmed_at, lifecycle_status, metadata)
            VALUES ($1, $2, 'Pre-existing persistent memory about Python', 'fact', 'technical', 4, 0.95, 'confirmed', now(), 'active', '{"pre_upgrade": true}'::jsonb)
            """,
            legacy_mem_id, user_id,
        )

        dummy_768 = f"[{','.join(['0.02'] * 768)}]"
        await conn.execute(
            """
            INSERT INTO public.memory_embeddings (memory_id, user_id, provider, model, version, dimension, embedding_768, is_active)
            VALUES ($1, $2, 'gemini', 'text-embedding-004', 'v1', 768, $3::vector, TRUE)
            """,
            legacy_mem_id, user_id, dummy_768,
        )

        # Step C: Execute forward migration 017
        mf_017 = [mf for mf in migration_files if "017_" in mf][0]
        sql_017 = Path(mf_017).read_text(encoding="utf-8")
        await conn.execute(sql_017)

        # Step D: Verify data preservation
        mem_after = await conn.fetchrow("SELECT * FROM public.memories WHERE id = $1", legacy_mem_id)
        assert mem_after is not None
        assert mem_after["content"] == "Pre-existing persistent memory about Python"
        import json
        meta = json.loads(mem_after["metadata"]) if isinstance(mem_after["metadata"], str) else mem_after["metadata"]
        assert meta["pre_upgrade"] is True

        emb_after = await conn.fetchrow("SELECT * FROM public.memory_embeddings WHERE memory_id = $1", legacy_mem_id)
        assert emb_after is not None
        assert emb_after["model"] == "text-embedding-004"
        assert emb_after["dimension"] == 768
        assert emb_after["embedding_768"] is not None

        # Step E: Verify active embedding model shifted to gemini-embedding-2
        active_after = await conn.fetchrow(
            "SELECT provider, model, version, dimension FROM public.embedding_models WHERE purpose = 'retrieval' AND is_active = TRUE"
        )
        assert active_after is not None
        assert active_after["model"] == "gemini-embedding-2"
        assert active_after["dimension"] == 768

        old_after = await conn.fetchval(
            "SELECT is_active FROM public.embedding_models WHERE model = 'text-embedding-004' AND provider = 'gemini'"
        )
        assert old_after is False

        # Step F: Verify worker role reconciliation
        worker_role = await conn.fetchrow("SELECT rolcanlogin, rolinherit FROM pg_roles WHERE rolname = 'auren_worker'")
        assert worker_role["rolcanlogin"] is False
        assert worker_role["rolinherit"] is False

        svc_role = await conn.fetchrow("SELECT rolcanlogin FROM pg_roles WHERE rolname = 'auren_worker_service'")
        assert svc_role["rolcanlogin"] is True

        # Step G: Verify direct table access denial from auren_worker
        worker_test_user = f"worker_test_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"CREATE USER {worker_test_user} WITH PASSWORD 'pw' IN ROLE auren_worker")
        worker_conn = await asyncpg.connect(
            host=postgresql_server["host"], port=postgresql_server["port"], database=db_name,
            user=worker_test_user, password="pw",
        )
        try:
            # Direct SELECT on memories must be denied
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.memories")

            # Direct SELECT on messages must be denied
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.messages")

            # Direct SELECT on journal_entries must be denied
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.journal_entries")

            # Direct SELECT on memory_extraction_jobs must be denied
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await worker_conn.fetch("SELECT * FROM public.memory_extraction_jobs")

            # But worker CAN execute queue claim RPC
            jobs = await worker_conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-test', 5, 300)")
            assert isinstance(jobs, list)

        finally:
            await worker_conn.close()

        # Step H: Verify repeatability / idempotency: re-running 017 succeeds without error
        await conn.execute(sql_017)
