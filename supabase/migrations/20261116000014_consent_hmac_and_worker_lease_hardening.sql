-- Migration: 014_consent_hmac_and_worker_lease_hardening.sql
-- Description: Binds actual requested date_range in consumed_consent_tokens and RPC,
--              establishes lease-generation token protection against same-worker and cross-worker
--              stale claim execution, and hardens worker SECURITY DEFINER caller authentication using SESSION_USER.

-- ============================================================================
-- 1. BIND DATE_RANGE IN CONSUMED CONSENT TOKENS
-- ============================================================================

ALTER TABLE public.consumed_consent_tokens
    ADD COLUMN IF NOT EXISTS date_range TEXT NOT NULL DEFAULT 'unspecified';

-- Drop previous 5-argument version of consume_journal_consent_rpc
DROP FUNCTION IF EXISTS public.consume_journal_consent_rpc(UUID, UUID, TEXT, TEXT, TIMESTAMPTZ);

-- Recreate consume_journal_consent_rpc with p_date_range binding
CREATE OR REPLACE FUNCTION public.consume_journal_consent_rpc(
    p_nonce UUID,
    p_conversation_id UUID,
    p_idempotency_key TEXT,
    p_scope TEXT,
    p_date_range TEXT,
    p_expires_at TIMESTAMPTZ
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_conv_owner UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    -- Validate non-empty request identity fields
    IF p_nonce IS NULL THEN
        RAISE EXCEPTION 'Consent nonce cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_conversation_id IS NULL THEN
        RAISE EXCEPTION 'Consent conversation_id cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_idempotency_key IS NULL OR length(trim(p_idempotency_key)) = 0 THEN
        RAISE EXCEPTION 'Consent idempotency_key cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_scope IS NULL OR length(trim(p_scope)) = 0 THEN
        RAISE EXCEPTION 'Consent scope cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_date_range IS NULL OR length(trim(p_date_range)) = 0 THEN
        RAISE EXCEPTION 'Consent date_range cannot be empty' USING ERRCODE = '22023';
    END IF;

    -- Validate permitted consent scopes
    IF trim(p_scope) NOT IN ('journal.read', 'journal.read_write', 'journal.summarize') THEN
        RAISE EXCEPTION 'Invalid consent scope: %', p_scope USING ERRCODE = '22023';
    END IF;

    -- Validate token expiration and maximum lifetime window (15 minutes)
    IF p_expires_at IS NULL THEN
        RAISE EXCEPTION 'Consent expires_at cannot be null' USING ERRCODE = '22023';
    END IF;

    IF clock_timestamp() > p_expires_at THEN
        RAISE EXCEPTION 'Consent token has expired' USING ERRCODE = '22023';
    END IF;

    IF p_expires_at > (clock_timestamp() + INTERVAL '15 minutes') THEN
        RAISE EXCEPTION 'Consent token lifetime exceeds maximum permitted window of 15 minutes' USING ERRCODE = '22023';
    END IF;

    -- Verify authenticated user owns the supplied conversation
    SELECT user_id INTO v_conv_owner
    FROM public.conversations
    WHERE id = p_conversation_id;

    IF NOT FOUND OR v_conv_owner != v_user_id THEN
        RAISE EXCEPTION 'Conversation not found or access denied: %', p_conversation_id USING ERRCODE = '42501';
    END IF;

    -- Atomic single-use nonce consumption storing exact requested date range
    INSERT INTO public.consumed_consent_tokens (
        nonce,
        user_id,
        conversation_id,
        idempotency_key,
        scope,
        date_range,
        expires_at
    ) VALUES (
        p_nonce,
        v_user_id,
        p_conversation_id,
        trim(p_idempotency_key),
        trim(p_scope),
        trim(p_date_range),
        p_expires_at
    );

    RETURN TRUE;
EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION 'Consent token has already been consumed (replay rejected)' USING ERRCODE = '23505';
END;
$$;

-- ============================================================================
-- 2. LEASE-GENERATION PROTECTION ON EXTRACTION JOBS
-- ============================================================================

ALTER TABLE public.memory_extraction_jobs
    ADD COLUMN IF NOT EXISTS claim_token UUID DEFAULT gen_random_uuid() NOT NULL;

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_claim_token
    ON public.memory_extraction_jobs(id, claim_token);

-- ============================================================================
-- 3. HARDENED WORKER RPC FUNCTIONS WITH LEASE-GENERATION TOKENS
-- ============================================================================

-- Function: claim_memory_extraction_jobs_rpc
DROP FUNCTION IF EXISTS public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT);

