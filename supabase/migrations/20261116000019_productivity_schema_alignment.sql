-- ============================================================================
-- AUREN Schema Migration: 20261116000019_productivity_schema_alignment.sql
-- Description: Align Projects, Tasks, and Goals schema for Phase 3C.4 Productivity Core:
--              - Support complete lifecycle status matrices for tasks, projects, and goals.
--              - Add start dates, target dates, completion timestamps, tags, and metrics.
--              - Establish cross-entity relationship foreign keys (project->goal, task->goal, task->parent_task).
--              - Harden RLS policies to prevent cross-tenant referencing across all productivity hierarchies.
--              - Add performance indexes for status, hierarchy, and deadline queries.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Projects Table Alignment
-- ----------------------------------------------------------------------------

-- Add new columns to public.projects
ALTER TABLE public.projects
    ADD COLUMN IF NOT EXISTS start_date DATE,
    ADD COLUMN IF NOT EXISTS target_date DATE,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS goal_id UUID REFERENCES public.goals(id) ON DELETE SET NULL;

-- Update status constraint on public.projects
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_status_check;
ALTER TABLE public.projects ADD CONSTRAINT projects_status_check 
    CHECK (status IN ('planning', 'active', 'on_hold', 'completed', 'cancelled', 'archived'));

-- Indexes for projects
CREATE INDEX IF NOT EXISTS idx_projects_goal_id ON public.projects(goal_id);
CREATE INDEX IF NOT EXISTS idx_projects_user_created ON public.projects(user_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 2. Goals Table Alignment
-- ----------------------------------------------------------------------------

-- Update legacy 'completed' status to 'achieved' if existing
UPDATE public.goals SET status = 'achieved' WHERE status = 'completed';

-- Add new columns to public.goals
ALTER TABLE public.goals
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS target_value NUMERIC,
    ADD COLUMN IF NOT EXISTS current_value NUMERIC DEFAULT 0,
    ADD COLUMN IF NOT EXISTS unit TEXT;

-- Update status constraint on public.goals
ALTER TABLE public.goals DROP CONSTRAINT IF EXISTS goals_status_check;
ALTER TABLE public.goals ADD CONSTRAINT goals_status_check 
    CHECK (status IN ('not_started', 'in_progress', 'achieved', 'paused', 'abandoned', 'completed'));

-- Indexes for goals
CREATE INDEX IF NOT EXISTS idx_goals_user_target_date ON public.goals(user_id, target_date);
CREATE INDEX IF NOT EXISTS idx_goals_user_created ON public.goals(user_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 3. Tasks Table Alignment
-- ----------------------------------------------------------------------------

-- Update legacy 'done' status to 'completed' if existing
UPDATE public.tasks SET status = 'completed' WHERE status = 'done';

-- Add new columns to public.tasks
ALTER TABLE public.tasks
    ADD COLUMN IF NOT EXISTS start_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS goal_id UUID REFERENCES public.goals(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS parent_task_id UUID REFERENCES public.tasks(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'::text[];

-- Update status constraint on public.tasks
ALTER TABLE public.tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE public.tasks ADD CONSTRAINT tasks_status_check 
    CHECK (status IN ('todo', 'in_progress', 'blocked', 'completed', 'cancelled'));

-- Indexes for tasks
CREATE INDEX IF NOT EXISTS idx_tasks_goal_id ON public.tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON public.tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status_due ON public.tasks(user_id, status, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_user_created ON public.tasks(user_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 4. RLS Security Hardening (Cross-Tenant Hierarchy Protection)
-- ----------------------------------------------------------------------------

-- Projects RLS: user owns project AND linked goal must be owned by the same user
DROP POLICY IF EXISTS "projects_all_own" ON public.projects;
DROP POLICY IF EXISTS "projects_select_own" ON public.projects;
DROP POLICY IF EXISTS "projects_insert_own" ON public.projects;
DROP POLICY IF EXISTS "projects_update_own" ON public.projects;
DROP POLICY IF EXISTS "projects_delete_own" ON public.projects;

CREATE POLICY "projects_select_own" ON public.projects
    FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "projects_insert_own" ON public.projects
    FOR INSERT
    WITH CHECK (
        user_id = auth.uid()
        AND (
            goal_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.goals g
                WHERE g.id = goal_id AND g.user_id = auth.uid()
            )
        )
    );

CREATE POLICY "projects_update_own" ON public.projects
    FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (
        user_id = auth.uid()
        AND (
            goal_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.goals g
                WHERE g.id = goal_id AND g.user_id = auth.uid()
            )
        )
    );

CREATE POLICY "projects_delete_own" ON public.projects
    FOR DELETE
    USING (user_id = auth.uid());

-- Tasks RLS: user owns task AND linked project, goal, and parent_task must belong to the same user
DROP POLICY IF EXISTS "tasks_select_own" ON public.tasks;
DROP POLICY IF EXISTS "tasks_insert_own" ON public.tasks;
DROP POLICY IF EXISTS "tasks_update_own" ON public.tasks;
DROP POLICY IF EXISTS "tasks_delete_own" ON public.tasks;

CREATE POLICY "tasks_select_own" ON public.tasks
    FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "tasks_insert_own" ON public.tasks
    FOR INSERT
    WITH CHECK (
        user_id = auth.uid()
        AND (
            project_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = project_id AND p.user_id = auth.uid()
            )
        )
        AND (
            goal_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.goals g
                WHERE g.id = goal_id AND g.user_id = auth.uid()
            )
        )
        AND (
            parent_task_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.tasks t
                WHERE t.id = parent_task_id AND t.user_id = auth.uid()
            )
        )
    );

CREATE POLICY "tasks_update_own" ON public.tasks
    FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (
        user_id = auth.uid()
        AND (
            project_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = project_id AND p.user_id = auth.uid()
            )
        )
        AND (
            goal_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.goals g
                WHERE g.id = goal_id AND g.user_id = auth.uid()
            )
        )
        AND (
            parent_task_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.tasks t
                WHERE t.id = parent_task_id AND t.user_id = auth.uid()
            )
        )
    );

CREATE POLICY "tasks_delete_own" ON public.tasks
    FOR DELETE
    USING (user_id = auth.uid());

-- Goals RLS: user owns goal
DROP POLICY IF EXISTS "goals_all_own" ON public.goals;
DROP POLICY IF EXISTS "goals_select_own" ON public.goals;
DROP POLICY IF EXISTS "goals_insert_own" ON public.goals;
DROP POLICY IF EXISTS "goals_update_own" ON public.goals;
DROP POLICY IF EXISTS "goals_delete_own" ON public.goals;

CREATE POLICY "goals_select_own" ON public.goals
    FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "goals_insert_own" ON public.goals
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "goals_update_own" ON public.goals
    FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "goals_delete_own" ON public.goals
    FOR DELETE
    USING (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- 5. Role Permissions
-- ----------------------------------------------------------------------------
REVOKE ALL ON TABLE public.projects FROM anon;
REVOKE ALL ON TABLE public.tasks FROM anon;
REVOKE ALL ON TABLE public.goals FROM anon;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.projects TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.tasks TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.goals TO authenticated;

