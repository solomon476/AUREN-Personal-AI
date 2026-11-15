-- Migration: 009_strict_lifecycle_matrix_and_exclusive_claim.sql
-- Description: Strict lifecycle transition matrix, exclusive RPC claiming, hex fingerprint enforcement,
--              and dedicated reconciliation RPC.

-- ============================================================================
-- 1. BACKFILL AND ENFORCE 64-CHARACTER HEXADECIMAL REQUEST FINGERPRINT
-- ============================================================================

-- Backfill any legacy NULL request_fingerprint with deterministic 64-hex SHA-256 hash
UPDATE public.chat_requests
SET request_fingerprint = encode(digest('legacy:' || user_id::text || ':' || idempotency_key, 'sha256'), 'hex')
WHERE request_fingerprint IS NULL;

-- Enforce NOT NULL on request_fingerprint
ALTER TABLE public.chat_requests
    ALTER COLUMN request_fingerprint SET NOT NULL;

-- Enforce strictly 64-character lowercase/uppercase hexadecimal format
ALTER TABLE public.chat_requests
    DROP CONSTRAINT IF EXISTS chat_requests_fingerprint_hex_check;

ALTER TABLE public.chat_requests
    ADD CONSTRAINT chat_requests_fingerprint_hex_check
    CHECK (request_fingerprint ~ '^[0-9a-fA-F]{64}$');

-- ============================================================================
-- 2. EXCLUSIVE RPC CLAIMING: REVOKE DIRECT INSERT PRIVILEGES
-- ============================================================================

-- Authenticated clients cannot directly INSERT into chat_requests.
-- All claims must proceed exclusively through the claim_chat_request() RPC.
REVOKE INSERT ON public.chat_requests FROM authenticated, anon;
DROP POLICY IF EXISTS "chat_requests_insert_own" ON public.chat_requests;

-- Ensure SELECT is granted to authenticated for reading their own requests
GRANT SELECT ON public.chat_requests TO authenticated;

-- ============================================================================
-- 3. DATABASE-LEVEL TRIGGER: STRICT TRANSITION MATRIX & IMMUTABILITY
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_chat_requests_immutability()
RETURNS TRIGGER AS $$
BEGIN
    -- Prevent altering request_fingerprint once assigned
    IF NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint THEN
        RAISE EXCEPTION 'request_fingerprint is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    -- Prevent altering user_id (prevent tampering with request ownership)
    IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        RAISE EXCEPTION 'user_id is immutable and cannot be transferred' USING ERRCODE = '42501';
    END IF;

    -- Prevent altering idempotency_key
    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
        RAISE EXCEPTION 'idempotency_key is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    -- Prevent altering conversation_id
    IF NEW.conversation_id IS DISTINCT FROM OLD.conversation_id THEN
        RAISE EXCEPTION 'conversation_id is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    -- Prevent altering user_message_id
    IF NEW.user_message_id IS DISTINCT FROM OLD.user_message_id THEN
        RAISE EXCEPTION 'user_message_id is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    -- Prevent altering created_at
    IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'created_at is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    -- Enforce explicit lifecycle transition matrix
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        -- Terminal state check: completed can never transition to any other status
        IF OLD.status = 'completed' THEN
            RAISE EXCEPTION 'Completed chat requests cannot be transitioned out of completed status' USING ERRCODE = '22023';
        END IF;

        -- Permitted transitions:
        -- 1. processing -> completed
        -- 2. processing -> failed
        -- 3. processing -> interrupted
        -- 4. failed -> processing
        -- 5. interrupted -> processing
        -- 6. reconciliation: failed/interrupted -> completed (requires assistant_message_id)
        IF NOT (
            (OLD.status = 'processing' AND NEW.status IN ('completed', 'failed', 'interrupted')) OR
            (OLD.status IN ('failed', 'interrupted') AND NEW.status = 'processing') OR
            (OLD.status IN ('failed', 'interrupted') AND NEW.status = 'completed' AND NEW.assistant_message_id IS NOT NULL)
        ) THEN
            RAISE EXCEPTION 'Invalid status transition from % to %', OLD.status, NEW.status USING ERRCODE = '22023';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chat_requests_immutability ON public.chat_requests;
CREATE TRIGGER trg_chat_requests_immutability
    BEFORE UPDATE ON public.chat_requests
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_chat_requests_immutability();

-- ============================================================================
-- 4. SECURITY DEFINER RPCS: EXCLUSIVE CLAIMING & STRICT LIFECYCLE
-- ============================================================================

