-- ============================================================================
-- Migration: 016_persistent_memory_pipeline_and_hybrid_retrieval.sql
-- Description: Persistent memory extraction outbox, hybrid retrieval scoring,
--              worker claim-token fencing, source message quarantine,
--              epistemic provenance enforcement, and terminal lifecycle cleanup.
-- Baseline: 98c87a71ef5e24ba8dafb8845ba4c5c8f65edd1c
-- ============================================================================

-- ============================================================================
-- 1. FAIL-CLOSED METADATA BOOLEAN PARSER
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_safe_jsonb_bool(
    p_metadata JSONB,
    p_key TEXT,
    p_default_if_missing BOOLEAN,
    p_default_if_malformed BOOLEAN
)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_val JSONB;
BEGIN
    IF p_metadata IS NULL OR jsonb_typeof(p_metadata) != 'object' THEN
        RETURN p_default_if_malformed;
    END IF;

    IF NOT (p_metadata ? p_key) THEN
        RETURN p_default_if_missing;
    END IF;

    v_val := p_metadata -> p_key;
    IF jsonb_typeof(v_val) = 'boolean' THEN
        RETURN (v_val)::BOOLEAN;
    END IF;

    RETURN p_default_if_malformed;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_safe_jsonb_bool(JSONB, TEXT, BOOLEAN, BOOLEAN) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.fn_safe_jsonb_bool(JSONB, TEXT, BOOLEAN, BOOLEAN) TO authenticated, auren_worker;

-- ============================================================================
-- 2. SCHEMA EXTENSIONS: CHAT REQUESTS & EXTRACTION JOBS
-- ============================================================================

-- Add authoritative server-side journal classification to chat_requests
ALTER TABLE public.chat_requests
    ADD COLUMN IF NOT EXISTS contains_journal_data BOOLEAN DEFAULT FALSE NOT NULL;

-- Bind extraction jobs to idempotency key and source chat request
ALTER TABLE public.memory_extraction_jobs
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS completed_token UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'memory_extraction_jobs_chat_request_fk'
    ) THEN
        ALTER TABLE public.memory_extraction_jobs
            ADD CONSTRAINT memory_extraction_jobs_chat_request_fk
            FOREIGN KEY (user_id, idempotency_key)
            REFERENCES public.chat_requests(user_id, idempotency_key)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_user_idemp
    ON public.memory_extraction_jobs(user_id, idempotency_key);

-- ============================================================================
-- 3. TRANSACTIONAL OUTBOX: HARDENED COMPLETE_CHAT_REQUEST RPC
-- ============================================================================

