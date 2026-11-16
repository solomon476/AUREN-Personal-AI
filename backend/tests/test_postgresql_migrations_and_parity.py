"""Real PostgreSQL integration tests verifying migration execution, trigger compatibility,

normalization parity, UUIDv5 derivation, legacy provenance validation, and pgcrypto schema portability.
All tests run against genuinely isolated ephemeral databases with automatic cleanup.
"""

from contextlib import asynccontextmanager
import glob
import json
from pathlib import Path
import subprocess
import time
import uuid

import asyncpg
import pytest

from app.models.chat import compute_request_fingerprint

PG_SOCK_DIR = Path("/tmp/auren_pg_sock")
PG_DATA_DIR = Path("/tmp/auren_pg_test")
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
        SELECT '11111111-1111-1111-1111-111111111111'::UUID;
    $$ LANGUAGE sql STABLE;
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
    END $$;
"""


@pytest.fixture(scope="session")
def postgresql_server():
    """Ensure local PostgreSQL server is running for actual database-level testing."""
    PG_SOCK_DIR.mkdir(parents=True, exist_ok=True)

    sock_file = PG_SOCK_DIR / f".s.PGSQL.{PG_PORT}"
    if not sock_file.exists():
        if not (PG_DATA_DIR / "PG_VERSION").exists():
            subprocess.run(
                ["/usr/lib/postgresql/17/bin/initdb", "-D", str(PG_DATA_DIR), "--auth=trust", "--no-sync"],
                check=True,
                capture_output=True,
            )
        subprocess.run(
            [
                "/usr/lib/postgresql/17/bin/pg_ctl",
                "-D", str(PG_DATA_DIR),
                "-o", f"-p {PG_PORT} -k {PG_SOCK_DIR}",
                "-l", str(PG_DATA_DIR / "logfile"),
                "start",
            ],
            check=True,
            capture_output=True,
        )
        time.sleep(1.0)

    yield {"host": str(PG_SOCK_DIR), "port": PG_PORT}


@asynccontextmanager
async def isolated_postgres_db(server_info, prefix="auren_test", apply_all_migrations=False):
    """Context manager creating a uniquely named ephemeral database for each test.

    Guarantees complete database isolation, zero dependence on residual state from
    previous runs or other tests, and robust teardown using DROP DATABASE ... WITH (FORCE).
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
        if apply_all_migrations:
            await conn.execute(MOCK_AUTH_SQL)
            migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611150000*.sql")))
            assert len(migration_files) == 10, f"Expected 10 migration files, found {len(migration_files)}"
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
async def test_fresh_database_migration_001_to_010(postgresql_server):
    """Execute the complete migration sequence (001 through 010) on a fresh isolated database."""
    async with isolated_postgres_db(postgresql_server, prefix="auren_fresh", apply_all_migrations=False) as (conn, db_name):
        # Mock auth setup matching Supabase
        await conn.execute(MOCK_AUTH_SQL)

        # Apply all migrations in order
        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611150000*.sql")))
        assert len(migration_files) == 10, f"Expected 10 migration files, found {len(migration_files)}"

        for mf in migration_files:
            sql = Path(mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        # Verify tables and triggers exist
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        table_names = {t["table_name"] for t in tables}
        assert "chat_requests" in table_names
        assert "conversations" in table_names
        assert "messages" in table_names

        # Verify strict immutability trigger exists
        triggers = await conn.fetch("SELECT trigger_name FROM information_schema.triggers WHERE event_object_table = 'chat_requests'")
        trigger_names = {tr["trigger_name"] for tr in triggers}
        assert "trg_chat_requests_immutability" in trigger_names


@pytest.mark.asyncio
async def test_legacy_provenance_validation_and_reconstruction(postgresql_server):
    """Verify legacy migration 010 strictly enforces provenance validation across all conditions:

    - Records with valid user messages survive and receive correct reconstructed fingerprints.
    - Records with mismatched user_id are purged.
    - Records with mismatched conversation_id are purged.
    - Records referencing assistant messages are purged.
    - Records with altered metadata (edited=true, content_changed=true, original_content) are purged.
    - Records with missing source messages are purged.
    - Records with non-boolean metadata string survive and reconstruct safely.
    All executed against a fresh, completely isolated test database.
    """
    async with isolated_postgres_db(postgresql_server, prefix="auren_prov", apply_all_migrations=False) as (conn, db_name):
        await conn.execute(MOCK_AUTH_SQL)

        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611150000*.sql")))
        # Apply 001..009
        for mf in migration_files[:-1]:
            sql = Path(mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        # Setup users
        user_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
        user_b = uuid.UUID("22222222-2222-2222-2222-222222222222")
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_a, "user_a@example.com")
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", user_b, "user_b@example.com")

        # Setup conversations
        conv_a1 = uuid.uuid4()
        conv_a2 = uuid.uuid4()
        conv_b = uuid.uuid4()
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv A1')", conv_a1, user_a)
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv A2')", conv_a2, user_a)
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Conv B')", conv_b, user_b)

        # 1. Valid user message belonging to correct user & explicit conversation
        key_valid_explicit = "legacy-valid-explicit"
        msg_valid_explicit = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', $4)",
            msg_valid_explicit, conv_a1, user_a, "Pristine explicit conv prompt",
        )

        # 2. Valid user message originally without conversation ID (deterministic conversation)
        key_valid_no_conv = "legacy-valid-no-conv"
        det_conv_a = uuid.uuid5(uuid.NAMESPACE_OID, f"auren:conv:{user_a}:{key_valid_no_conv}")
        await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, 'Det Conv A')", det_conv_a, user_a)
        msg_valid_no_conv = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', $4)",
            msg_valid_no_conv, det_conv_a, user_a, "Pristine no-conv prompt",
        )

        # 3. Message belonging to another user (user_b vs user_a)
        key_cross_user = "legacy-cross-user"
        msg_user_b = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', $4)",
            msg_user_b, conv_b, user_b, "Prompt belonging to user B",
        )

        # 4. Message belonging to another conversation (conv_a2 vs conv_a1)
        key_cross_conv = "legacy-cross-conv"
        msg_other_conv = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'user', $4)",
            msg_other_conv, conv_a2, user_a, "Prompt in different conv",
        )

        # 5. Assistant-role message referenced as user message
        key_assistant = "legacy-assistant-role"
        msg_assistant = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, 'assistant', $4)",
            msg_assistant, conv_a1, user_a, "Assistant response mistakenly referenced",
        )

        # 6. Altered metadata: edited = true
        key_edited = "legacy-edited-true"
        msg_edited = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'user', $4, $5)",
            msg_edited, conv_a1, user_a, "Edited text", '{"edited": true}',
        )

        # 7. Altered metadata: content_changed = true
        key_changed = "legacy-content-changed-true"
        msg_changed = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'user', $4, $5)",
            msg_changed, conv_a1, user_a, "Changed text", '{"content_changed": true}',
        )

        # 8. Altered metadata: original_content key present
        key_orig = "legacy-original-content-key"
        msg_orig = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'user', $4, $5)",
            msg_orig, conv_a1, user_a, "Original key text", '{"original_content": "old text"}',
        )

        # 9. Missing source message (referenced UUID does not exist)
        key_missing = "legacy-missing-msg"
        fake_msg_id = uuid.uuid4()

        # 10. Valid message with non-boolean metadata string (safe to reconstruct)
        key_non_bool = "legacy-non-bool-meta"
        msg_non_bool = uuid.uuid4()
        await conn.execute(
            "INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, 'user', $4, $5)",
            msg_non_bool, conv_a1, user_a, "Safe non-bool metadata prompt", '{"edited": "false_string", "note": "ok"}',
        )

        # Insert legacy chat requests with synthetic migration 009 fingerprints
        # Temporarily bypass FK constraint for the missing-message test record
        await conn.execute("SET session_replication_role = replica")

        legacy_test_records = [
            (user_a, key_valid_explicit, conv_a1, msg_valid_explicit),
            (user_a, key_valid_no_conv, det_conv_a, msg_valid_no_conv),
            (user_a, key_cross_user, conv_a1, msg_user_b),        # Mismatched user_id
            (user_a, key_cross_conv, conv_a1, msg_other_conv),     # Mismatched conversation_id
            (user_a, key_assistant, conv_a1, msg_assistant),      # role = assistant
            (user_a, key_edited, conv_a1, msg_edited),            # edited = true
            (user_a, key_changed, conv_a1, msg_changed),          # content_changed = true
            (user_a, key_orig, conv_a1, msg_orig),                # original_content present
            (user_a, key_missing, conv_a1, fake_msg_id),          # Missing message
            (user_a, key_non_bool, conv_a1, msg_non_bool),        # Safe non-bool metadata
        ]

        for u, k, c, m in legacy_test_records:
            synth = await conn.fetchval(
                "SELECT encode(digest(convert_to($1, 'UTF8'), 'sha256'), 'hex')",
                f"legacy:{u}:{k}",
            )
            await conn.execute(
                """
                INSERT INTO public.chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint)
                VALUES ($1, $2, $3, 'completed', $4, $5)
                """,
                u, k, c, m, synth,
            )

        await conn.execute("SET session_replication_role = DEFAULT")

        # Execute Migration 010
        sql010 = Path(migration_files[-1]).read_text(encoding="utf-8")
        await conn.execute(sql010)

        # Assertions on Surviving Records:
        # 1. Valid explicit conv record survived with reconstructed conv:<uuid> fingerprint
        fp_explicit = await conn.fetchval("SELECT request_fingerprint FROM public.chat_requests WHERE idempotency_key = $1", key_valid_explicit)
        expected_fp_explicit = compute_request_fingerprint(user_a, "Pristine explicit conv prompt", conv_a1)
        assert fp_explicit == expected_fp_explicit

        # 2. Valid no-conv record survived with reconstructed conv:none fingerprint
        fp_no_conv = await conn.fetchval("SELECT request_fingerprint FROM public.chat_requests WHERE idempotency_key = $1", key_valid_no_conv)
        expected_fp_no_conv = compute_request_fingerprint(user_a, "Pristine no-conv prompt", None)
        assert fp_no_conv == expected_fp_no_conv

        # 10. Valid record with non-boolean metadata survived and reconstructed cleanly
        fp_non_bool = await conn.fetchval("SELECT request_fingerprint FROM public.chat_requests WHERE idempotency_key = $1", key_non_bool)
        expected_fp_non_bool = compute_request_fingerprint(user_a, "Safe non-bool metadata prompt", conv_a1)
        assert fp_non_bool == expected_fp_non_bool

        # Assertions on Purged Records (failing ANY provenance check):
        # 3. Cross-user message purged
        assert await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key_cross_user) is None
        # 4. Cross-conversation message purged
        assert await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key_cross_conv) is None
        # 5. Assistant-role message purged
        assert await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key_assistant) is None
        # 6. Edited metadata purged
        assert await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key_edited) is None
        # 7. Content_changed metadata purged
        assert await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key_changed) is None
        # 8. Original_content metadata purged
        assert await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key_orig) is None
        # 9. Missing message purged
        assert await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key_missing) is None

        # Verify permanent strict immutability trigger blocks modifying request_fingerprint
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="request_fingerprint is immutable"):
            await conn.execute("UPDATE public.chat_requests SET request_fingerprint = $1 WHERE idempotency_key = $2", "a" * 64, key_valid_explicit)

        # Verify user message content immutability trigger blocks tampering
        with pytest.raises(asyncpg.exceptions.RaiseError, match="User message content is immutable"):
            await conn.execute("UPDATE public.messages SET content = 'Tampered text' WHERE id = $1", msg_valid_explicit)


