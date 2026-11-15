-- Migration: 010_correct_legacy_fingerprints_and_pgcrypto.sql
-- Description: Correct legacy fingerprint backfill matching application normalization semantics,
--              preserve original request conversation-ID semantics (conv:none vs conv:<uuid>),
--              safely resolve pgcrypto without static schema qualifications, enforce user-message
--              immutability, and apply strict compatibility policies for unreconstructable records.

-- ============================================================================
-- 1. VERIFY PGCRYPTO EXTENSION DEPENDENCY & DYNAMIC SCHEMA RESOLUTION
-- ============================================================================

-- Ensure pgcrypto extension is installed
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Dynamically configure session search_path to locate digest regardless of whether
-- pgcrypto was installed in public or extensions, avoiding static schema qualifications.
DO $$
DECLARE
    v_schema TEXT;
BEGIN
    SELECT n.nspname INTO v_schema
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE p.proname = 'digest'
    LIMIT 1;

    IF v_schema IS NOT NULL AND v_schema NOT IN ('public', 'pg_catalog') THEN
        EXECUTE 'SET search_path TO ' || current_setting('search_path') || ', ' || quote_ident(v_schema);
    END IF;
END;
$$;

-- ============================================================================
-- 2. NORMALIZATION & FINGERPRINT FUNCTIONS (EXACT APPLICATION PARITY)
-- ============================================================================

-- Function: normalize_chat_content
-- Matches Python exactly: "\n".join(line.rstrip() for line in content.strip().splitlines())
-- Handles all 29 Unicode whitespace characters and all 11 line boundary representations.
CREATE OR REPLACE FUNCTION public.normalize_chat_content(p_content TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_whitespace TEXT;
    v_line_sep TEXT;
    v_trimmed TEXT;
    v_lines TEXT[];
    v_line TEXT;
    v_cleaned TEXT[] := ARRAY[]::TEXT[];
BEGIN
    IF p_content IS NULL THEN
        RETURN '';
    END IF;

    -- All 29 Unicode whitespace characters matching Python's str.isspace()
    v_whitespace := chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288);

    -- 1. Strip leading and trailing whitespace from the complete content
    v_trimmed := trim(both v_whitespace FROM p_content);
    IF v_trimmed = '' THEN
        RETURN '';
    END IF;

    -- All 11 line boundary representations recognized by Python's str.splitlines()
    -- \r\n (CRLF) is first to avoid splitting into two empty lines
    v_line_sep := chr(13) || chr(10) || '|[' || chr(10) || chr(13) || chr(11) || chr(12) || chr(28) || chr(29) || chr(30) || chr(133) || chr(8232) || chr(8233) || ']';

    -- 2. Split into lines
    v_lines := regexp_split_to_array(v_trimmed, v_line_sep);
    FOREACH v_line IN ARRAY v_lines LOOP
        -- Remove trailing whitespace from each line
        v_cleaned := array_append(v_cleaned, rtrim(v_line, v_whitespace));
    END LOOP;

    -- 3. Join lines using newline character
    RETURN array_to_string(v_cleaned, chr(10));
END;
$$;

-- Function: compute_deterministic_conversation_id_sql
-- Generates exact RFC 4122 UUIDv5 for namespace OID: 6ba7b812-9dad-11d1-80b4-00c04fd430c8
-- Matching Python: uuid.uuid5(uuid.NAMESPACE_OID, f"auren:conv:{user_id}:{idempotency_key}")
CREATE OR REPLACE FUNCTION public.compute_deterministic_conversation_id_sql(
    p_user_id UUID,
    p_idempotency_key TEXT
)
RETURNS UUID
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_data BYTEA;
    v_hash BYTEA;
    v_hex TEXT;
    v_b6_v5 TEXT;
    v_b8_var TEXT;
    v_b8_int INT;
    v_uuid_str TEXT;
BEGIN
    -- Namespace OID bytes: 6ba7b8129dad11d180b400c04fd430c8
    v_data := decode('6ba7b8129dad11d180b400c04fd430c8', 'hex') || 
              convert_to('auren:conv:' || p_user_id::TEXT || ':' || p_idempotency_key, 'UTF8');
    v_hash := digest(v_data, 'sha1');
    v_hex := encode(v_hash, 'hex');

    -- Version 5: high nibble of byte 7 (0-indexed char 13..14) is 5
    v_b6_v5 := '5' || substr(v_hex, 14, 1);

    -- Variant RFC 4122: high 2 bits of byte 9 (0-indexed char 17..18) are 10
    v_b8_int := ('x' || substr(v_hex, 17, 2))::bit(8)::int;
    v_b8_int := (v_b8_int & 63) | 128;
    v_b8_var := lpad(to_hex(v_b8_int), 2, '0');

    v_uuid_str := substr(v_hex, 1, 8) || '-' ||
                  substr(v_hex, 9, 4) || '-' ||
                  v_b6_v5 || substr(v_hex, 15, 2) || '-' ||
                  v_b8_var || substr(v_hex, 19, 2) || '-' ||
                  substr(v_hex, 21, 12);

    RETURN v_uuid_str::UUID;
END;
$$;

