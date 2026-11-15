-- Migration: 007_chat_requests_integrity_and_rls.sql
-- Description: Enforce request_fingerprint immutability, protect ownership and status lifecycle transitions, and tighten RLS permissions on chat_requests.

-- 1. Function enforcing immutable fields and valid lifecycle transitions on chat_requests
CREATE OR REPLACE FUNCTION public.handle_chat_requests_immutability()
RETURNS TRIGGER AS $$
BEGIN
    -- Prevent altering request_fingerprint once assigned (allows setting once if previously NULL for backwards compatibility)
    IF OLD.request_fingerprint IS NOT NULL AND NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint THEN
        RAISE EXCEPTION 'request_fingerprint is immutable and cannot be modified once set';
    END IF;

    -- Prevent altering user_id (prevent tampering with request ownership)
    IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        RAISE EXCEPTION 'user_id is immutable and cannot be transferred';
    END IF;

    -- Prevent altering idempotency_key
    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
        RAISE EXCEPTION 'idempotency_key is immutable and cannot be modified';
    END IF;

    -- Prevent altering conversation_id
    IF NEW.conversation_id IS DISTINCT FROM OLD.conversation_id THEN
        RAISE EXCEPTION 'conversation_id is immutable and cannot be modified';
    END IF;

    -- Prevent altering user_message_id
    IF NEW.user_message_id IS DISTINCT FROM OLD.user_message_id THEN
        RAISE EXCEPTION 'user_message_id is immutable and cannot be modified';
    END IF;

    -- Prevent altering created_at
    IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'created_at is immutable and cannot be modified';
    END IF;

    -- Prevent invalid transition out of completed status
    IF OLD.status = 'completed' AND NEW.status != 'completed' THEN
        RAISE EXCEPTION 'Completed chat requests cannot be transitioned out of completed status';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Attach trigger to public.chat_requests
DROP TRIGGER IF EXISTS trg_chat_requests_immutability ON public.chat_requests;
CREATE TRIGGER trg_chat_requests_immutability
    BEFORE UPDATE ON public.chat_requests
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_chat_requests_immutability();

-- 3. Replace broad FOR ALL policy with granular, least-privilege RLS policies
DROP POLICY IF EXISTS "chat_requests_all_own" ON public.chat_requests;
DROP POLICY IF EXISTS "chat_requests_select_own" ON public.chat_requests;
DROP POLICY IF EXISTS "chat_requests_insert_own" ON public.chat_requests;
DROP POLICY IF EXISTS "chat_requests_update_own" ON public.chat_requests;
DROP POLICY IF EXISTS "chat_requests_delete_own" ON public.chat_requests;

-- Authenticated callers can only SELECT their own requests
CREATE POLICY "chat_requests_select_own" ON public.chat_requests
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

-- Authenticated callers can only INSERT requests owned by them with initial status 'processing'
CREATE POLICY "chat_requests_insert_own" ON public.chat_requests
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id
        AND status = 'processing'
    );

-- Authenticated callers can only UPDATE their own requests to valid lifecycle statuses
CREATE POLICY "chat_requests_update_own" ON public.chat_requests
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (
        auth.uid() = user_id
        AND status IN ('processing', 'completed', 'failed', 'interrupted')
    );

-- Direct DELETE is intentionally omitted: authenticated clients cannot arbitrarily delete chat_requests.
-- Deletion is strictly managed via CASCADE from parent conversations or users.
REVOKE DELETE ON public.chat_requests FROM authenticated, anon;

