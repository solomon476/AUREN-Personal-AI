-- Migration: 008_restrict_lifecycle_mutation_and_rpcs.sql
-- Description: Revoke direct UPDATE/DELETE privileges on chat_requests, enforce strict INSERT validation,
--              and implement narrowly scoped security-definer RPC functions for lifecycle transitions.

-- 1. Revoke direct mutation privileges from authenticated and anon
REVOKE UPDATE, DELETE ON public.chat_requests FROM authenticated, anon;
DROP POLICY IF EXISTS "chat_requests_update_own" ON public.chat_requests;
DROP POLICY IF EXISTS "chat_requests_delete_own" ON public.chat_requests;

-- 2. Enforce strict INSERT policy verifying ownership of conversation, user message, status, and fingerprint
DROP POLICY IF EXISTS "chat_requests_insert_own" ON public.chat_requests;
CREATE POLICY "chat_requests_insert_own" ON public.chat_requests
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id
        AND status = 'processing'
        AND request_fingerprint IS NOT NULL
        AND length(request_fingerprint) = 64
        AND EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = conversation_id AND c.user_id = auth.uid()
        )
        AND EXISTS (
            SELECT 1 FROM public.messages m
            WHERE m.id = user_message_id
              AND m.user_id = auth.uid()
              AND m.conversation_id = chat_requests.conversation_id
              AND m.role = 'user'
        )
    );

-- 3. RPC: claim_chat_request
-- Atomically claims a request lifecycle record validating conversation and message ownership.
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

    -- Validate fingerprint format
    IF p_request_fingerprint IS NULL OR length(p_request_fingerprint) != 64 THEN
        RAISE EXCEPTION 'Valid 64-character request fingerprint is required' USING ERRCODE = '22023';
    END IF;

    -- Verify caller owns the conversation
    IF NOT EXISTS (
        SELECT 1 FROM public.conversations
        WHERE id = p_conversation_id AND user_id = v_user_id
    ) THEN
        RAISE EXCEPTION 'Conversation not found or access denied' USING ERRCODE = '42501';
    END IF;

    -- Verify caller owns the user message in that conversation
    IF NOT EXISTS (
        SELECT 1 FROM public.messages
        WHERE id = p_user_message_id AND user_id = v_user_id AND conversation_id = p_conversation_id AND role = 'user'
    ) THEN
        RAISE EXCEPTION 'User message not found or access denied' USING ERRCODE = '42501';
    END IF;

    -- Check if request already claimed
    SELECT * INTO v_existing
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key;

    IF FOUND THEN
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
        RETURN jsonb_build_object(
            'claimed', false,
            'request', to_jsonb(v_existing)
        );
END;
$$;

-- 4. RPC: complete_chat_request
-- Atomically completes a processing or recovered request, strictly validating assistant_message_id.
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

    -- Find request owned by caller
    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    -- Enforce terminal state: completed cannot be re-completed
    IF v_req.status = 'completed' THEN
        RETURN to_jsonb(v_req);
    END IF;

    -- Permitted transitions to completed: processing, failed, interrupted (reconciliation)
    IF v_req.status NOT IN ('processing', 'failed', 'interrupted') THEN
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

-- 5. RPC: fail_chat_request
-- Atomically transitions processing request to failed.
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
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_req.status = 'completed' THEN
        RAISE EXCEPTION 'Completed requests cannot be transitioned to failed' USING ERRCODE = '22023';
    END IF;

    UPDATE public.chat_requests
    SET status = 'failed',
        updated_at = now()
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key
    RETURNING * INTO v_req;

    RETURN to_jsonb(v_req);
END;
$$;

-- 6. RPC: interrupt_chat_request
-- Atomically transitions processing request to interrupted, validating assistant_message_id if provided.
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
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Chat request not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_req.status = 'completed' THEN
        RAISE EXCEPTION 'Completed requests cannot be transitioned to interrupted' USING ERRCODE = '22023';
    END IF;

    -- If assistant_message_id is provided, validate ownership and role
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

-- 7. RPC: retry_chat_request
-- Atomically transitions request from failed or interrupted to processing.
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

    -- If not transitioned, return current state
    SELECT * INTO v_req
    FROM public.chat_requests
    WHERE user_id = v_user_id AND idempotency_key = p_idempotency_key;

    RETURN jsonb_build_object(
        'transitioned', false,
        'request', to_jsonb(v_req)
    );
END;
$$;

-- 8. Grant execute permissions strictly to authenticated users (revoked from anon)
REVOKE ALL ON FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.complete_chat_request(TEXT, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.fail_chat_request(TEXT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.interrupt_chat_request(TEXT, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.retry_chat_request(TEXT) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.complete_chat_request(TEXT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fail_chat_request(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.interrupt_chat_request(TEXT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.retry_chat_request(TEXT) TO authenticated;