@pytest.mark.asyncio
async def test_actual_postgresql_normalization_parity_all_vectors(postgresql_server):
    """Execute public.normalize_chat_content() and public.compute_request_fingerprint_sql() in an isolated database

    and compare directly against Python's compute_request_fingerprint across all test vectors.
    Explicitly proves migrations have been applied to this database.
    """
    async with isolated_postgres_db(postgresql_server, prefix="auren_norm", apply_all_migrations=True) as (conn, db_name):
        # Explicitly prove required migration functions exist in this isolated database
        has_norm_proc = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'normalize_chat_content')")
        has_fp_proc = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'compute_request_fingerprint_sql')")
        assert has_norm_proc is True, f"normalize_chat_content must be established in isolated DB {db_name}"
        assert has_fp_proc is True, f"compute_request_fingerprint_sql must be established in isolated DB {db_name}"

        test_vectors = [
            ("ordinary_spaces_tabs", "   hello \t world \t  "),
            ("crlf_lf_cr", "Line 1\r\nLine 2\nLine 3\rLine 4"),
            ("vt_ff", "Line 1\x0bLine 2\x0cLine 3"),
            ("unicode_whitespace", "\u00a0\u2000Hello\u2003World\u3000\u200a"),
            ("unicode_line_separators", "Line 1\u2028Line 2\u2029Line 3\x85Line 4"),
            ("empty_string", ""),
            ("whitespace_only_ascii", "   \t\r\n\x0b\x0c   "),
            ("whitespace_only_unicode", "\u2000\u2001\u3000\u2028\u2029"),
            ("multiline_trailing_ws", "  Line 1   \r\n\r\n  Line 2  \t \nLine 3   \n\n"),
            ("all_delimiters_combined", "A\r\nB\nC\rD\x0bE\x0cF\x1cG\x1dH\x1eI\x85J\u2028K\u2029L"),
        ]

        for label, raw_text in test_vectors:
            py_norm = "\n".join(line.rstrip() for line in raw_text.strip().splitlines()) if raw_text else ""
            sql_norm = await conn.fetchval("SELECT public.normalize_chat_content($1)", raw_text)
            assert py_norm == sql_norm, f"Normalization mismatch on vector '{label}': py={repr(py_norm)}, sql={repr(sql_norm)}"
            assert py_norm.encode("utf-8") == sql_norm.encode("utf-8")

            user_uuid = uuid.uuid4()
            py_fp = compute_request_fingerprint(user_uuid, raw_text, None)
            sql_fp = await conn.fetchval("SELECT public.compute_request_fingerprint_sql($1, $2, $3)", user_uuid, None, raw_text)
            assert py_fp == sql_fp, f"Fingerprint mismatch on vector '{label}': py={py_fp}, sql={sql_fp}"