-- Atomically completes a chat request and enqueues extraction job if eligible.
-- Preserves complete_chat_request(TEXT, UUID) signature and JSONB return contract.
CREATE OR REPLACE FUNCTION public.complete_chat_request(
    p_idempotency_key TEXT,
    p_assistant_message_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_req public.chat_requests%ROWTYPE;
    v_asst_msg public.messages%ROWTYPE;
    v_user_msg public.messages%ROWTYPE;
    v_has_consumed_consent BOOLEAN;
    v_user_journal_flag BOOLEAN;
    v_asst_journal_flag BOOLEAN;
    v_is_journal BOOLEAN;
    v_user_interrupted BOOLEAN;
    v_asst_interrupted BOOLEAN;
    v_is_interrupted BOOLEAN;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    IF p_assistant_message_id IS NULL THEN
        RAISE EXCEPTION 'assistant_message_id is required to complete request' USING ERRCODE = '22023';
    END IF;

    IF p_idempotency_key IS NULL OR length(trim(p_idempotency_key)) = 0 THEN
        RAISE EXCEPTION 'idempotency_key cannot be empty' USING ERRCODE = '22023';
    END IF;

    -- Lock request row exclusively
    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    -- Enforce terminal state: completed request cannot be updated with a different message.
    -- Idempotent retry returns existing request unchanged without backfilling or mutating outbox.
    IF v_req.status = 'completed' THEN
        IF v_req.assistant_message_id = p_assistant_message_id THEN
            RETURN to_jsonb(v_req);
        ELSE
            RAISE EXCEPTION 'Completed request cannot be updated with a different assistant message'
                USING ERRCODE = '22023';
        END IF;
    END IF;

    -- Ordinary completion RPC ONLY allows processing -> completed.
    IF v_req.status != 'processing' THEN
        RAISE EXCEPTION 'Invalid status transition: cannot complete request with status %', v_req.status
            USING ERRCODE = '22023';
    END IF;

    -- Verify assistant_message_id belongs to caller, belongs to conversation, and has role='assistant'
    SELECT * INTO v_asst_msg
    FROM public.messages
    WHERE id = p_assistant_message_id
      AND user_id = v_user_id
      AND conversation_id = v_req.conversation_id
      AND role = 'assistant';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid assistant_message_id: message not found in thread or not an assistant response'
            USING ERRCODE = '42501';
    END IF;

    -- Verify source user_message_id belongs to caller, belongs to conversation, and has role='user'
    SELECT * INTO v_user_msg
    FROM public.messages
    WHERE id = v_req.user_message_id
      AND user_id = v_user_id
      AND conversation_id = v_req.conversation_id
      AND role = 'user';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid user_message_id: source user message not found in thread'
            USING ERRCODE = '42501';
    END IF;

    -- -------------------------------------------------------------------------
    -- Journal Isolation & Interruption Verification (Fail-Closed)
    -- -------------------------------------------------------------------------

    -- 1. Three-field match on consumed consent ledger: user_id, conversation_id, and idempotency_key
    v_has_consumed_consent := EXISTS (
        SELECT 1
        FROM public.consumed_consent_tokens cct
        WHERE cct.user_id = v_user_id
          AND cct.conversation_id = v_req.conversation_id
          AND cct.idempotency_key = p_idempotency_key
    );

    -- 2. Message metadata parsing (malformed fails closed to TRUE)
    v_user_journal_flag := public.fn_safe_jsonb_bool(v_user_msg.metadata, 'contains_journal_data', FALSE, TRUE);
    v_asst_journal_flag := public.fn_safe_jsonb_bool(v_asst_msg.metadata, 'contains_journal_data', FALSE, TRUE);

    -- Authoritative classification: any positive or malformed signal quarantines turn
    v_is_journal := (v_has_consumed_consent OR v_user_journal_flag OR v_asst_journal_flag);

    -- 3. Interruption detection
    v_user_interrupted := public.fn_safe_jsonb_bool(v_user_msg.metadata, 'interrupted', FALSE, TRUE);
    v_asst_interrupted := public.fn_safe_jsonb_bool(v_asst_msg.metadata, 'interrupted', FALSE, TRUE)
                       OR public.fn_safe_jsonb_bool(v_asst_msg.metadata, 'failed', FALSE, TRUE);

    v_is_interrupted := (v_user_interrupted OR v_asst_interrupted);

    -- Update chat request to completed with authoritative journal classification
    UPDATE public.chat_requests
    SET status = 'completed',
        assistant_message_id = p_assistant_message_id,
        contains_journal_data = v_is_journal,
        updated_at = now()
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    RETURNING * INTO v_req;

    -- Transactional Outbox: atomically insert extraction job ONLY for eligible, unquarantined turns
    IF NOT v_is_journal AND NOT v_is_interrupted THEN
        INSERT INTO public.memory_extraction_jobs (
            user_id,
            conversation_id,
            source_message_id,
            idempotency_key,
            status,
            scheduled_at
        ) VALUES (
            v_user_id,
            v_req.conversation_id,
            p_assistant_message_id,
            p_idempotency_key,
            'pending',
            now()
        )
        ON CONFLICT (user_id, source_message_id) DO NOTHING;
    END IF;

    RETURN to_jsonb(v_req);
END;
$$;

REVOKE ALL ON FUNCTION public.complete_chat_request(TEXT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.complete_chat_request(TEXT, UUID) TO authenticated;

-- ============================================================================
-- 4. SECURE EXTRACTION SOURCE RETRIEVAL RPC
-- ============================================================================

-- Fetches source message pair strictly for an authorized, locked, and unquarantined job.
-- Enforces claim-token fencing, lease validity, and journal quarantine fail-closed.
CREATE OR REPLACE FUNCTION public.fetch_extraction_source_message_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_claim_token UUID
)
RETURNS TABLE (
    job_id UUID,
    user_id UUID,
    conversation_id UUID,
    source_message_id UUID,
    assistant_content TEXT,
    assistant_role TEXT,
    user_message_content TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_job public.memory_extraction_jobs%ROWTYPE;
    v_req public.chat_requests%ROWTYPE;
    v_asst_msg public.messages%ROWTYPE;
    v_user_msg public.messages%ROWTYPE;
    v_has_consent BOOLEAN;
    v_is_journal BOOLEAN;
    v_is_interrupted BOOLEAN;
BEGIN
    -- Verify caller session identity: strictly requires membership in auren_worker role
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    IF p_job_id IS NULL THEN
        RAISE EXCEPTION 'Job ID cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_claim_token IS NULL THEN
        RAISE EXCEPTION 'Claim token cannot be null' USING ERRCODE = '22023';
    END IF;

    -- Lock job row
    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    -- Fencing Token Check: UUIDv4 token provides 122 bits of cryptographic entropy
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has a different claim token', p_job_id USING ERRCODE = '22023';
    END IF;

    -- Caller identity and lease status checks
    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker % (status: %, locked_by: %)',
            p_job_id, p_worker_id, v_job.status, v_job.locked_by USING ERRCODE = '42501';
    END IF;

    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; source fetch rejected',
            p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    -- Retrieve assistant message
    SELECT * INTO v_asst_msg
    FROM public.messages m
    WHERE m.id = v_job.source_message_id
      AND m.user_id = v_job.user_id
      AND m.conversation_id = v_job.conversation_id
      AND m.role = 'assistant';

    IF NOT FOUND THEN
        UPDATE public.memory_extraction_jobs mej
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),
            last_error = '[INTEGRITY] Assistant source message missing or invalid',
            updated_at = clock_timestamp()
        WHERE mej.id = p_job_id;

        RETURN;
    END IF;

    -- Retrieve associated chat request
    SELECT * INTO v_req
    FROM public.chat_requests cr
    WHERE cr.user_id = v_job.user_id
      AND cr.assistant_message_id = v_job.source_message_id;

    IF NOT FOUND OR v_req.status != 'completed' THEN
        UPDATE public.memory_extraction_jobs mej
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),
            last_error = '[INTEGRITY] Chat request not found or not in completed status',
            updated_at = clock_timestamp()
        WHERE mej.id = p_job_id;

        RETURN;
    END IF;

    -- Retrieve source user message
    SELECT * INTO v_user_msg
    FROM public.messages m
    WHERE m.id = v_req.user_message_id
      AND m.user_id = v_job.user_id
      AND m.conversation_id = v_job.conversation_id
      AND m.role = 'user';

    IF NOT FOUND THEN
        UPDATE public.memory_extraction_jobs mej
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),
            last_error = '[INTEGRITY] Source user message not found in thread',
            updated_at = clock_timestamp()
        WHERE mej.id = p_job_id;

        RETURN;
    END IF;

    -- Re-check Journal Quarantine and Interruption (Defense in Depth)
    v_has_consent := EXISTS (
        SELECT 1
        FROM public.consumed_consent_tokens cct
        WHERE cct.user_id = v_job.user_id
          AND cct.conversation_id = v_job.conversation_id
          AND cct.idempotency_key = v_req.idempotency_key
    );

    v_is_journal := (
        v_req.contains_journal_data
        OR v_has_consent
        OR public.fn_safe_jsonb_bool(v_user_msg.metadata, 'contains_journal_data', FALSE, TRUE)
        OR public.fn_safe_jsonb_bool(v_asst_msg.metadata, 'contains_journal_data', FALSE, TRUE)
    );

    v_is_interrupted := (
        public.fn_safe_jsonb_bool(v_user_msg.metadata, 'interrupted', FALSE, TRUE)
        OR public.fn_safe_jsonb_bool(v_asst_msg.metadata, 'interrupted', FALSE, TRUE)
        OR public.fn_safe_jsonb_bool(v_asst_msg.metadata, 'failed', FALSE, TRUE)
    );

    IF v_is_journal OR v_is_interrupted THEN
        -- Zero-retention quarantine: dead-letter job and clear locks without returning payload
        UPDATE public.memory_extraction_jobs mej
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),
            last_error = CASE
                WHEN v_is_journal THEN '[QUARANTINE] Source turn contains private journal data'
                ELSE '[QUARANTINE] Source turn was interrupted'
            END,
            updated_at = clock_timestamp()
        WHERE mej.id = p_job_id;

        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        v_job.id,
        v_job.user_id,
        v_job.conversation_id,
        v_asst_msg.id,
        v_asst_msg.content,
        v_asst_msg.role,
        v_user_msg.content;
