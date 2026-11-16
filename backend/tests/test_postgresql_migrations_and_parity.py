"""Real PostgreSQL integration tests verifying migration execution, trigger compatibility,

normalization parity, UUIDv5 derivation, and pgcrypto schema portability.
"""

import asyncio
import glob
import hashlib
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


@pytest.fixture(scope="session")
def postgresql_server():
    """Ensure local PostgreSQL server is running for actual database-level testing."""
    PG_SOCK_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if postgres is already accepting connections
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


async def _get_admin_conn(server_info):
    return await asyncpg.connect(host=server_info["host"], port=server_info["port"], database="postgres")


@pytest.mark.asyncio
async def test_fresh_database_migration_001_to_010(postgresql_server):
    """Execute the complete migration sequence (001 through 010) on a fresh database."""
    conn0 = await _get_admin_conn(postgresql_server)
    await conn0.execute("DROP DATABASE IF EXISTS fresh_test_db")
    await conn0.execute("CREATE DATABASE fresh_test_db")
    await conn0.close()

    conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="fresh_test_db")
    
    # Mock auth setup matching Supabase
    await conn.execute("""
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
    """)

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

    await conn.close()


@pytest.mark.asyncio
async def test_legacy_database_migration_with_trigger_compatibility_and_reconstruction(postgresql_server):
    """Execute migrations 001..009, insert legacy records with synthetic fingerprints, and apply migration 010."""
    conn0 = await _get_admin_conn(postgresql_server)
    await conn0.execute("DROP DATABASE IF EXISTS legacy_test_db")
    await conn0.execute("CREATE DATABASE legacy_test_db")
    await conn0.close()

    conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="legacy_test_db")

    # Mock auth setup matching Supabase
    await conn.execute("""
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
    """)

    migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611150000*.sql")))
    # Apply 001..009
    for mf in migration_files[:-1]:
        sql = Path(mf).read_text(encoding="utf-8")
        await conn.execute(sql)

    uid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, $2)", uid, "user@example.com")

    # 1. Pristine request originally submitted WITHOUT conversation ID
    key1 = "legacy-no-conv"
    det_conv1 = uuid.uuid5(uuid.NAMESPACE_OID, f"auren:conv:{uid}:{key1}")
    await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, $3)", det_conv1, uid, "Thread 1")
    msg1 = uuid.uuid4()
    await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, $4, $5)", msg1, det_conv1, uid, "user", "Prompt without conv")
    synth1 = await conn.fetchval("SELECT encode(digest(convert_to($1, 'UTF8'), 'sha256'), 'hex')", f"legacy:{uid}:{key1}")
    await conn.execute(
        "INSERT INTO public.chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint) VALUES ($1, $2, $3, $4, $5, $6)",
        uid, key1, det_conv1, "completed", msg1, synth1
    )

    # 2. Pristine request originally submitted WITH explicit conversation ID
    key2 = "legacy-explicit-conv"
    conv2 = uuid.uuid4()
    await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, $3)", conv2, uid, "Thread 2")
    msg2 = uuid.uuid4()
    await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content) VALUES ($1, $2, $3, $4, $5)", msg2, conv2, uid, "user", "Prompt with explicit conv")
    synth2 = await conn.fetchval("SELECT encode(digest(convert_to($1, 'UTF8'), 'sha256'), 'hex')", f"legacy:{uid}:{key2}")
    await conn.execute(
        "INSERT INTO public.chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint) VALUES ($1, $2, $3, $4, $5, $6)",
        uid, key2, conv2, "completed", msg2, synth2
    )

    # 3. Missing source user message
    key3 = "legacy-missing-msg"
    conv3 = uuid.uuid4()
    fake_msg3 = uuid.uuid4()
    await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, $3)", conv3, uid, "Thread 3")
    synth3 = await conn.fetchval("SELECT encode(digest(convert_to($1, 'UTF8'), 'sha256'), 'hex')", f"legacy:{uid}:{key3}")
    await conn.execute("SET session_replication_role = replica")
    await conn.execute(
        "INSERT INTO public.chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint) VALUES ($1, $2, $3, $4, $5, $6)",
        uid, key3, conv3, "failed", fake_msg3, synth3
    )
    await conn.execute("SET session_replication_role = DEFAULT")

    # 4. Altered user message (edited=true)
    key4 = "legacy-altered-msg"
    conv4 = uuid.uuid4()
    msg4 = uuid.uuid4()
    await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, $3)", conv4, uid, "Thread 4")
    await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, $4, $5, $6)", msg4, conv4, uid, "user", "Altered text", '{"edited": true}')
    synth4 = await conn.fetchval("SELECT encode(digest(convert_to($1, 'UTF8'), 'sha256'), 'hex')", f"legacy:{uid}:{key4}")
    await conn.execute(
        "INSERT INTO public.chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint) VALUES ($1, $2, $3, $4, $5, $6)",
        uid, key4, conv4, "completed", msg4, synth4
    )

    # 5. Invalid metadata string (should not abort, should reconstruct safely)
    key5 = "legacy-invalid-meta"
    conv5 = uuid.uuid4()
    msg5 = uuid.uuid4()
    await conn.execute("INSERT INTO public.conversations (id, user_id, title) VALUES ($1, $2, $3)", conv5, uid, "Thread 5")
    await conn.execute("INSERT INTO public.messages (id, conversation_id, user_id, role, content, metadata) VALUES ($1, $2, $3, $4, $5, $6)", msg5, conv5, uid, "user", "Non-boolean meta prompt", '{"edited": "invalid-bool-val"}')
    synth5 = await conn.fetchval("SELECT encode(digest(convert_to($1, 'UTF8'), 'sha256'), 'hex')", f"legacy:{uid}:{key5}")
    await conn.execute(
        "INSERT INTO public.chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint) VALUES ($1, $2, $3, $4, $5, $6)",
        uid, key5, conv5, "completed", msg5, synth5
    )

    # Now execute migration 010
    sql010 = Path(migration_files[-1]).read_text(encoding="utf-8")
    await conn.execute(sql010)

    # Assertions
    # 1. Rec 1 reconstructed with conv:none
    fp1 = await conn.fetchval("SELECT request_fingerprint FROM public.chat_requests WHERE idempotency_key = $1", key1)
    expected_fp1 = compute_request_fingerprint(uid, "Prompt without conv", None)
    assert fp1 == expected_fp1, f"Expected conv:none fingerprint {expected_fp1}, got {fp1}"

    # 2. Rec 2 reconstructed with conv:<uuid>
    fp2 = await conn.fetchval("SELECT request_fingerprint FROM public.chat_requests WHERE idempotency_key = $1", key2)
    expected_fp2 = compute_request_fingerprint(uid, "Prompt with explicit conv", conv2)
    assert fp2 == expected_fp2, f"Expected conv:<uuid> fingerprint {expected_fp2}, got {fp2}"

    # 3. Rec 3 purged per compatibility policy
    req3 = await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key3)
    assert req3 is None, "Expected orphaned request to be purged"

    # 4. Rec 4 purged per compatibility policy (altered provenance)
    req4 = await conn.fetchval("SELECT idempotency_key FROM public.chat_requests WHERE idempotency_key = $1", key4)
    assert req4 is None, "Expected altered request to be purged"

    # 5. Rec 5 reconstructed safely without failure on invalid metadata
    fp5 = await conn.fetchval("SELECT request_fingerprint FROM public.chat_requests WHERE idempotency_key = $1", key5)
    expected_fp5 = compute_request_fingerprint(uid, "Non-boolean meta prompt", conv5)
    assert fp5 == expected_fp5

    # 6. Verify permanent strict immutability trigger blocks modifying request_fingerprint
    with pytest.raises(asyncpg.exceptions.InvalidParameterValueError, match="request_fingerprint is immutable"):
        await conn.execute("UPDATE public.chat_requests SET request_fingerprint = $1 WHERE idempotency_key = $2", "b" * 64, key1)

    # 7. Verify user message content immutability trigger blocks modifications
    with pytest.raises(asyncpg.exceptions.RaiseError, match="User message content is immutable"):
        await conn.execute("UPDATE public.messages SET content = $1 WHERE id = $2", "Tampered content", msg1)

    await conn.close()


