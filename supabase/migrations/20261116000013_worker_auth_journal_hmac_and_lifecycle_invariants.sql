-- Migration: 013_worker_auth_journal_hmac_and_lifecycle_invariants.sql
-- Description: Establishes auren_worker role authentication boundaries, hardens worker job lease
--              validation and reclamation, corrects legacy records to NULL confidence, strengthens
--              system-asserted validation and lifecycle invariants, and prevents unauthorized role assumption.

-- ============================================================================
-- 1. WORKER ROLE AUTHENTICATION BOUNDARY & PREVENTING ASSUMPTION
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker') THEN
        CREATE ROLE auren_worker NOLOGIN NOINHERIT;
    END IF;
END $$;

-- Prevent ordinary authenticated or anonymous users from assuming or inheriting the worker role
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'REVOKE auren_worker FROM authenticated';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE auren_worker FROM anon';
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Ensure schema usage
GRANT USAGE ON SCHEMA public TO auren_worker;

-- ============================================================================
-- 2. CORRECT LEGACY CONFIDENCE TO NULL (UNKNOWN CONFIDENCE)
-- ============================================================================

-- Drop NOT NULL and DEFAULT on confidence to properly represent unknown confidence
ALTER TABLE public.memories
    ALTER COLUMN confidence DROP NOT NULL,
    ALTER COLUMN confidence DROP DEFAULT;

-- Update constraint to allow NULL confidence
ALTER TABLE public.memories
    DROP CONSTRAINT IF EXISTS memories_confidence_range_check;

ALTER TABLE public.memories
    ADD CONSTRAINT memories_confidence_range_check
        CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0));

-- Eliminate fabricated certainty: legacy imported records must have NULL confidence
UPDATE public.memories
SET confidence = NULL
WHERE origin = 'legacy_import';

-- ============================================================================
-- 3. HARDENED LIFECYCLE INVARIANTS & IMMUTABILITY GUARD
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_memories_lifecycle_guard()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Immutable user_id
    IF OLD.user_id != NEW.user_id THEN
        RAISE EXCEPTION 'Cannot modify memory owner (user_id is immutable)' USING ERRCODE = '42501';
    END IF;

    -- Root memory ID immutability
    IF OLD.root_memory_id IS NOT NULL AND NEW.root_memory_id != OLD.root_memory_id THEN
        RAISE EXCEPTION 'Cannot modify root_memory_id of existing memory' USING ERRCODE = '22023';
    END IF;

    -- Superseded memories are strictly terminal (cannot be reactivated or mutated)
    IF OLD.lifecycle_status = 'superseded' AND (NEW.lifecycle_status != 'superseded' OR OLD.content != NEW.content) THEN
        RAISE EXCEPTION 'Illegal lifecycle transition: superseded memories are terminal' USING ERRCODE = '22023';
    END IF;

    -- Forgotten memories are strictly terminal
    IF OLD.lifecycle_status = 'forgotten' AND NEW.lifecycle_status != 'forgotten' THEN
        RAISE EXCEPTION 'Illegal lifecycle transition: forgotten memories are terminal' USING ERRCODE = '22023';
    END IF;

    -- Rejected confirmation status is strictly terminal
    IF OLD.confirmation_status = 'rejected' AND (NEW.confirmation_status != 'rejected' OR NEW.lifecycle_status = 'active') THEN
        RAISE EXCEPTION 'Illegal transition: rejected memories cannot be confirmed, reactivated, or superseded' USING ERRCODE = '22023';
    END IF;

    -- Rejected lifecycle status is strictly terminal
    IF OLD.lifecycle_status = 'rejected' AND NEW.lifecycle_status != 'rejected' THEN
        RAISE EXCEPTION 'Illegal lifecycle transition: rejected memories cannot be reactivated' USING ERRCODE = '22023';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_memories_lifecycle_guard ON public.memories;
CREATE TRIGGER trg_memories_lifecycle_guard
    BEFORE UPDATE ON public.memories
    FOR EACH ROW EXECUTE FUNCTION public.fn_memories_lifecycle_guard();