-- Function: compute_request_fingerprint_sql
-- Matches Python: hashlib.sha256(f"user:{user_id}|conv:{conv_part}|content:{normalized}").hexdigest()
CREATE OR REPLACE FUNCTION public.compute_request_fingerprint_sql(
    p_user_id UUID,
    p_conversation_id UUID,
    p_content TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_normalized TEXT;
    v_conv_part TEXT;
    v_payload TEXT;
    v_hash BYTEA;
BEGIN
    v_normalized := public.normalize_chat_content(p_content);
    v_conv_part := CASE WHEN p_conversation_id IS NOT NULL THEN p_conversation_id::TEXT ELSE 'none' END;
    v_payload := 'user:' || p_user_id::TEXT || '|conv:' || v_conv_part || '|content:' || v_normalized;

    v_hash := digest(convert_to(v_payload, 'UTF8'), 'sha256');

    RETURN encode(v_hash, 'hex');
END;
$$;

-- ============================================================================
-- 3. PROVENANCE INTEGRITY & IMMUTABILITY TRIGGER ON USER MESSAGES
-- ============================================================================

-- Function: handle_messages_immutability
-- Enforces that user message content is immutable once created.
CREATE OR REPLACE FUNCTION public.handle_messages_immutability()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF OLD.role = 'user' AND NEW.content IS DISTINCT FROM OLD.content THEN
        RAISE EXCEPTION 'User message content is immutable and cannot be modified';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_messages_user_content_immutability ON public.messages;
CREATE TRIGGER trg_messages_user_content_immutability
BEFORE UPDATE ON public.messages
FOR EACH ROW
EXECUTE FUNCTION public.handle_messages_immutability();

-- ============================================================================
-- 4. LEGACY FINGERPRINT RECONSTRUCTION & COMPATIBILITY POLICY
-- ============================================================================

-- Step 4a: Compatibility Policy for unreconstructable legacy records:
-- If a legacy record's user_message_id does not exist in public.messages, OR if the message's
-- provenance is broken (e.g. edited/altered content), original content cannot be proved.
-- To avoid fabricating false fingerprints that cause permanent HTTP 409 collisions on retry,
-- unreconstructable records are purged from chat_requests.
DELETE FROM public.chat_requests cr
WHERE NOT EXISTS (
    SELECT 1 FROM public.messages m
    WHERE m.id = cr.user_message_id
      AND COALESCE((m.metadata->>'edited')::boolean, FALSE) IS FALSE
      AND COALESCE((m.metadata->>'content_changed')::boolean, FALSE) IS FALSE
);

-- Step 4b: Reconstruct fingerprints for all pristine legacy records:
-- Determine whether the original request supplied a conversation ID:
--   - If cr.conversation_id == deterministic_conv_id: request supplied NO conversation ID -> conv:none (NULL)
--   - If cr.conversation_id != deterministic_conv_id: request supplied explicit conversation ID -> conv:<uuid>
UPDATE public.chat_requests cr
SET request_fingerprint = public.compute_request_fingerprint_sql(
    cr.user_id,
    CASE 
        WHEN cr.conversation_id = public.compute_deterministic_conversation_id_sql(cr.user_id, cr.idempotency_key)
        THEN NULL
        ELSE cr.conversation_id
    END,
    m.content
)
FROM public.messages m
WHERE cr.user_message_id = m.id
  AND (
      cr.request_fingerprint IS NULL
      OR cr.request_fingerprint !~ '^[0-9a-fA-F]{64}$'
      -- Also recompute if it was the temporary synthetic digest from migration 009
      OR cr.request_fingerprint = encode(digest(convert_to('legacy:' || cr.user_id::text || ':' || cr.idempotency_key, 'UTF8'), 'sha256'), 'hex')
  );

-- Any remaining records with NULL fingerprint cannot be reconstructed: purge per compatibility policy
DELETE FROM public.chat_requests
WHERE request_fingerprint IS NULL;

-- ============================================================================
-- 5. ENFORCE STRICT TABLE CONSTRAINTS
-- ============================================================================

ALTER TABLE public.chat_requests
    ALTER COLUMN request_fingerprint SET NOT NULL;

ALTER TABLE public.chat_requests
    DROP CONSTRAINT IF EXISTS chat_requests_fingerprint_hex_check;

ALTER TABLE public.chat_requests
    ADD CONSTRAINT chat_requests_fingerprint_hex_check
    CHECK (request_fingerprint ~ '^[0-9a-fA-F]{64}$');

-- ============================================================================
-- 6. REINFORCE SEARCH PATH ON ALL SECURITY DEFINER RPCS
-- ============================================================================

ALTER FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.complete_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.fail_chat_request(TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.interrupt_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.retry_chat_request(TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.reconcile_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;

-- ============================================================================
-- 7. AUDIT & RE-ASSERT LEAST-PRIVILEGE TABLE & RPC PERMISSIONS
-- ============================================================================

-- Ensure all direct mutations on chat_requests remain strictly revoked
REVOKE INSERT, UPDATE, DELETE ON public.chat_requests FROM authenticated, anon, public;
GRANT SELECT ON public.chat_requests TO authenticated;

-- Ensure execute on all lifecycle RPCs is granted strictly to authenticated
REVOKE ALL ON FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.complete_chat_request(TEXT, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.fail_chat_request(TEXT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.interrupt_chat_request(TEXT, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.retry_chat_request(TEXT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.reconcile_chat_request(TEXT, UUID) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.complete_chat_request(TEXT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fail_chat_request(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.interrupt_chat_request(TEXT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.retry_chat_request(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.reconcile_chat_request(TEXT, UUID) TO authenticated;
