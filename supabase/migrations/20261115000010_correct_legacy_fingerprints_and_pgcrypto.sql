-- Migration: 010_correct_legacy_fingerprints_and_pgcrypto.sql
-- Description: Correct legacy fingerprint backfill matching application normalization semantics,
--              verify pgcrypto extension resolution, and enforce strict privilege boundaries.

-- ============================================================================
-- 1. VERIFY PGCRYPTO EXTENSION DEPENDENCY & RESOLUTION
-- ============================================================================

-- Ensure pgcrypto extension is installed
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 2. NORMALIZATION & FINGERPRINT FUNCTIONS (EXACT APPLICATION PARITY)
-- ============================================================================

-- Function: normalize_chat_content
-- Matches Python: "\n".join(line.rstrip() for line in content.strip().splitlines())
CREATE OR REPLACE FUNCTION public.normalize_chat_content(p_content TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_trimmed TEXT;
    v_lines TEXT[];
    v_line TEXT;
    v_cleaned TEXT[] := ARRAY[]::TEXT[];
BEGIN
    IF p_content IS NULL THEN
        RETURN '';
    END IF;

    -- 1. Strip leading and trailing whitespace from the complete content
    v_trimmed := trim(both E' \t\r\n' FROM p_content);
    IF v_trimmed = '' THEN
        RETURN '';
    END IF;

    -- 2. Split into lines (handling \r\n, \n, or \r)
    v_lines := regexp_split_to_array(v_trimmed, E'\r\n|\n|\r');
    FOREACH v_line IN ARRAY v_lines LOOP
        -- Remove trailing whitespace from each line
        v_cleaned := array_append(v_cleaned, rtrim(v_line, E' \t\r\n'));
    END LOOP;

    -- 3. Join lines using newline character
    RETURN array_to_string(v_cleaned, E'\n');
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

    -- Resolve digest safely across extensions and public schemas
    BEGIN
        SELECT extensions.digest(convert_to(v_payload, 'UTF8'), 'sha256') INTO v_hash;
    EXCEPTION WHEN undefined_function OR invalid_schema_name THEN
        BEGIN
            SELECT public.digest(convert_to(v_payload, 'UTF8'), 'sha256') INTO v_hash;
        EXCEPTION WHEN undefined_function THEN
            SELECT digest(convert_to(v_payload, 'UTF8'), 'sha256') INTO v_hash;
        END;
    END;

    RETURN encode(v_hash, 'hex');
END;
$$;

-- ============================================================================
-- 3. LEGACY FINGERPRINT RECONSTRUCTION & COMPATIBILITY POLICY
-- ============================================================================

-- Step 3a: Reconstruct fingerprints for all legacy records whose source user message exists
UPDATE public.chat_requests cr
SET request_fingerprint = public.compute_request_fingerprint_sql(cr.user_id, cr.conversation_id, m.content)
FROM public.messages m
WHERE cr.user_message_id = m.id
  AND (
      cr.request_fingerprint IS NULL
      OR cr.request_fingerprint !~ '^[0-9a-fA-F]{64}$'
      -- Also recompute if it was set to the temporary synthetic hash from 009
      OR cr.request_fingerprint = encode(
          CASE
              WHEN EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'digest' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'extensions'))
              THEN extensions.digest(convert_to('legacy:' || cr.user_id::text || ':' || cr.idempotency_key, 'UTF8'), 'sha256')
              ELSE public.digest(convert_to('legacy:' || cr.user_id::text || ':' || cr.idempotency_key, 'UTF8'), 'sha256')
          END, 'hex'
      )
  );

-- Step 3b: Compatibility Policy for unreconstructable legacy records:
-- If a legacy record's user_message_id does not exist in public.messages, its original content
-- cannot be cryptographically proven or recovered. In accordance with the ON DELETE CASCADE contract,
-- orphaned records without a source message are purged to avoid fake fingerprints and false conflicts.
DELETE FROM public.chat_requests cr
WHERE NOT EXISTS (
    SELECT 1 FROM public.messages m WHERE m.id = cr.user_message_id
);

-- ============================================================================
-- 4. ENFORCE STRICT TABLE CONSTRAINTS
-- ============================================================================

ALTER TABLE public.chat_requests
    ALTER COLUMN request_fingerprint SET NOT NULL;

ALTER TABLE public.chat_requests
    DROP CONSTRAINT IF EXISTS chat_requests_fingerprint_hex_check;

ALTER TABLE public.chat_requests
    ADD CONSTRAINT chat_requests_fingerprint_hex_check
    CHECK (request_fingerprint ~ '^[0-9a-fA-F]{64}$');

-- ============================================================================
-- 5. REINFORCE SEARCH PATH ON ALL SECURITY DEFINER RPCS
-- ============================================================================

ALTER FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.complete_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.fail_chat_request(TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.interrupt_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.retry_chat_request(TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.reconcile_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;

-- ============================================================================
-- 6. AUDIT & RE-ASSERT LEAST-PRIVILEGE TABLE & RPC PERMISSIONS
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