-- ============================================================================
-- 4. HARDEN SYSTEM ASSERTED MEMORY CREATION (WORKER-ONLY)
-- ============================================================================

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
    -- Verify caller identity: must be auren_worker or superuser
    IF NOT (
        CURRENT_USER = 'auren_worker'
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(CURRENT_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
        OR COALESCE(current_setting('request.jwt.claim.role', true), '') IN ('service_role', 'auren_worker')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller does not have auren_worker role' USING ERRCODE = '42501';
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

    -- Strict validation of memory type, category, and importance
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

-- ============================================================================
-- 5. HARDEN WORKER QUEUE RPCS: LEASE EXPIRY & STALE WORKER REJECTION
-- ============================================================================

-- Function: claim_memory_extraction_jobs_rpc
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
    attempts INT,
    max_attempts INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    -- Verify caller identity: must be auren_worker or superuser
    IF NOT (
        CURRENT_USER = 'auren_worker'
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(CURRENT_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
        OR COALESCE(current_setting('request.jwt.claim.role', true), '') IN ('service_role', 'auren_worker')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller does not have auren_worker role' USING ERRCODE = '42501';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_worker_id) > 255 THEN
        RAISE EXCEPTION 'Worker ID exceeds maximum length' USING ERRCODE = '22023';
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
        attempts = j.attempts + 1,
        updated_at = clock_timestamp()
    FROM candidate
    WHERE j.id = candidate.candidate_id
    RETURNING j.id, j.user_id, j.conversation_id, j.source_message_id, j.attempts, j.max_attempts;
END;
$$;

-- Function: complete_memory_extraction_job_rpc
CREATE OR REPLACE FUNCTION public.complete_memory_extraction_job_rpc(
    p_job_id UUID,
    p_worker_id TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_job public.memory_extraction_jobs%ROWTYPE;
BEGIN
    -- Verify caller identity: must be auren_worker or superuser
    IF NOT (
        CURRENT_USER = 'auren_worker'
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(CURRENT_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
        OR COALESCE(current_setting('request.jwt.claim.role', true), '') IN ('service_role', 'auren_worker')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller does not have auren_worker role' USING ERRCODE = '42501';
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
CREATE OR REPLACE FUNCTION public.fail_memory_extraction_job_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
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
BEGIN
    -- Verify caller identity: must be auren_worker or superuser
    IF NOT (
        CURRENT_USER = 'auren_worker'
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(CURRENT_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
        OR COALESCE(current_setting('request.jwt.claim.role', true), '') IN ('service_role', 'auren_worker')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller does not have auren_worker role' USING ERRCODE = '42501';
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

    -- Reject failure update if lease has expired
    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; failure update rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    IF p_retry AND v_job.attempts < v_job.max_attempts THEN
        UPDATE public.memory_extraction_jobs
        SET status = 'pending',
            locked_by = NULL,
            locked_at = NULL,
            lease_expires_at = NULL,
            last_error = p_error,
            scheduled_at = clock_timestamp() + (POWER(2, v_job.attempts) * 5 || ' seconds')::INTERVAL,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    ELSE
        UPDATE public.memory_extraction_jobs
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            last_error = p_error,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    END IF;

    RETURN TRUE;
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
    -- Verify caller identity: must be auren_worker or superuser
    IF NOT (
        CURRENT_USER = 'auren_worker'
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(CURRENT_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
        OR COALESCE(current_setting('request.jwt.claim.role', true), '') IN ('service_role', 'auren_worker')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller does not have auren_worker role' USING ERRCODE = '42501';
    END IF;

    -- Move exhausted leases to dead_letter (strictly terminal)
    UPDATE public.memory_extraction_jobs
    SET status = 'dead_letter',
        locked_by = NULL,
        lease_expires_at = NULL,
        last_error = 'Lease expired and max attempts exceeded',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts >= p_max_retries;

    GET DIAGNOSTICS v_dead_lettered = ROW_COUNT;

    -- Return recoverable expired leases to pending
    UPDATE public.memory_extraction_jobs
    SET status = 'pending',
        locked_by = NULL,
        locked_at = NULL,
        lease_expires_at = NULL,
        last_error = 'Lease expired; automatically recovered for retry',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts < p_max_retries;

    GET DIAGNOSTICS v_reaped = ROW_COUNT;

    RETURN v_reaped + v_dead_lettered;
END;
$$;

-- Function: insert_extracted_memory_rpc
CREATE OR REPLACE FUNCTION public.insert_extracted_memory_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
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
    -- Verify caller identity: must be auren_worker or superuser
    IF NOT (
        CURRENT_USER = 'auren_worker'
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(CURRENT_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
        OR COALESCE(current_setting('request.jwt.claim.role', true), '') IN ('service_role', 'auren_worker')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller does not have auren_worker role' USING ERRCODE = '42501';
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

    -- Reject ingestion if lease has expired
    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; ingestion rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    -- Deduplication check
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

-- Function: activate_embedding_model_rpc
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
    -- Verify caller identity: must be auren_worker or superuser
    IF NOT (
        CURRENT_USER = 'auren_worker'
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(CURRENT_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
        OR COALESCE(current_setting('request.jwt.claim.role', true), '') IN ('service_role', 'auren_worker')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller does not have auren_worker role' USING ERRCODE = '42501';
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
-- 6. STRICT RE-ENFORCEMENT OF PERMISSIONS
-- ============================================================================

REVOKE ALL ON FUNCTION public.create_system_asserted_memory_rpc FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_memory_extraction_jobs_rpc FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_memory_extraction_job_rpc FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fail_memory_extraction_job_rpc FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.reap_stale_extraction_jobs_rpc FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.insert_extracted_memory_rpc FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.activate_embedding_model_rpc FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.create_system_asserted_memory_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.claim_memory_extraction_jobs_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.complete_memory_extraction_job_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.fail_memory_extraction_job_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.reap_stale_extraction_jobs_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.activate_embedding_model_rpc TO auren_worker;