-- RPC 1: claim_chat_request
-- Atomically claims a request lifecycle record validating conversation and message ownership.
-- Enforces 64-char hex fingerprint and detects conflicts on duplicate submissions.
CREATE OR REPLACE FUNCTION public.claim_chat_request(
    p_idempotency_key TEXT,
    p_conversation_id UUID,
    p_user_message_id UUID,
    p_request_fingerprint TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_existing public.chat_requests%ROWTYPE;
    v_new public.chat_requests%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    -- Validate fingerprint format: strictly non-null, 64-character hexadecimal
    IF p_request_fingerprint IS NULL OR p_request_fingerprint !~ '^[0-9a-fA-F]{64}$' THEN
        RAISE EXCEPTION 'Valid 64-character hexadecimal request fingerprint is required' USING ERRCODE = '22023';
    END IF;

    -- Verify caller owns the conversation
    IF NOT EXISTS (
        SELECT 1 FROM public.conversations
        WHERE id = p_conversation_id AND user_id = v_user_id
    ) THEN
        RAISE EXCEPTION 'Conversation not found or access denied' USING ERRCODE = '42501';
    END IF;

    -- Verify caller owns the user message in that conversation with role='user'
    IF NOT EXISTS (
        SELECT 1 FROM public.messages
        WHERE id = p_user_message_id AND user_id = v_user_id AND conversation_id = p_conversation_id AND role = 'user'
    ) THEN
        RAISE EXCEPTION 'User message not found or access denied' USING ERRCODE = '42501';
    END IF;

    -- Check if request already claimed (with row lock for concurrency)
    SELECT * INTO v_existing
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF FOUND THEN
        -- Compare stored fingerprint with incoming fingerprint
        IF v_existing.request_fingerprint IS DISTINCT FROM p_request_fingerprint THEN
            RAISE EXCEPTION 'Idempotency key % was already used with conflicting request content', p_idempotency_key
                USING ERRCODE = '23505'; -- 23505 maps to HTTP 409 Conflict in PostgREST
        END IF;

        RETURN jsonb_build_object(
            'claimed', false,
            'request', to_jsonb(v_existing)
        );
    END IF;

    -- Insert new processing record
    INSERT INTO public.chat_requests (
        user_id,
        idempotency_key,
        conversation_id,
        status,
        user_message_id,
        request_fingerprint,
        created_at,
        updated_at
    ) VALUES (
        v_user_id,
        p_idempotency_key,
        p_conversation_id,
        'processing',
        p_user_message_id,
        p_request_fingerprint,
        now(),
        now()
    )
    RETURNING * INTO v_new;

    RETURN jsonb_build_object(
        'claimed', true,
        'request', to_jsonb(v_new)
    );
EXCEPTION
    WHEN unique_violation THEN
        SELECT * INTO v_existing
        FROM public.chat_requests
        WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key;

        IF FOUND THEN
            IF v_existing.request_fingerprint IS DISTINCT FROM p_request_fingerprint THEN
                RAISE EXCEPTION 'Idempotency key % was already used with conflicting request content', p_idempotency_key
                    USING ERRCODE = '23505';
            END IF;

            RETURN jsonb_build_object(
                'claimed', false,
                'request', to_jsonb(v_existing)
            );
        END IF;
        RAISE;
END;
$$;

-- RPC 2: complete_chat_request
-- Atomically completes a processing request. Rejects non-processing requests (failed/interrupted must use reconcile_chat_request).
CREATE OR REPLACE FUNCTION public.complete_chat_request(
    p_idempotency_key TEXT,
    p_assistant_message_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_req public.chat_requests%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    IF p_assistant_message_id IS NULL THEN
        RAISE EXCEPTION 'assistant_message_id is required to complete request' USING ERRCODE = '22023';
    END IF;

    -- Lock row
    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    -- Enforce terminal state: completed cannot be changed to another assistant message
    IF v_req.status = 'completed' THEN
        IF v_req.assistant_message_id = p_assistant_message_id THEN
            RETURN to_jsonb(v_req);
        ELSE
            RAISE EXCEPTION 'Completed request cannot be updated with a different assistant message'
                USING ERRCODE = '22023';
        END IF;
    END IF;

    -- Ordinary completion RPC ONLY allows processing -> completed.
    -- failed -> completed and interrupted -> completed are REJECTED (must use reconcile_chat_request).
    IF v_req.status != 'processing' THEN
        RAISE EXCEPTION 'Invalid status transition: cannot complete request with status %', v_req.status
            USING ERRCODE = '22023';
    END IF;

    -- Verify assistant_message_id belongs to caller, belongs to conversation, and has role='assistant'
    IF NOT EXISTS (
        SELECT 1 FROM public.messages
        WHERE id = p_assistant_message_id
          AND user_id = v_user_id
          AND conversation_id = v_req.conversation_id
          AND role = 'assistant'
    ) THEN
        RAISE EXCEPTION 'Invalid assistant_message_id: message not found in thread or not an assistant response'
            USING ERRCODE = '42501';
    END IF;

    -- Update record to completed
    UPDATE public.chat_requests
    SET status = 'completed',
        assistant_message_id = p_assistant_message_id,
        updated_at = now()
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    RETURNING * INTO v_req;

    RETURN to_jsonb(v_req);
END;
$$;

-- RPC 3: fail_chat_request
-- Atomically transitions processing request to failed. Rejects non-processing requests.
CREATE OR REPLACE FUNCTION public.fail_chat_request(
    p_idempotency_key TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_req public.chat_requests%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_req.status = 'failed' THEN
        RETURN to_jsonb(v_req);
    END IF;

    IF v_req.status != 'processing' THEN
        RAISE EXCEPTION 'Invalid status transition: cannot fail request with status %', v_req.status
            USING ERRCODE = '22023';
    END IF;

    UPDATE public.chat_requests
    SET status = 'failed',
        updated_at = now()
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    RETURNING * INTO v_req;

    RETURN to_jsonb(v_req);
END;
$$;

-- RPC 4: interrupt_chat_request
-- Atomically transitions processing request to interrupted. Rejects non-processing requests.
CREATE OR REPLACE FUNCTION public.interrupt_chat_request(
    p_idempotency_key TEXT,
    p_assistant_message_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_req public.chat_requests%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_req.status = 'interrupted' THEN
        RETURN to_jsonb(v_req);
    END IF;

    IF v_req.status != 'processing' THEN
        RAISE EXCEPTION 'Invalid status transition: cannot interrupt request with status %', v_req.status
            USING ERRCODE = '22023';
    END IF;

    -- If assistant_message_id is provided, validate ownership, thread, and role
    IF p_assistant_message_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.messages
            WHERE id = p_assistant_message_id
              AND user_id = v_user_id
              AND conversation_id = v_req.conversation_id
              AND role = 'assistant'
        ) THEN
            RAISE EXCEPTION 'Invalid assistant_message_id: message not found in thread or not an assistant response'
                USING ERRCODE = '42501';
        END IF;
    END IF;

    UPDATE public.chat_requests
    SET status = 'interrupted',
        assistant_message_id = COALESCE(p_assistant_message_id, assistant_message_id),
        updated_at = now()
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    RETURNING * INTO v_req;

    RETURN to_jsonb(v_req);
END;
$$;

-- RPC 5: retry_chat_request
-- Atomically transitions request from failed or interrupted to processing. Rejects processing and completed.
CREATE OR REPLACE FUNCTION public.retry_chat_request(
    p_idempotency_key TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_req public.chat_requests%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    -- Atomic conditional transition
    UPDATE public.chat_requests
    SET status = 'processing',
        updated_at = now()
    WHERE user_id = v_user_id
      AND idempotency_key = p_idempotency_key
      AND status IN ('failed', 'interrupted')
    RETURNING * INTO v_req;

    IF FOUND THEN
        RETURN jsonb_build_object(
            'transitioned', true,
            'request', to_jsonb(v_req)
        );
    END IF;

    -- If not transitioned, inspect current state
    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_req.status = 'completed' THEN
        RAISE EXCEPTION 'Completed requests cannot be retried' USING ERRCODE = '22023';
    END IF;

    RETURN jsonb_build_object(
        'transitioned', false,
        'request', to_jsonb(v_req)
    );
END;
$$;

-- RPC 6: reconcile_chat_request
-- Dedicated narrowly scoped reconciliation operation for persistence recovery.
-- Validates that the assistant message belongs to the caller, thread, matches the user message,
-- and is not marked as interrupted before transitioning an incomplete request (processing/failed/interrupted)
-- to completed.
CREATE OR REPLACE FUNCTION public.reconcile_chat_request(
    p_idempotency_key TEXT,
    p_assistant_message_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_req public.chat_requests%ROWTYPE;
    v_msg public.messages%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    IF p_assistant_message_id IS NULL THEN
        RAISE EXCEPTION 'assistant_message_id is required to reconcile request' USING ERRCODE = '22023';
    END IF;

    -- Lock row
    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    -- Terminal check
    IF v_req.status = 'completed' THEN
        IF v_req.assistant_message_id = p_assistant_message_id THEN
            RETURN to_jsonb(v_req);
        ELSE
            RAISE EXCEPTION 'Completed request already associated with different assistant message'
                USING ERRCODE = '22023';
        END IF;
    END IF;

    -- Verify assistant message exists in the thread with role='assistant'
    SELECT * INTO v_msg
    FROM public.messages
    WHERE id = p_assistant_message_id
      AND user_id = v_user_id
      AND conversation_id = v_req.conversation_id
      AND role = 'assistant';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid assistant_message_id: message not found in thread or not an assistant response'
            USING ERRCODE = '42501';
    END IF;

    -- Validate user_message association in metadata
    IF (v_msg.metadata->>'user_message_id') IS DISTINCT FROM v_req.user_message_id::text THEN
        RAISE EXCEPTION 'Assistant message was not generated for this user message' USING ERRCODE = '22023';
    END IF;

    -- Validate assistant message is not interrupted
    IF (v_msg.metadata->>'interrupted') = 'true' THEN
        RAISE EXCEPTION 'Cannot reconcile request with an interrupted assistant message' USING ERRCODE = '22023';
    END IF;

    -- Transition status to completed
    UPDATE public.chat_requests
    SET status = 'completed',
        assistant_message_id = p_assistant_message_id,
        updated_at = now()
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    RETURNING * INTO v_req;

    RETURN to_jsonb(v_req);
END;
$$;

-- ============================================================================
-- 5. FUNCTION PRIVILEGES: RESTRICT TO AUTHENTICATED ONLY
-- ============================================================================

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