END;
$$;

REVOKE ALL ON FUNCTION public.fetch_extraction_source_message_rpc(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fetch_extraction_source_message_rpc(UUID, TEXT, UUID) TO auren_worker;

-- ============================================================================
-- 5. WORKER TERMINAL LIFECYCLE & FENCING PROTECTIONS
-- ============================================================================

-- Function: complete_memory_extraction_job_rpc
-- Sets status = 'completed', clears locked_by/lease_expires_at, and rotates claim_token.
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
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    IF p_job_id IS NULL THEN
        RAISE EXCEPTION 'Job ID cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_claim_token IS NULL THEN
        RAISE EXCEPTION 'Claim token cannot be null' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    -- Safe Idempotency on completed job:
    -- Repeated completion with matching completing token succeeds idempotently.
    -- Attempted completion with mismatched/stale token is strictly rejected.
    IF v_job.status = 'completed' THEN
        IF v_job.completed_token = p_claim_token OR v_job.claim_token = p_claim_token THEN
            RETURN TRUE;
        ELSE
            RAISE EXCEPTION 'Stale claim token: job % has a different claim token', p_job_id USING ERRCODE = '22023';
        END IF;
    END IF;

    -- Strict Claim Token Check
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has a different claim token', p_job_id USING ERRCODE = '22023';
    END IF;

    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker % (current status: %, locked_by: %)',
            p_job_id, p_worker_id, v_job.status, v_job.locked_by USING ERRCODE = '42501';
    END IF;

    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; completion rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    -- Terminal transition: clear lease ownership, record completed_token, and rotate active claim_token (122 random bits invalidation)
    UPDATE public.memory_extraction_jobs
    SET status = 'completed',
        locked_by = NULL,
        lease_expires_at = NULL,
        completed_token = v_job.claim_token,
        claim_token = gen_random_uuid(),
        updated_at = clock_timestamp()
    WHERE id = p_job_id;

    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) TO auren_worker;