@pytest.mark.asyncio
async def test_actual_postgresql_uuid5_parity_multiple_keys(postgresql_server):
    """Execute public.compute_deterministic_conversation_id_sql() in an isolated database

    and compare directly against Python's uuid.uuid5(uuid.NAMESPACE_OID, ...).
    Explicitly proves migrations have been applied to this database.
    """
    async with isolated_postgres_db(postgresql_server, prefix="auren_uuid5", apply_all_migrations=True) as (conn, db_name):
        # Explicitly prove required migration function exists in this isolated database
        has_uuid5_proc = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'compute_deterministic_conversation_id_sql')"
        )
        assert has_uuid5_proc is True, f"compute_deterministic_conversation_id_sql must be established in isolated DB {db_name}"

        test_cases = [
            (uuid.uuid4(), "idemp-standard-1"),
            (uuid.uuid4(), "special-chars:!@#$%^&*()_+{}[]:;<>?,./~`-="),
            (uuid.UUID("00000000-0000-0000-0000-000000000000"), "zero-uuid-test"),
            (uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"), "all-f-uuid-test"),
            (uuid.uuid4(), "a" * 128),
            (uuid.uuid4(), "unicode-key-日本語-äöü-🚀"),
        ]

        for uid, ikey in test_cases:
            expected = uuid.uuid5(uuid.NAMESPACE_OID, f"auren:conv:{uid}:{ikey}")
            actual = await conn.fetchval("SELECT public.compute_deterministic_conversation_id_sql($1, $2)", uid, ikey)
            assert expected == actual, f"UUIDv5 mismatch for {uid}, {ikey}: expected={expected}, actual={actual}"


@pytest.mark.asyncio
async def test_pgcrypto_portability_in_public_and_extensions(postgresql_server):
    """Verify that digest resolution and compute_request_fingerprint_sql execute successfully

    both when pgcrypto is in 'public' and when it is in 'extensions'.
    Each test branch executes in its own isolated ephemeral database.
    """
    migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611150000*.sql")))

    # 1. Database with pgcrypto in public
    async with isolated_postgres_db(postgresql_server, prefix="auren_pgpub", apply_all_migrations=False) as (conn_pub, _):
        await conn_pub.execute("CREATE EXTENSION pgcrypto WITH SCHEMA public")
        schema_pub = await conn_pub.fetchval(
            "SELECT nspname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = 'digest'"
        )
        assert schema_pub == "public"

        await conn_pub.execute(MOCK_AUTH_SQL)
        for mf in migration_files:
            sql_text = Path(mf).read_text(encoding="utf-8")
            await conn_pub.execute(sql_text)

        test_uid = uuid.uuid4()
        fp_pub = await conn_pub.fetchval("SELECT public.compute_request_fingerprint_sql($1, $2, $3)", test_uid, None, "Hello public pgcrypto")
        expected_fp = compute_request_fingerprint(test_uid, "Hello public pgcrypto", None)
        assert fp_pub == expected_fp

    # 2. Database with pgcrypto in extensions (Supabase hosted configuration)
    async with isolated_postgres_db(postgresql_server, prefix="auren_pgext", apply_all_migrations=False) as (conn_ext, _):
        await conn_ext.execute("CREATE SCHEMA extensions")
        await conn_ext.execute("CREATE EXTENSION pgcrypto WITH SCHEMA extensions")
        schema_ext = await conn_ext.fetchval(
            "SELECT nspname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = 'digest'"
        )
        assert schema_ext == "extensions"

        await conn_ext.execute(MOCK_AUTH_SQL)
        for mf in migration_files:
            sql_text = Path(mf).read_text(encoding="utf-8")
            await conn_ext.execute(sql_text)

        fp_ext = await conn_ext.fetchval("SELECT public.compute_request_fingerprint_sql($1, $2, $3)", test_uid, None, "Hello extensions pgcrypto")
        expected_fp_ext = compute_request_fingerprint(test_uid, "Hello extensions pgcrypto", None)
        assert fp_ext == expected_fp_ext
