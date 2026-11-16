-- Migration: 020_parent_task_deletion_set_null.sql
-- Description:
-- 1. Update parent_task_id foreign key from ON DELETE CASCADE to ON DELETE SET NULL.
--    Ensures that deleting a parent task unlinks subtasks rather than destroying them,
--    preserving independently meaningful subtasks and user data integrity.
-- 2. Correct SQL column scoping in tasks_insert_own and tasks_update_own policies
--    so t.id compares against tasks.parent_task_id (rather than self-shadowing t.parent_task_id).

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT conname
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
        WHERE c.conrelid = 'public.tasks'::regclass
          AND c.contype = 'f'
          AND a.attname = 'parent_task_id'
    ) LOOP
        EXECUTE 'ALTER TABLE public.tasks DROP CONSTRAINT ' || quote_ident(r.conname);
    END LOOP;
END $$;

ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_parent_task_id_fkey
    FOREIGN KEY (parent_task_id)
    REFERENCES public.tasks(id)
    ON DELETE SET NULL;

-- Correct RLS policies to explicitly qualify tasks.parent_task_id, tasks.project_id, and tasks.goal_id
DROP POLICY IF EXISTS "tasks_insert_own" ON public.tasks;
CREATE POLICY "tasks_insert_own" ON public.tasks
    FOR INSERT
    WITH CHECK (
        user_id = auth.uid()
        AND (
            project_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = tasks.project_id AND p.user_id = auth.uid()
            )
        )
        AND (
            goal_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.goals g
                WHERE g.id = tasks.goal_id AND g.user_id = auth.uid()
            )
        )
        AND (
            parent_task_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.tasks t
                WHERE t.id = tasks.parent_task_id AND t.user_id = auth.uid()
            )
        )
    );

DROP POLICY IF EXISTS "tasks_update_own" ON public.tasks;
CREATE POLICY "tasks_update_own" ON public.tasks
    FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (
        user_id = auth.uid()
        AND (
            project_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = tasks.project_id AND p.user_id = auth.uid()
            )
        )
        AND (
            goal_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.goals g
                WHERE g.id = tasks.goal_id AND g.user_id = auth.uid()
            )
        )
        AND (
            parent_task_id IS NULL
            OR EXISTS (
                SELECT 1 FROM public.tasks t
                WHERE t.id = tasks.parent_task_id AND t.user_id = auth.uid()
            )
        )
    );