CREATE OR REPLACE FUNCTION public.claim_memory_extraction_jobs_rpc(
    p_worker_id TEXT,
    p_batch_size INT DEFAULT 5,
    p_lease_seconds INT DEFAULT 300
)
RETURNS TABLE (
    id UUID,
    user_id UUID,
    conversation_id UUID,
    source_message_id UUID,
    claim_token UUID,
    attempts INT,
    max_attempts INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    -- Verify caller session identity using SESSION_USER (not CURRENT_USER)
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_worker_id) > 255 THEN
        RAISE EXCEPTION 'Worker ID exceeds maximum length of 255 characters' USING ERRCODE = '22023';
    END IF;

    IF p_batch_size IS NULL OR p_batch_size < 1 OR p_batch_size > 50 THEN
        RAISE EXCEPTION 'Batch size must be between 1 and 50' USING ERRCODE = '22023';
    END IF;

    IF p_lease_seconds IS NULL OR p_lease_seconds < 10 OR p_lease_seconds > 3600 THEN
        RAISE EXCEPTION 'Lease duration must be between 10 and 3600 seconds' USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    WITH candidate AS (
        SELECT j.id AS candidate_id
        FROM public.memory_extraction_jobs j
        WHERE (j.status = 'pending' AND j.scheduled_at <= clock_timestamp())
           OR (j.status = 'processing' AND j.lease_expires_at < clock_timestamp() AND j.attempts < j.max_attempts)
        ORDER BY j.scheduled_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT p_batch_size
    )
    UPDATE public.memory_extraction_jobs j
    SET status = 'processing',
        locked_by = trim(p_worker_id),
        locked_at = clock_timestamp(),
        lease_expires_at = clock_timestamp() + (p_lease_seconds || ' seconds')::INTERVAL,
        claim_token = gen_random_uuid(),  -- Fresh lease-generation token
        attempts = j.attempts + 1,
        updated_at = clock_timestamp()
    FROM candidate
    WHERE j.id = candidate.candidate_id
    RETURNING j.id, j.user_id, j.conversation_id, j.source_message_id, j.claim_token, j.attempts, j.max_attempts;
END;
$$;

-- Function: complete_memory_extraction_job_rpc
DROP FUNCTION IF EXISTS public.complete_memory_extraction_job_rpc(UUID, TEXT);
DROP FUNCTION IF EXISTS public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID);

CREATE OR REPLACE FUNCTION public.complete_memory_extraction_job_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_claim_token UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_job public.memory_extraction_jobs%ROWTYPE;
BEGIN
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    -- Idempotent completion if already completed
    IF v_job.status = 'completed' THEN
        RETURN TRUE;
    END IF;

    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker % (current status: %, locked_by: %)', p_job_id, p_worker_id, v_job.status, v_job.locked_by USING ERRCODE = '42501';
    END IF;

    -- Lease-generation token check: prevents stale worker executions
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has been reclaimed or lease regenerated', p_job_id USING ERRCODE = '22023';
    END IF;

    -- Reject completion if lease has expired
    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; completion rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    UPDATE public.memory_extraction_jobs
    SET status = 'completed',
        locked_by = NULL,
        lease_expires_at = NULL,
        updated_at = clock_timestamp()
    WHERE id = p_job_id;

    RETURN TRUE;
END;
$$;

-- Function: fail_memory_extraction_job_rpc
DROP FUNCTION IF EXISTS public.fail_memory_extraction_job_rpc(UUID, TEXT, TEXT, BOOLEAN);
DROP FUNCTION IF EXISTS public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN);

CREATE OR REPLACE FUNCTION public.fail_memory_extraction_job_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_claim_token UUID,
    p_error TEXT,
    p_retry BOOLEAN DEFAULT TRUE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_job public.memory_extraction_jobs%ROWTYPE;
    v_sanitized_error TEXT;
