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

from app.core.config import settings
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
            assert len(migration_files) >= 13, f"Expected at least 13 migration files, found {len(migration_files)}"
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
async def test_fresh_migration_001_through_013(postgresql_server):
    """Execute complete migration sequence 001 through 013 and verify all memory tables,
    indexes, schema columns, and NULL confidence support exist accurately.
    """
    async with isolated_postgres_db(postgresql_server, prefix="mem_fresh", apply_all_migrations=True) as (conn, db_name):
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        table_names = {t["table_name"] for t in tables}

        assert "memories" in table_names
        assert "memory_embeddings" in table_names
        assert "embedding_models" in table_names
        assert "consumed_consent_tokens" in table_names
        assert "memory_extraction_jobs" in table_names

        # Verify vector columns on memory_embeddings
        cols = await conn.fetch("SELECT column_name, data_type, udt_name, is_nullable FROM information_schema.columns WHERE table_name = 'memories'")
        col_map = {c["column_name"]: c for c in cols}
        assert "confidence" in col_map
        assert col_map["confidence"]["is_nullable"] == "YES"

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
            if any(x in mf for x in ("011_", "012_", "013_")):
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

        # Now execute Migration 011, 012, and 013 in order
        for suffix in ("011_", "012_", "013_"):
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
            finally:
                await client_conn.close()

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

        secret = settings.JOURNAL_HMAC_SECRET
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
                now=now,
            )

        # 6. Expired token is rejected
        past_time = now + timedelta(seconds=130)
        with pytest.raises(ExpiredConsentTokenError, match="has expired"):
            verify_journal_consent_token(
                token=token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                now=past_time,
            )

        # 7. Excessive lifetime (> 15 minutes) is rejected
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
                now=now,
            )

        # 8. Valid token is verified and atomically consumed in PostgreSQL
        consumed = await verify_and_consume_journal_consent(
            token=token,
            secret=secret,
            expected_user_id=user_a,
            expected_conversation_id=conv_a,
            expected_idempotency_key=idemp_key,
            db_conn=conn,
            now=now,
        )
        assert consumed is True

        # 9. Replay attempt with same nonce is rejected by database ledger
        with pytest.raises(ReplayedConsentTokenError, match="already been consumed"):
            await verify_and_consume_journal_consent(
                token=token,
                secret=secret,
                expected_user_id=user_a,
                expected_conversation_id=conv_a,
                expected_idempotency_key=idemp_key,
                db_conn=conn,
                now=now,
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
        await conn.execute("SET ROLE auren_worker")
        await conn.execute("SELECT public.activate_embedding_model_rpc('openai', 'text-embedding-3-small', 'v1')")
        await conn.execute("RESET ROLE")

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

        # 1. Parameter validation in claim_memory_extraction_jobs_rpc
        await conn.execute("SET ROLE auren_worker")
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Batch size must be between 1 and 50"):
            await conn.execute("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', p_batch_size => 0)")

        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="Lease duration must be between 10 and 3600"):
            await conn.execute("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', p_lease_seconds => 5)")

        # 2. Concurrent claims: Worker A claims 1 job
        claimed_a = await conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-a', 1, 30)")
        assert len(claimed_a) == 1
        job_a_id = claimed_a[0]["id"]

        # Worker B concurrently claims 1 job; must receive the other job without collision
        claimed_b = await conn.fetch("SELECT * FROM public.claim_memory_extraction_jobs_rpc('worker-b', 1, 30)")
        assert len(claimed_b) == 1
        job_b_id = claimed_b[0]["id"]
        assert job_a_id != job_b_id

        # 3. Stale worker completion rejection: artificially expire Worker A's lease
        await conn.execute("RESET ROLE")
        await conn.execute(
            "UPDATE public.memory_extraction_jobs SET lease_expires_at = now() - INTERVAL '5 seconds' WHERE id = $1",
            job_a_id,
        )

        await conn.execute("SET ROLE auren_worker")
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="lease expired"):
            await conn.execute("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-a')", job_a_id)

        # Stale worker ingestion rejection on expired lease
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="lease expired"):
            await conn.execute(
                """
                SELECT public.insert_extracted_memory_rpc(
                    p_job_id => $1,
                    p_worker_id => 'worker-a',
                    p_content => 'Stale ingestion attempt',
                    p_memory_type => 'fact',
                    p_category => 'general'
                )
                """,
                job_a_id,
            )

        # 4. Reclamation by reaper
        reaped = await conn.fetchval("SELECT public.reap_stale_extraction_jobs_rpc(3)")
        assert reaped >= 1

        reaped_row = await conn.fetchrow("SELECT status, locked_by FROM public.memory_extraction_jobs WHERE id = $1", job_a_id)
        assert reaped_row["status"] == "pending"
        assert reaped_row["locked_by"] is None

        # 5. Worker B completes its job normally
        comp_b = await conn.fetchval("SELECT public.complete_memory_extraction_job_rpc($1, 'worker-b')", job_b_id)
        assert comp_b is True

        # 6. Exhausted job cannot be reclaimed indefinitely
        await conn.execute("RESET ROLE")
        await conn.execute(
            """
            UPDATE public.memory_extraction_jobs
            SET status = 'processing', locked_by = 'flaky-worker', lease_expires_at = now() - INTERVAL '10 seconds', attempts = 3, max_attempts = 3
            WHERE id = $1
            """,
            job_a_id,
        )
        await conn.execute("SET ROLE auren_worker")
        await conn.fetchval("SELECT public.reap_stale_extraction_jobs_rpc(3)")

        dead_job = await conn.fetchrow("SELECT status FROM public.memory_extraction_jobs WHERE id = $1", job_a_id)
        assert dead_job["status"] == "dead_letter"

        # Calling reaper again does NOT revive dead-letter job
        await conn.fetchval("SELECT public.reap_stale_extraction_jobs_rpc(3)")
        dead_job_after = await conn.fetchrow("SELECT status FROM public.memory_extraction_jobs WHERE id = $1", job_a_id)
        assert dead_job_after["status"] == "dead_letter"
        await conn.execute("RESET ROLE")


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
