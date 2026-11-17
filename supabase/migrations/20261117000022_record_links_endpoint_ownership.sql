-- Migration 022: record_links endpoint ownership enforcement
--
-- Phase 3C.5.2 / SEC-01: Prevents cross-tenant endpoint references in record_links.
--
-- Background:
--   The record_links RLS policy (Migration 021) only checks user_id = auth.uid(), but it
--   does NOT verify that source_id or target_id actually belong to the authenticated user.
--   This allows a user to forge a link pointing at another user's task, project, goal, etc.
--
-- Fix:
--   A BEFORE INSERT OR UPDATE trigger validates both endpoints against their respective
--   entity tables (tasks, projects, goals, memories, conversations, messages) and confirms
--   each record is owned by the same user_id being written to record_links.
--   Messages inherit ownership from their parent conversation.
--
-- Security properties:
--   * SECURITY DEFINER with pinned search_path prevents search_path hijacking.
--   * user_id = auth.uid() check is enforced at trigger level (defense-in-depth with RLS).
--   * Invalid entity_type values are rejected.
--   * Nonexistent UUIDs are rejected.
--
-- Idempotent: safe to apply multiple times.

-- ============================================================
-- Step 1: Trigger function
-- ============================================================

CREATE OR REPLACE FUNCTION public.validate_record_link_endpoints()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
DECLARE
    v_ok BOOLEAN;
    v_conv_user UUID;
BEGIN
    -- Enforce user_id = auth.uid() at trigger level (defense-in-depth with RLS)
    IF NEW.user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'record_links.user_id must equal auth.uid() (got %, expected %)',
            NEW.user_id, auth.uid()
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Validate source_id ownership
    CASE NEW.source_type::text
        WHEN 'task' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.tasks WHERE id = NEW.source_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'project' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.projects WHERE id = NEW.source_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'goal' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.goals WHERE id = NEW.source_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'memory' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.memories WHERE id = NEW.source_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'conversation' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.conversations WHERE id = NEW.source_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'message' THEN
            -- Messages don't have a direct user_id column; ownership is via conversation.
            SELECT EXISTS(
                SELECT 1
                FROM public.messages m
                JOIN public.conversations c ON c.id = m.conversation_id
                WHERE m.id = NEW.source_id AND c.user_id = NEW.user_id
            ) INTO v_ok;
        ELSE
            RAISE EXCEPTION 'record_links: invalid source_type %', NEW.source_type
                USING ERRCODE = 'invalid_parameter_value';
    END CASE;

    IF NOT v_ok THEN
        RAISE EXCEPTION 'record_links: source record (type=%, id=%) not found or not owned by user %',
            NEW.source_type, NEW.source_id, NEW.user_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Validate target_id ownership
    CASE NEW.target_type::text
        WHEN 'task' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.tasks WHERE id = NEW.target_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'project' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.projects WHERE id = NEW.target_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'goal' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.goals WHERE id = NEW.target_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'memory' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.memories WHERE id = NEW.target_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'conversation' THEN
            SELECT EXISTS(
                SELECT 1 FROM public.conversations WHERE id = NEW.target_id AND user_id = NEW.user_id
            ) INTO v_ok;
        WHEN 'message' THEN
            SELECT EXISTS(
                SELECT 1
                FROM public.messages m
                JOIN public.conversations c ON c.id = m.conversation_id
                WHERE m.id = NEW.target_id AND c.user_id = NEW.user_id
            ) INTO v_ok;
        ELSE
            RAISE EXCEPTION 'record_links: invalid target_type %', NEW.target_type
                USING ERRCODE = 'invalid_parameter_value';
    END CASE;

    IF NOT v_ok THEN
        RAISE EXCEPTION 'record_links: target record (type=%, id=%) not found or not owned by user %',
            NEW.target_type, NEW.target_id, NEW.user_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN NEW;
END;
$$;

-- ============================================================
-- Step 2: Attach trigger (idempotent via DROP IF EXISTS first)
-- ============================================================

DROP TRIGGER IF EXISTS trg_record_links_endpoint_ownership ON public.record_links;

CREATE TRIGGER trg_record_links_endpoint_ownership
    BEFORE INSERT OR UPDATE ON public.record_links
    FOR EACH ROW
    EXECUTE FUNCTION public.validate_record_link_endpoints();

-- ============================================================
-- Step 3: Grant execute on the SECURITY DEFINER function only to
--         the roles that need it (authenticated + service_role if present).
--         revoking from PUBLIC first prevents privilege escalation.
--         Also grant DML permissions on record_links to authenticated.
-- ============================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.record_links TO authenticated;

REVOKE ALL ON FUNCTION public.validate_record_link_endpoints() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.validate_record_link_endpoints() TO authenticated;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        GRANT EXECUTE ON FUNCTION public.validate_record_link_endpoints() TO service_role;
    END IF;
END $$;

COMMENT ON FUNCTION public.validate_record_link_endpoints() IS
    'SEC-01 (Phase 3C.5.2): Validates both endpoints of a record_link belong to the '
    'authenticated user. Prevents cross-tenant endpoint injection.';

