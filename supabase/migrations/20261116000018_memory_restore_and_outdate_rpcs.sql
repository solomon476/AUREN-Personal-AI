-- ============================================================================
-- AUREN Schema Migration: 20261116000018_memory_restore_and_outdate_rpcs.sql
-- Description: Implement dedicated SECURITY DEFINER RPCs for memory lifecycle
--              transitions: restore_memory_rpc and outdate_memory_rpc.
--
-- Security Rationale:
--   Migration 011 revoked direct write policies on public.memories, restricting
--   mutations exclusively to SECURITY DEFINER RPCs. Direct PostgREST PATCH
--   requests violate this security invariant and are blocked by RLS.
--   This migration introduces dedicated, ownership-enforcing, audit-safe RPCs
--   for memory restoration (archived/expired -> active) and outdating (active -> expired).
-- ============================================================================

-- Function: restore_memory_rpc
-- Restores an archived or expired memory back to active status.
-- Terminal states (superseded, forgotten, rejected) cannot be reactivated.
CREATE OR REPLACE FUNCTION public.restore_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_current_status TEXT;
    v_conf_status TEXT;
BEGIN
    -- 1. Derive user identity from authenticated JWT context
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    -- 2. Verify ownership and restorable lifecycle status with row-level lock
    SELECT lifecycle_status, confirmation_status 
    INTO v_current_status, v_conf_status
    FROM public.memories
    WHERE id = p_memory_id AND user_id = v_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Memory not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    -- Disallow reviving rejected memories
    IF v_conf_status = 'rejected' THEN
        RAISE EXCEPTION 'Cannot restore rejected memory' USING ERRCODE = '22023';
    END IF;

    -- Only archived or expired memories are eligible for restoration
    IF v_current_status NOT IN ('archived', 'expired') THEN
        RAISE EXCEPTION 'Cannot restore memory with lifecycle status: %', v_current_status USING ERRCODE = '22023';
    END IF;

    -- 3. Atomically transition to active status
    UPDATE public.memories
    SET lifecycle_status = 'active',
        updated_at = now()
    WHERE id = p_memory_id
      AND user_id = v_user_id;

    RETURN TRUE;
END;
$$;

-- Function: outdate_memory_rpc
-- Transitions an active memory to expired status.
CREATE OR REPLACE FUNCTION public.outdate_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_current_status TEXT;
    v_conf_status TEXT;
BEGIN
    -- 1. Derive user identity from authenticated JWT context
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    -- 2. Verify ownership and active lifecycle status with row-level lock
    SELECT lifecycle_status, confirmation_status
    INTO v_current_status, v_conf_status
    FROM public.memories
    WHERE id = p_memory_id AND user_id = v_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Memory not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_conf_status = 'rejected' THEN
        RAISE EXCEPTION 'Cannot outdate rejected memory' USING ERRCODE = '22023';
    END IF;

    IF v_current_status != 'active' THEN
        RAISE EXCEPTION 'Cannot outdate memory with lifecycle status: %', v_current_status USING ERRCODE = '22023';
    END IF;

    -- 3. Atomically transition to expired status
    UPDATE public.memories
    SET lifecycle_status = 'expired',
        updated_at = now()
    WHERE id = p_memory_id
      AND user_id = v_user_id;

    RETURN TRUE;
END;
$$;

-- ============================================================================
-- Explicit Permission Grants
-- ============================================================================

-- Revoke all public / anonymous execute permissions
REVOKE ALL ON FUNCTION public.restore_memory_rpc(UUID) FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.outdate_memory_rpc(UUID) FROM PUBLIC, anon, authenticated, auren_worker;

-- Explicitly grant execute to authenticated users only
GRANT EXECUTE ON FUNCTION public.restore_memory_rpc(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.outdate_memory_rpc(UUID) TO authenticated;