-- Function: fail_memory_extraction_job_rpc
-- Ensures locked_by and lease_expires_at are cleared and claim_token is rotated.
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
    v_clean_error TEXT;
    v_sanitized_error TEXT;
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    IF p_job_id IS NULL THEN
        RAISE EXCEPTION 'Job ID cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_claim_token IS NULL THEN
        RAISE EXCEPTION 'Claim token cannot be null' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has a different claim token', p_job_id USING ERRCODE = '22023';
    END IF;

    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker %', p_job_id, p_worker_id USING ERRCODE = '42501';
    END IF;

    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; failure update rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    -- Redact sensitive credentials in error text
    v_clean_error := COALESCE(p_error, 'Extraction failed without specific error details');
    v_clean_error := regexp_replace(v_clean_error, '(sk-[a-zA-Z0-9_\-]{8,}|AIza[a-zA-Z0-9_\-]{20,}|gh[pousr]_[a-zA-Z0-9]{20,})', '[REDACTED_API_KEY]', 'g');
    v_clean_error := regexp_replace(v_clean_error, 'Bearer\s+[a-zA-Z0-9._\-]+', 'Bearer [REDACTED_TOKEN]', 'gi');
    v_clean_error := regexp_replace(v_clean_error, 'ey[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}(\.[a-zA-Z0-9_\-]+)?', '[REDACTED_JWT]', 'g');
    v_clean_error := regexp_replace(v_clean_error, '(?i)(password|secret|key|token|authorization|apikey)\s*[:=]\s*[^\s,;]+', '\1=[REDACTED]', 'g');
    v_clean_error := regexp_replace(v_clean_error, '\b[a-f0-9]{32,64}\b', '[REDACTED_HEX]', 'g');
    v_sanitized_error := substr(trim(v_clean_error), 1, 500);

    IF p_retry AND v_job.attempts < v_job.max_attempts THEN
        UPDATE public.memory_extraction_jobs
        SET status = 'pending',
            locked_by = NULL,
            locked_at = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),
            last_error = v_sanitized_error,
            scheduled_at = clock_timestamp() + (POWER(2, v_job.attempts) * 5 || ' seconds')::INTERVAL,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    ELSE
        UPDATE public.memory_extraction_jobs
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),
            last_error = v_sanitized_error,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    END IF;

    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) TO auren_worker;