BEGIN
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker %', p_job_id, p_worker_id USING ERRCODE = '42501';
    END IF;

    -- Lease-generation token check
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has been reclaimed or lease regenerated', p_job_id USING ERRCODE = '22023';
    END IF;

    -- Reject failure update if lease has expired
    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; failure update rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    -- Sanitize and bound error message length (max 1000 characters)
    v_sanitized_error := substr(trim(COALESCE(p_error, 'Extraction failed without specific error details')), 1, 1000);

    IF p_retry AND v_job.attempts < v_job.max_attempts THEN
        UPDATE public.memory_extraction_jobs
        SET status = 'pending',
            locked_by = NULL,
            locked_at = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),  -- Invalidate claim on requeue
            last_error = v_sanitized_error,
            scheduled_at = clock_timestamp() + (POWER(2, v_job.attempts) * 5 || ' seconds')::INTERVAL,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    ELSE
        -- Terminal dead-letter state
        UPDATE public.memory_extraction_jobs
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),  -- Invalidate claim
            last_error = v_sanitized_error,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: insert_extracted_memory_rpc
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, TEXT, TEXT, TEXT, INT, REAL, JSONB);
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB);

CREATE OR REPLACE FUNCTION public.insert_extracted_memory_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_claim_token UUID,
    p_content TEXT,
    p_memory_type TEXT,
    p_category TEXT,
    p_importance INT DEFAULT 3,
    p_confidence REAL DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_job public.memory_extraction_jobs%ROWTYPE;
    v_memory_id UUID;
    v_existing_id UUID;
BEGIN
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker %', p_job_id, p_worker_id USING ERRCODE = '42501';
    END IF;

    -- Lease-generation token check
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has been reclaimed or lease regenerated; ingestion rejected', p_job_id USING ERRCODE = '22023';
    END IF;

    -- Reject ingestion if lease has expired
    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; ingestion rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_content) > 10000 THEN
        RAISE EXCEPTION 'Memory content exceeds maximum permitted length' USING ERRCODE = '22023';
    END IF;

    IF p_memory_type NOT IN ('fact', 'preference', 'goal', 'project', 'context', 'observation') THEN
        RAISE EXCEPTION 'Invalid memory_type: %', p_memory_type USING ERRCODE = '22023';
    END IF;

    IF p_category NOT IN ('personal', 'work', 'technical', 'health_lifestyle', 'financial', 'general') THEN
        RAISE EXCEPTION 'Invalid category: %', p_category USING ERRCODE = '22023';
    END IF;

    IF p_importance IS NOT NULL AND (p_importance < 1 OR p_importance > 5) THEN
        RAISE EXCEPTION 'Importance must be between 1 and 5' USING ERRCODE = '22023';
    END IF;

    -- Deduplication check: return existing ID if identical memory already stored
    SELECT id INTO v_existing_id
    FROM public.memories
    WHERE user_id = v_job.user_id
      AND source_message_id = v_job.source_message_id
      AND content = trim(p_content)
      AND lifecycle_status = 'active';

    IF FOUND THEN
        RETURN v_existing_id;
    END IF;

    INSERT INTO public.memories (
        user_id,
        content,
        memory_type,
        category,
        importance,
        origin,
        confidence,
        confirmation_status,
        lifecycle_status,
        last_confirmed_at,
        source_message_id,
        source_conversation_id,
        metadata
    ) VALUES (
        v_job.user_id,
        trim(p_content),
        p_memory_type,
        p_category,
        COALESCE(p_importance, 3),
        'chat_inferred',
        p_confidence,
        'unconfirmed',
        'active',
        NULL,
        v_job.source_message_id,
        v_job.conversation_id,
        COALESCE(p_metadata, '{}'::jsonb)
    ) RETURNING id INTO v_memory_id;

    UPDATE public.memories SET root_memory_id = v_memory_id WHERE id = v_memory_id;

    RETURN v_memory_id;
END;
$$;