@pytest.mark.asyncio
async def test_actual_postgresql_normalization_parity_all_vectors(postgresql_server):
    """Execute public.normalize_chat_content() and public.compute_request_fingerprint_sql() in PostgreSQL

    and compare directly against Python's compute_request_fingerprint across all test vectors.
    """
    conn0 = await _get_admin_conn(postgresql_server)
    conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="postgres")

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

    await conn.close()
    await conn0.close()


@pytest.mark.asyncio
async def test_actual_postgresql_uuid5_parity_multiple_keys(postgresql_server):
    """Execute public.compute_deterministic_conversation_id_sql() in PostgreSQL

    and compare directly against Python's uuid.uuid5(uuid.NAMESPACE_OID, ...).
    """
    conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="postgres")

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

    await conn.close()


@pytest.mark.asyncio
async def test_pgcrypto_portability_in_public_and_extensions(postgresql_server):
    """Verify that digest resolution and compute_request_fingerprint_sql execute successfully

    both when pgcrypto is in 'public' and when it is in 'extensions'.
    """
    conn0 = await _get_admin_conn(postgresql_server)
    migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611150000*.sql")))

    auth_sql = """
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

    # 1. Database with pgcrypto in public
    await conn0.execute("DROP DATABASE IF EXISTS test_pg_pub_db")
    await conn0.execute("CREATE DATABASE test_pg_pub_db")
    conn_pub = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="test_pg_pub_db")
    await conn_pub.execute("CREATE EXTENSION pgcrypto WITH SCHEMA public")
    schema_pub = await conn_pub.fetchval("SELECT nspname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = 'digest'")
    assert schema_pub == "public"

    await conn_pub.execute(auth_sql)
    for mf in migration_files:
        sql_text = Path(mf).read_text(encoding="utf-8")
        await conn_pub.execute(sql_text)

    # Test execution in public
    test_uid = uuid.uuid4()
    fp_pub = await conn_pub.fetchval("SELECT public.compute_request_fingerprint_sql($1, $2, $3)", test_uid, None, "Hello public pgcrypto")
    expected_fp = compute_request_fingerprint(test_uid, "Hello public pgcrypto", None)
    assert fp_pub == expected_fp
    await conn_pub.close()

    # 2. Database with pgcrypto in extensions (Supabase configuration)
    await conn0.execute("DROP DATABASE IF EXISTS test_pg_ext_db")
    await conn0.execute("CREATE DATABASE test_pg_ext_db")
    conn_ext = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="test_pg_ext_db")
    await conn_ext.execute("CREATE SCHEMA extensions")
    await conn_ext.execute("CREATE EXTENSION pgcrypto WITH SCHEMA extensions")
    schema_ext = await conn_ext.fetchval("SELECT nspname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = 'digest'")
    assert schema_ext == "extensions"

    await conn_ext.execute(auth_sql)
    for mf in migration_files:
        sql_text = Path(mf).read_text(encoding="utf-8")
        await conn_ext.execute(sql_text)

    # Test execution in extensions
    fp_ext = await conn_ext.fetchval("SELECT public.compute_request_fingerprint_sql($1, $2, $3)", test_uid, None, "Hello extensions pgcrypto")
    expected_fp_ext = compute_request_fingerprint(test_uid, "Hello extensions pgcrypto", None)
    assert fp_ext == expected_fp_ext
    await conn_ext.close()

    await conn0.close()