-- ============================================================================
-- 6. EPISTEMIC PROVENANCE & MEMORY INGESTION RPC
-- ============================================================================

-- Drop 9-argument version to prevent parameter ambiguity
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB);

-- Function: insert_extracted_memory_rpc
-- Enforces:
-- 1. Caller session is authorized worker.
-- 2. Claim-token fencing and active lease validation.
-- 3. Inferred dialogue provenance: origin='chat_inferred', confirmation_status='unconfirmed'.
-- 4. Rejection of worker-created 'system_asserted' memories.
-- 5. Deduplication against existing active memories from same source turn.
-- 6. Atomic embedding persistence if provided.
CREATE OR REPLACE FUNCTION public.insert_extracted_memory_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_claim_token UUID,
    p_content TEXT,
    p_memory_type TEXT,
    p_category TEXT,
    p_importance INT DEFAULT 3,
    p_confidence DOUBLE PRECISION DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb,
    p_embedding_768 vector(768) DEFAULT NULL
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
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    IF p_claim_token IS NULL THEN
        RAISE EXCEPTION 'Claim token cannot be null' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    -- Strict Claim Token Check
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has a different claim token; ingestion rejected', p_job_id
            USING ERRCODE = '22023';
    END IF;

    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker %', p_job_id, p_worker_id USING ERRCODE = '42501';
    END IF;

    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; ingestion rejected', p_job_id, v_job.lease_expires_at
            USING ERRCODE = '22023';
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

    IF p_importance IS NULL OR p_importance < 1 OR p_importance > 5 THEN
        RAISE EXCEPTION 'Importance must be between 1 and 5' USING ERRCODE = '22023';
    END IF;

    IF p_confidence IS NOT NULL AND (p_confidence < 0.0 OR p_confidence > 1.0) THEN
        RAISE EXCEPTION 'Confidence must be between 0.0 and 1.0' USING ERRCODE = '22023';
    END IF;

    -- Epistemic Boundary Check: ordinary workers CANNOT create system_asserted memories
    IF p_metadata IS NOT NULL AND (
        p_metadata ->> 'confirmation_status' = 'system_asserted'
        OR p_metadata ->> 'origin' = 'system_asserted'
    ) THEN
        RAISE EXCEPTION 'Worker extractions cannot create system_asserted memories' USING ERRCODE = '42501';
    END IF;

    -- Duplicate Extraction Prevention: check if identical memory already extracted for this source turn
    SELECT id INTO v_existing_id
    FROM public.memories
    WHERE user_id = v_job.user_id
      AND source_message_id = v_job.source_message_id
      AND lower(trim(content)) = lower(trim(p_content))
      AND lifecycle_status = 'active'
    LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        -- Return existing memory ID to preserve idempotency without duplicate storage
        RETURN v_existing_id;
    END IF;

    -- Ingestion with strict epistemic status: origin='chat_inferred', confirmation_status='unconfirmed'
    INSERT INTO public.memories (
        user_id,
        content,
        memory_type,
        category,
        importance,
        confidence,
        origin,
        confirmation_status,
        last_confirmed_at,
        lifecycle_status,
        source_message_id,
        source_conversation_id,
        metadata
    ) VALUES (
        v_job.user_id,
        trim(p_content),
        p_memory_type,
        p_category,
        p_importance,
        COALESCE(p_confidence, 0.7),
        'chat_inferred',
        'unconfirmed',
        NULL,
        'active',
        v_job.source_message_id,
        v_job.conversation_id,
        COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_memory_id;

    -- Set root_memory_id to self
    UPDATE public.memories
    SET root_memory_id = v_memory_id
    WHERE id = v_memory_id;

    -- Attach vector embedding atomically if provided
    IF p_embedding_768 IS NOT NULL THEN
        INSERT INTO public.memory_embeddings (
            memory_id,
            user_id,
            provider,
            model,
            version,
            dimension,
            embedding_768,
            is_active
        ) VALUES (
            v_memory_id,
            v_job.user_id,
            'gemini',
            'text-embedding-004',
            'v1',
            768,
            p_embedding_768,
            TRUE
        )
        ON CONFLICT (memory_id, provider, model, version) DO NOTHING;
    END IF;

    RETURN v_memory_id;
END;
$$;

REVOKE ALL ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector) TO auren_worker;