-- Function: reap_stale_extraction_jobs_rpc
CREATE OR REPLACE FUNCTION public.reap_stale_extraction_jobs_rpc(
    p_max_retries INT DEFAULT 3
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_reaped INT := 0;
    v_dead_lettered INT := 0;
BEGIN
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    -- Move exhausted leases to dead_letter (strictly terminal, new claim_token)
    UPDATE public.memory_extraction_jobs
    SET status = 'dead_letter',
        locked_by = NULL,
        lease_expires_at = NULL,
        claim_token = gen_random_uuid(),
        last_error = 'Lease expired and max attempts exceeded',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts >= p_max_retries;

    GET DIAGNOSTICS v_dead_lettered = ROW_COUNT;

    -- Return recoverable expired leases to pending (generates new claim_token)
    UPDATE public.memory_extraction_jobs
    SET status = 'pending',
        locked_by = NULL,
        locked_at = NULL,
        lease_expires_at = NULL,
        claim_token = gen_random_uuid(),
        last_error = 'Lease expired; automatically recovered for retry',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts < p_max_retries;

    GET DIAGNOSTICS v_reaped = ROW_COUNT;

    RETURN v_reaped + v_dead_lettered;
END;
$$;

-- Function: create_system_asserted_memory_rpc (Hardened SESSION_USER identity check)
CREATE OR REPLACE FUNCTION public.create_system_asserted_memory_rpc(
    p_user_id UUID,
    p_content TEXT,
    p_memory_type TEXT,
    p_category TEXT,
    p_importance INT DEFAULT 3,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_memory_id UUID;
BEGIN
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_user_id) THEN
        RAISE EXCEPTION 'Target user % does not exist', p_user_id USING ERRCODE = 'P0002';
    END IF;

    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_content) > 10000 THEN
        RAISE EXCEPTION 'Memory content exceeds maximum permitted length' USING ERRCODE = '22023';
    END IF;

    -- Strict taxonomy validation
    IF p_memory_type NOT IN ('fact', 'preference', 'goal', 'project', 'context', 'observation') THEN
        RAISE EXCEPTION 'Invalid memory_type: %', p_memory_type USING ERRCODE = '22023';
    END IF;

    IF p_category NOT IN ('personal', 'work', 'technical', 'health_lifestyle', 'financial', 'general') THEN
        RAISE EXCEPTION 'Invalid category: %', p_category USING ERRCODE = '22023';
    END IF;

    IF p_importance IS NOT NULL AND (p_importance < 1 OR p_importance > 5) THEN
        RAISE EXCEPTION 'Importance must be between 1 and 5' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.memories (
        user_id,
        content,
        memory_type,
        category,
        importance,
        origin,
        confidence,
        confirmation_status,
        lifecycle_status,
        last_confirmed_at,
        metadata
    ) VALUES (
        p_user_id,
        trim(p_content),
        p_memory_type,
        p_category,
        COALESCE(p_importance, 3),
        'system_asserted',
        1.0,
        'system_asserted',
        'active',
        clock_timestamp(),
        COALESCE(p_metadata, '{}'::jsonb)
    ) RETURNING id INTO v_memory_id;

    UPDATE public.memories SET root_memory_id = v_memory_id WHERE id = v_memory_id;

    RETURN v_memory_id;
END;
$$;

-- Function: activate_embedding_model_rpc (Hardened SESSION_USER identity check)
CREATE OR REPLACE FUNCTION public.activate_embedding_model_rpc(
    p_provider TEXT,
    p_model TEXT,
    p_version TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_purpose TEXT;
    v_dim INT;
BEGIN
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    SELECT purpose, dimension INTO v_purpose, v_dim
    FROM public.embedding_models
    WHERE provider = p_provider AND model = p_model AND version = p_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Embedding model %/%/% not registered', p_provider, p_model, p_version USING ERRCODE = 'P0002';
    END IF;

    UPDATE public.embedding_models
    SET is_active = FALSE
    WHERE purpose = v_purpose AND is_active = TRUE;

    UPDATE public.embedding_models
    SET is_active = TRUE
    WHERE provider = p_provider AND model = p_model AND version = p_version;

    RETURN TRUE;
END;
$$;

-- ============================================================================
-- 4. PERMISSION GRANTS & REVOCATIONS
-- ============================================================================

-- Revoke all by default
REVOKE ALL ON FUNCTION public.consume_journal_consent_rpc(UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.reap_stale_extraction_jobs_rpc(INT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_system_asserted_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.activate_embedding_model_rpc(TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;

-- Grant client consent consumption to authenticated
GRANT EXECUTE ON FUNCTION public.consume_journal_consent_rpc(UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ) TO authenticated;

-- Grant worker RPCs exclusively to auren_worker
GRANT EXECUTE ON FUNCTION public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.reap_stale_extraction_jobs_rpc(INT) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.create_system_asserted_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.activate_embedding_model_rpc(TEXT, TEXT, TEXT) TO auren_worker;
