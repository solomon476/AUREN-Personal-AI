-- Migration: 003_security_hardening.sql
-- Description: Hardening relational integrity and cross-tenant parent checks in RLS policies
-- Security: Prevents linking child entities (messages, tasks, milestones) to foreign parent entities owned by other users

-- ============================================================================
-- 1. HARDEN MESSAGES POLICY (CROSS-TENANT CONVERSATION INJECTION PREVENTION)
-- ============================================================================
DROP POLICY IF EXISTS "messages_all_own" ON public.messages;

CREATE POLICY "messages_select_own" ON public.messages
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "messages_insert_own" ON public.messages
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = conversation_id AND c.user_id = auth.uid()
        )
    );

CREATE POLICY "messages_update_own" ON public.messages
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = conversation_id AND c.user_id = auth.uid()
        )
    );

CREATE POLICY "messages_delete_own" ON public.messages
    FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- ============================================================================
-- 2. HARDEN TASKS POLICY (CROSS-TENANT PROJECT LINKING PREVENTION)
-- ============================================================================
DROP POLICY IF EXISTS "tasks_all_own" ON public.tasks;

CREATE POLICY "tasks_select_own" ON public.tasks
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "tasks_insert_own" ON public.tasks
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id AND (
            project_id IS NULL OR
            EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = project_id AND p.user_id = auth.uid()
            )
        )
    );

CREATE POLICY "tasks_update_own" ON public.tasks
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (
        auth.uid() = user_id AND (
            project_id IS NULL OR
            EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = project_id AND p.user_id = auth.uid()
            )
        )
    );

CREATE POLICY "tasks_delete_own" ON public.tasks
    FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- ============================================================================
-- 3. HARDEN MILESTONES POLICY (CROSS-TENANT GOAL LINKING PREVENTION)
-- ============================================================================
DROP POLICY IF EXISTS "milestones_all_own" ON public.milestones;

CREATE POLICY "milestones_select_own" ON public.milestones
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "milestones_insert_own" ON public.milestones
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM public.goals g
            WHERE g.id = goal_id AND g.user_id = auth.uid()
        )
    );

CREATE POLICY "milestones_update_own" ON public.milestones
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM public.goals g
            WHERE g.id = goal_id AND g.user_id = auth.uid()
        )
    );

CREATE POLICY "milestones_delete_own" ON public.milestones
    FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- ============================================================================
-- 4. HARDEN FUNCTION PRIVILEGES (PREVENT ARBITRARY CALLS TO TRIGGER FUNCTIONS)
-- ============================================================================
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.handle_updated_at() FROM PUBLIC;

-- ============================================================================
-- 5. EXPLICIT ANON PRIVILEGE RESTRICTION
-- ============================================================================
-- Revoke all direct permissions from the unauthenticated anon role on private tables
REVOKE ALL ON TABLE public.profiles FROM anon;
REVOKE ALL ON TABLE public.projects FROM anon;
REVOKE ALL ON TABLE public.tasks FROM anon;
REVOKE ALL ON TABLE public.conversations FROM anon;
REVOKE ALL ON TABLE public.messages FROM anon;
REVOKE ALL ON TABLE public.memories FROM anon;
REVOKE ALL ON TABLE public.journal_entries FROM anon;
REVOKE ALL ON TABLE public.goals FROM anon;
REVOKE ALL ON TABLE public.milestones FROM anon;
REVOKE ALL ON TABLE public.briefings FROM anon;