-- ============================================================================
-- 7. HYBRID MEMORY RETRIEVAL RPC
-- ============================================================================

-- Mathematical Scoring Formulation:
-- Score(m) = 0.40 * S_sem(m) + 0.25 * S_lex(m) + 0.15 * (importance / 5.0) + D(m) + 0.10 * conf(m)
-- Bounds:
-- - S_sem in [0.0, 1.0]
-- - S_lex in [0.0, 1.0) via ts_rank_cd(..., 32)
-- - importance in [0.03, 0.15]
-- - D(m) in (0.00, 0.10]
-- - conf(m) in [0.00, 0.10] (neutral 0.50 fallback for NULL)
-- Total Score: Infimum > 0.03, Supremum < 1.00, Legacy Interval [0.18, 0.95).
CREATE OR REPLACE FUNCTION public.search_memories_hybrid_rpc(
    p_query_text TEXT,
    p_query_embedding vector(768) DEFAULT NULL,
    p_limit INT DEFAULT 5,
    p_min_similarity REAL DEFAULT 0.0
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    memory_type TEXT,
    category TEXT,
    importance INT,
    confidence DOUBLE PRECISION,
    confirmation_status TEXT,
    score REAL
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_tsquery tsquery;
    v_has_text BOOLEAN;
    v_has_embedding BOOLEAN;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 50 THEN
        p_limit := 5;
    END IF;

    v_has_text := (p_query_text IS NOT NULL AND length(trim(p_query_text)) > 0);
    v_has_embedding := (p_query_embedding IS NOT NULL);

    IF v_has_text THEN
        v_tsquery := plainto_tsquery('english', trim(p_query_text));
    ELSE
        v_tsquery := NULL;
    END IF;

    RETURN QUERY
    WITH scored AS (
        SELECT
            m.id,
            m.content,
            m.memory_type,
            m.category,
            m.importance,
            m.confidence,
            m.confirmation_status,
            -- Component 1: Semantic similarity S_sem in [0, 1]
            (CASE
                WHEN v_has_embedding AND emb.embedding_768 IS NOT NULL THEN
                    GREATEST(0.0::real, LEAST(1.0::real, (1.0 - (emb.embedding_768 <=> p_query_embedding))::real))
                ELSE 0.0::real
            END) AS s_sem,
            -- Component 2: Lexical rank S_lex in [0, 1) using ts_rank_cd flag 32 (rank / (rank + 1))
            (CASE
                WHEN v_has_text AND v_tsquery IS NOT NULL THEN
                    LEAST(0.999999::real, GREATEST(0.0::real,
                        ts_rank_cd(to_tsvector('english', m.content), v_tsquery, 32)::real
                    ))
                ELSE 0.0::real
            END) AS s_lex,
            -- Component 3: Normalized importance in [0.03, 0.15]
            (0.15::real * (m.importance::real / 5.0::real)) AS s_imp,
            -- Component 4: Recency / Time decay D(m) in (0, 0.10]
            (CASE
                WHEN m.memory_type IN ('preference', 'fact', 'goal', 'project') OR m.confirmation_status = 'system_asserted' THEN
                    0.10::real
                WHEN m.memory_type IN ('context', 'observation') THEN
                    (0.10::real * exp(-0.0231::real * GREATEST(0.0::real, (EXTRACT(EPOCH FROM (clock_timestamp() - m.created_at)) / 86400.0)::real)))
                ELSE
                    0.05::real  -- Safe fallback for future/unknown memory types
            END) AS s_decay,
            -- Component 5: Confidence in [0.0, 0.10] with neutral 0.50 fallback for NULL
            (0.10::real * COALESCE(m.confidence::real, 0.50::real)) AS s_conf
        FROM public.memories m
        LEFT JOIN LATERAL (
            SELECT me.embedding_768
            FROM public.memory_embeddings me
            WHERE me.memory_id = m.id
              AND me.user_id = v_user_id
              AND me.is_active = TRUE
              AND me.embedding_768 IS NOT NULL
            LIMIT 1
        ) emb ON TRUE
        WHERE m.user_id = v_user_id
          AND m.lifecycle_status = 'active'
          AND m.confirmation_status IN ('confirmed', 'unconfirmed', 'system_asserted')
          AND (m.expires_at IS NULL OR m.expires_at > clock_timestamp())
    )
    SELECT
        s.id,
        s.content,
        s.memory_type,
        s.category,
        s.importance,
        s.confidence,
        s.confirmation_status,
        (0.40::real * s.s_sem + 0.25::real * s.s_lex + s.s_imp + s.s_decay + s.s_conf)::real AS score
    FROM scored s
    WHERE (v_has_embedding IS FALSE OR s.s_sem >= p_min_similarity)
    ORDER BY score DESC
    LIMIT p_limit;
END;
$$;

REVOKE ALL ON FUNCTION public.search_memories_hybrid_rpc(TEXT, vector, INT, REAL) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.search_memories_hybrid_rpc(TEXT, vector, INT, REAL) TO authenticated;

-- ============================================================================
-- 8. WORKER PRIVILEGE BOUNDARY ENFORCEMENT
-- ============================================================================

-- Revoke direct table SELECT on memory_extraction_jobs from auren_worker
-- All worker queue interactions must use SECURITY DEFINER RPCs exclusively.
REVOKE SELECT ON TABLE public.memory_extraction_jobs FROM auren_worker;
DROP POLICY IF EXISTS "extraction_jobs_worker_select" ON public.memory_extraction_jobs;

-- Ensure auren_worker possesses NO direct access to messages or journal_entries
REVOKE ALL ON TABLE public.messages FROM auren_worker;
REVOKE ALL ON TABLE public.journal_entries FROM auren_worker;
