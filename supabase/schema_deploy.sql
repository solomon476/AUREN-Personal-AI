-- Migration: 001_core_schema.sql
-- Description: Core tables for AUREN Personal AI Assistant Platform
-- Security: Defines strictly typed schemas with user_id foreign keys to auth.users

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. PROFILES
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    preferences JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 2. PROJECTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT DEFAULT '#4872bd',
    status TEXT DEFAULT 'active' NOT NULL CHECK (status IN ('active', 'archived', 'completed')),
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 3. TASKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES public.projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'todo' NOT NULL CHECK (status IN ('todo', 'in_progress', 'done', 'cancelled')),
    priority TEXT DEFAULT 'medium' NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    due_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 4. CONVERSATIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT DEFAULT 'New Conversation' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 5. MESSAGES
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 6. MEMORIES
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'general' NOT NULL CHECK (category IN ('general', 'preference', 'fact', 'work', 'personal')),
    importance INT DEFAULT 1 NOT NULL CHECK (importance BETWEEN 1 AND 5),
    source_message_id UUID REFERENCES public.messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 7. JOURNAL ENTRIES
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT,
    content TEXT NOT NULL,
    mood TEXT,
    tags TEXT[] DEFAULT '{}'::text[] NOT NULL,
    is_private BOOLEAN DEFAULT TRUE NOT NULL,
    entry_date DATE DEFAULT CURRENT_DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 8. GOALS
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    target_date DATE,
    status TEXT DEFAULT 'in_progress' NOT NULL CHECK (status IN ('not_started', 'in_progress', 'completed', 'abandoned')),
    progress_percent INT DEFAULT 0 NOT NULL CHECK (progress_percent BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 9. MILESTONES
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES public.goals(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_date DATE,
    is_completed BOOLEAN DEFAULT FALSE NOT NULL,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- ============================================================================
-- 10. BRIEFINGS
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    briefing_date DATE DEFAULT CURRENT_DATE NOT NULL,
    summary TEXT NOT NULL,
    agenda JSONB DEFAULT '[]'::jsonb NOT NULL,
    active_goals_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Migration: 002_rls_and_triggers.sql
-- Description: Row Level Security (RLS) policies, triggers, and performance indexes
-- Security: Strict user isolation where every user can only view, create, edit, or delete their own records

-- ============================================================================
-- 1. AUTOMATIC TIMESTAMP MANAGEMENT
-- ============================================================================
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers to all tables with an updated_at column
DROP TRIGGER IF EXISTS set_profiles_updated_at ON public.profiles;
CREATE TRIGGER set_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS set_projects_updated_at ON public.projects;
CREATE TRIGGER set_projects_updated_at
    BEFORE UPDATE ON public.projects
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS set_tasks_updated_at ON public.tasks;
CREATE TRIGGER set_tasks_updated_at
    BEFORE UPDATE ON public.tasks
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS set_conversations_updated_at ON public.conversations;
CREATE TRIGGER set_conversations_updated_at
    BEFORE UPDATE ON public.conversations
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS set_memories_updated_at ON public.memories;
CREATE TRIGGER set_memories_updated_at
    BEFORE UPDATE ON public.memories
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS set_journal_entries_updated_at ON public.journal_entries;
CREATE TRIGGER set_journal_entries_updated_at
    BEFORE UPDATE ON public.journal_entries
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS set_goals_updated_at ON public.goals;
CREATE TRIGGER set_goals_updated_at
    BEFORE UPDATE ON public.goals
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- ============================================================================
-- 2. AUTOMATIC PROFILE CREATION TRIGGER (AUTH.USERS SIGNUP)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, avatar_url)
    VALUES (
        NEW.id,
        COALESCE(NEW.email, ''),
        COALESCE(NEW.raw_user_meta_data->>'full_name', ''),
        COALESCE(NEW.raw_user_meta_data->>'avatar_url', '')
    )
    ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- Attach trigger to auth.users (if running on Supabase instance)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_namespace WHERE nspname = 'auth'
    ) THEN
        DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
    END IF;
END $$;

-- ============================================================================
-- 3. ENABLE AND FORCE ROW LEVEL SECURITY (RLS) ON ALL TABLES
-- ============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles FORCE ROW LEVEL SECURITY;

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects FORCE ROW LEVEL SECURITY;

ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks FORCE ROW LEVEL SECURITY;

ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations FORCE ROW LEVEL SECURITY;

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages FORCE ROW LEVEL SECURITY;

ALTER TABLE public.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories FORCE ROW LEVEL SECURITY;

ALTER TABLE public.journal_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.journal_entries FORCE ROW LEVEL SECURITY;

ALTER TABLE public.goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.goals FORCE ROW LEVEL SECURITY;

ALTER TABLE public.milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.milestones FORCE ROW LEVEL SECURITY;

ALTER TABLE public.briefings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.briefings FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- 4. ROW LEVEL SECURITY POLICIES
-- ============================================================================

-- Profiles: Users can only read, insert, and update their own profile
CREATE POLICY "profiles_select_own" ON public.profiles
    FOR SELECT TO authenticated USING (auth.uid() = id);

CREATE POLICY "profiles_insert_own" ON public.profiles
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = id);

CREATE POLICY "profiles_update_own" ON public.profiles
    FOR UPDATE TO authenticated USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- Projects: Full isolation by user_id
CREATE POLICY "projects_all_own" ON public.projects
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Tasks: Full isolation by user_id
CREATE POLICY "tasks_all_own" ON public.tasks
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Conversations: Full isolation by user_id
CREATE POLICY "conversations_all_own" ON public.conversations
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Messages: Full isolation by user_id
CREATE POLICY "messages_all_own" ON public.messages
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Memories: Full isolation by user_id
CREATE POLICY "memories_all_own" ON public.memories
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Journal Entries: Strict privacy isolation by user_id
CREATE POLICY "journal_entries_all_own" ON public.journal_entries
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Goals: Full isolation by user_id
CREATE POLICY "goals_all_own" ON public.goals
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Milestones: Full isolation by user_id
CREATE POLICY "milestones_all_own" ON public.milestones
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Briefings: Full isolation by user_id
CREATE POLICY "briefings_all_own" ON public.briefings
    FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- 5. PERFORMANCE AND INTEGRITY INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_projects_user_status ON public.projects(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON public.tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON public.tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON public.tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON public.conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conv_created ON public.messages(conversation_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON public.messages(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_user_category ON public.memories(user_id, category);
CREATE INDEX IF NOT EXISTS idx_journal_user_entry_date ON public.journal_entries(user_id, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_goals_user_status ON public.goals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_milestones_goal_id ON public.milestones(goal_id);
CREATE INDEX IF NOT EXISTS idx_milestones_user_id ON public.milestones(user_id);
CREATE INDEX IF NOT EXISTS idx_briefings_user_date ON public.briefings(user_id, briefing_date DESC);

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

-- Migration: 004_chat_idempotency.sql
-- Description: Adds idempotency_key to messages table to prevent duplicate AI requests and message duplication on network retry

ALTER TABLE public.messages
ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

-- Enforce unique idempotency keys per user to guarantee deduplication on network retries
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_user_idempotency
ON public.messages (user_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

-- Migration: 005_chat_requests_idempotency.sql
-- Description: State table tracking chat request lifecycle for strict idempotency, deduplication, and recovery

CREATE TABLE IF NOT EXISTS public.chat_requests (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed', 'interrupted')),
    user_message_id UUID NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
    assistant_message_id UUID REFERENCES public.messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (user_id, idempotency_key)
);

-- Automatic timestamp management
DROP TRIGGER IF EXISTS set_chat_requests_updated_at ON public.chat_requests;
CREATE TRIGGER set_chat_requests_updated_at
    BEFORE UPDATE ON public.chat_requests
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Enable and force Row Level Security
ALTER TABLE public.chat_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_requests FORCE ROW LEVEL SECURITY;

CREATE POLICY "chat_requests_all_own" ON public.chat_requests
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Performance and lookup index
CREATE INDEX IF NOT EXISTS idx_chat_requests_user_status ON public.chat_requests(user_id, status);
-- Migration: 006_chat_requests_fingerprint.sql
-- Description: Add immutable request_fingerprint column to chat_requests table to bind idempotency keys to request content

ALTER TABLE public.chat_requests ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;

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

-- Migration: 009_strict_lifecycle_matrix_and_exclusive_claim.sql
-- Description: Strict lifecycle transition matrix, exclusive RPC claiming, hex fingerprint enforcement,
--              and dedicated reconciliation RPC.

-- ============================================================================
-- 1. BACKFILL AND ENFORCE 64-CHARACTER HEXADECIMAL REQUEST FINGERPRINT
-- ============================================================================

-- Dynamically configure session search_path to locate digest regardless of whether
-- pgcrypto was installed in public or extensions.
DO $$
DECLARE
    v_schema TEXT;
BEGIN
    SELECT n.nspname INTO v_schema
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE p.proname = 'digest'
    LIMIT 1;

    IF v_schema IS NOT NULL AND v_schema NOT IN ('public', 'pg_catalog') THEN
        EXECUTE 'SET search_path TO ' || current_setting('search_path') || ', ' || quote_ident(v_schema);
    END IF;
END;
$$;

-- Backfill any legacy NULL request_fingerprint with deterministic 64-hex SHA-256 hash
UPDATE public.chat_requests
SET request_fingerprint = encode(digest(convert_to('legacy:' || user_id::text || ':' || idempotency_key, 'UTF8'), 'sha256'), 'hex')
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
SET search_path = public, extensions, pg_temp
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
SET search_path = public, extensions, pg_temp
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
SET search_path = public, extensions, pg_temp
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
SET search_path = public, extensions, pg_temp
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
SET search_path = public, extensions, pg_temp
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
SET search_path = public, extensions, pg_temp
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

-- Migration: 010_correct_legacy_fingerprints_and_pgcrypto.sql
-- Description: Correct legacy fingerprint backfill matching application normalization semantics,
--              preserve original request conversation-ID semantics (conv:none vs conv:<uuid>),
--              safely resolve pgcrypto without static schema qualifications, enforce user-message
--              immutability, safely resolve migration 009/010 trigger conflict transactionally,
--              and apply strict compatibility policies for unreconstructable records.

-- ============================================================================
-- 1. VERIFY PGCRYPTO EXTENSION DEPENDENCY & DYNAMIC SCHEMA RESOLUTION
-- ============================================================================

-- Ensure pgcrypto extension is installed
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Dynamically configure session search_path to locate digest regardless of whether
-- pgcrypto was installed in public or extensions, avoiding static schema qualifications.
DO $$
DECLARE
    v_schema TEXT;
BEGIN
    SELECT n.nspname INTO v_schema
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE p.proname = 'digest'
    LIMIT 1;

    IF v_schema IS NOT NULL AND v_schema NOT IN ('public', 'pg_catalog') THEN
        EXECUTE 'SET search_path TO ' || current_setting('search_path') || ', ' || quote_ident(v_schema);
    END IF;
END;
$$;

-- ============================================================================
-- 2. NORMALIZATION & FINGERPRINT FUNCTIONS (EXACT APPLICATION PARITY)
-- ============================================================================

-- Function: normalize_chat_content
-- Matches Python exactly: "\n".join(line.rstrip() for line in content.strip().splitlines())
-- Handles all 29 Unicode whitespace characters and all 11 line boundary representations.
CREATE OR REPLACE FUNCTION public.normalize_chat_content(p_content TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_whitespace TEXT;
    v_line_sep TEXT;
    v_trimmed TEXT;
    v_lines TEXT[];
    v_line TEXT;
    v_cleaned TEXT[] := ARRAY[]::TEXT[];
BEGIN
    IF p_content IS NULL THEN
        RETURN '';
    END IF;

    -- All 29 Unicode whitespace characters matching Python's str.isspace()
    v_whitespace := chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288);

    -- 1. Strip leading and trailing whitespace from the complete content
    v_trimmed := trim(both v_whitespace FROM p_content);
    IF v_trimmed = '' THEN
        RETURN '';
    END IF;

    -- All 11 line boundary representations recognized by Python's str.splitlines()
    -- \r\n (CRLF) is first to avoid splitting into two empty lines
    v_line_sep := chr(13) || chr(10) || '|[' || chr(10) || chr(13) || chr(11) || chr(12) || chr(28) || chr(29) || chr(30) || chr(133) || chr(8232) || chr(8233) || ']';

    -- 2. Split into lines
    v_lines := regexp_split_to_array(v_trimmed, v_line_sep);
    FOREACH v_line IN ARRAY v_lines LOOP
        -- Remove trailing whitespace from each line
        v_cleaned := array_append(v_cleaned, rtrim(v_line, v_whitespace));
    END LOOP;

    -- 3. Join lines using newline character
    RETURN array_to_string(v_cleaned, chr(10));
END;
$$;

-- Function: compute_deterministic_conversation_id_sql
-- Generates exact RFC 4122 UUIDv5 for namespace OID: 6ba7b812-9dad-11d1-80b4-00c04fd430c8
-- Matching Python: uuid.uuid5(uuid.NAMESPACE_OID, f"auren:conv:{user_id}:{idempotency_key}")
CREATE OR REPLACE FUNCTION public.compute_deterministic_conversation_id_sql(
    p_user_id UUID,
    p_idempotency_key TEXT
)
RETURNS UUID
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_data BYTEA;
    v_hash BYTEA;
    v_hex TEXT;
    v_b6_v5 TEXT;
    v_b8_var TEXT;
    v_b8_int INT;
    v_uuid_str TEXT;
BEGIN
    -- Namespace OID bytes: 6ba7b8129dad11d180b400c04fd430c8
    v_data := decode('6ba7b8129dad11d180b400c04fd430c8', 'hex') || 
              convert_to('auren:conv:' || p_user_id::TEXT || ':' || p_idempotency_key, 'UTF8');
    v_hash := digest(v_data, 'sha1');
    v_hex := encode(v_hash, 'hex');

    -- Version 5: high nibble of byte 7 (0-indexed char 13..14) is 5
    v_b6_v5 := '5' || substr(v_hex, 14, 1);

    -- Variant RFC 4122: high 2 bits of byte 9 (0-indexed char 17..18) are 10
    v_b8_int := ('x' || substr(v_hex, 17, 2))::bit(8)::int;
    v_b8_int := (v_b8_int & 63) | 128;
    v_b8_var := lpad(to_hex(v_b8_int), 2, '0');

    v_uuid_str := substr(v_hex, 1, 8) || '-' ||
                  substr(v_hex, 9, 4) || '-' ||
                  v_b6_v5 || substr(v_hex, 15, 2) || '-' ||
                  v_b8_var || substr(v_hex, 19, 2) || '-' ||
                  substr(v_hex, 21, 12);

    RETURN v_uuid_str::UUID;
END;
$$;

-- Function: compute_request_fingerprint_sql
-- Matches Python: hashlib.sha256(f"user:{user_id}|conv:{conv_part}|content:{normalized}").hexdigest()
CREATE OR REPLACE FUNCTION public.compute_request_fingerprint_sql(
    p_user_id UUID,
    p_conversation_id UUID,
    p_content TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_normalized TEXT;
    v_conv_part TEXT;
    v_payload TEXT;
    v_hash BYTEA;
BEGIN
    v_normalized := public.normalize_chat_content(p_content);
    v_conv_part := CASE WHEN p_conversation_id IS NOT NULL THEN p_conversation_id::TEXT ELSE 'none' END;
    v_payload := 'user:' || p_user_id::TEXT || '|conv:' || v_conv_part || '|content:' || v_normalized;

    v_hash := digest(convert_to(v_payload, 'UTF8'), 'sha256');

    RETURN encode(v_hash, 'hex');
END;
$$;

-- ============================================================================
-- 3. PROVENANCE INTEGRITY & IMMUTABILITY TRIGGER ON USER MESSAGES
-- ============================================================================

-- Function: handle_messages_immutability
-- Enforces that user message content is immutable once created.
CREATE OR REPLACE FUNCTION public.handle_messages_immutability()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF OLD.role = 'user' AND NEW.content IS DISTINCT FROM OLD.content THEN
        RAISE EXCEPTION 'User message content is immutable and cannot be modified';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_messages_user_content_immutability ON public.messages;
CREATE TRIGGER trg_messages_user_content_immutability
BEFORE UPDATE ON public.messages
FOR EACH ROW
EXECUTE FUNCTION public.handle_messages_immutability();

-- ============================================================================
-- 4. LEGACY FINGERPRINT RECONSTRUCTION & COMPATIBILITY POLICY
-- ============================================================================

-- Step 4a: Compatibility Policy for unreconstructable legacy records:
-- A legacy request must only be reconstructed when its source message satisfies ALL of these conditions:
--   1. messages.id = chat_requests.user_message_id
--   2. messages.user_id = chat_requests.user_id
--   3. messages.conversation_id = chat_requests.conversation_id
--   4. messages.role = 'user'
--   5. Existing provenance metadata checks permit reconstruction (not edited, content not changed, no original_content)
-- Any legacy record failing ANY of these checks cannot be proved and must be purged from chat_requests
-- per compatibility policy to prevent fabricating false fingerprints that cause permanent HTTP 409 collisions.
DELETE FROM public.chat_requests cr
WHERE NOT EXISTS (
    SELECT 1 FROM public.messages m
    WHERE m.id = cr.user_message_id
      AND m.user_id = cr.user_id
      AND m.conversation_id = cr.conversation_id
      AND m.role = 'user'
      AND COALESCE(m.metadata->>'edited' = 'true', FALSE) IS FALSE
      AND COALESCE(m.metadata->>'content_changed' = 'true', FALSE) IS FALSE
      AND NOT (m.metadata ? 'original_content')
);

-- Step 4b: Safe, Transactional Migration-Only Trigger Update
-- Migration 009 created trg_chat_requests_immutability which prevents updating request_fingerprint.
-- We temporarily grant authorization strictly for replacing the known synthetic hash or NULL,
-- guarded by a session configuration flag.
CREATE OR REPLACE FUNCTION public.handle_chat_requests_immutability()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint THEN
        IF current_setting('auren.allow_legacy_fingerprint_reconstruction', true) = 'on'
           AND (
               OLD.request_fingerprint IS NULL
               OR OLD.request_fingerprint = encode(digest(convert_to('legacy:' || OLD.user_id::text || ':' || OLD.idempotency_key, 'UTF8'), 'sha256'), 'hex')
           ) THEN
            -- Permitted: strictly authorized replacement of legacy synthetic or NULL hash
            NULL;
        ELSE
            RAISE EXCEPTION 'request_fingerprint is immutable and cannot be modified' USING ERRCODE = '22023';
        END IF;
    END IF;

    IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        RAISE EXCEPTION 'user_id is immutable and cannot be transferred' USING ERRCODE = '42501';
    END IF;

    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
        RAISE EXCEPTION 'idempotency_key is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    IF NEW.conversation_id IS DISTINCT FROM OLD.conversation_id THEN
        RAISE EXCEPTION 'conversation_id is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    IF NEW.user_message_id IS DISTINCT FROM OLD.user_message_id THEN
        RAISE EXCEPTION 'user_message_id is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'created_at is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 4c: Execute transactional backfill with temporary migration-only session flag
DO $$
BEGIN
    PERFORM set_config('auren.allow_legacy_fingerprint_reconstruction', 'on', true);

    -- Reconstruct fingerprints for all pristine legacy records:
    -- Determine whether original request supplied conversation ID:
    --   - cr.conversation_id == deterministic_conv_id: request supplied NO conversation ID -> conv:none (NULL)
    --   - cr.conversation_id != deterministic_conv_id: request supplied explicit conversation ID -> conv:<uuid>
    UPDATE public.chat_requests cr
    SET request_fingerprint = public.compute_request_fingerprint_sql(
        cr.user_id,
        CASE 
            WHEN cr.conversation_id = public.compute_deterministic_conversation_id_sql(cr.user_id, cr.idempotency_key)
            THEN NULL
            ELSE cr.conversation_id
        END,
        m.content
    )
    FROM public.messages m
    WHERE cr.user_message_id = m.id
      AND m.user_id = cr.user_id
      AND m.conversation_id = cr.conversation_id
      AND m.role = 'user'
      AND COALESCE(m.metadata->>'edited' = 'true', FALSE) IS FALSE
      AND COALESCE(m.metadata->>'content_changed' = 'true', FALSE) IS FALSE
      AND NOT (m.metadata ? 'original_content')
      AND (
          cr.request_fingerprint IS NULL
          OR cr.request_fingerprint !~ '^[0-9a-fA-F]{64}$'
          OR cr.request_fingerprint = encode(digest(convert_to('legacy:' || cr.user_id::text || ':' || cr.idempotency_key, 'UTF8'), 'sha256'), 'hex')
      );

    PERFORM set_config('auren.allow_legacy_fingerprint_reconstruction', 'off', true);
END;
$$;

-- Step 4d: Restore Permanent Strict Immutability Trigger Function
CREATE OR REPLACE FUNCTION public.handle_chat_requests_immutability()
RETURNS TRIGGER AS $$
BEGIN
    -- Strict permanent immutability: request_fingerprint can NEVER be modified once assigned
    IF NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint THEN
        RAISE EXCEPTION 'request_fingerprint is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        RAISE EXCEPTION 'user_id is immutable and cannot be transferred' USING ERRCODE = '42501';
    END IF;

    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
        RAISE EXCEPTION 'idempotency_key is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    IF NEW.conversation_id IS DISTINCT FROM OLD.conversation_id THEN
        RAISE EXCEPTION 'conversation_id is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    IF NEW.user_message_id IS DISTINCT FROM OLD.user_message_id THEN
        RAISE EXCEPTION 'user_message_id is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'created_at is immutable and cannot be modified' USING ERRCODE = '22023';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chat_requests_immutability ON public.chat_requests;
CREATE TRIGGER trg_chat_requests_immutability
    BEFORE UPDATE ON public.chat_requests
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_chat_requests_immutability();

-- Any remaining records with NULL, synthetic or unreconstructed fingerprint cannot be reconstructed: purge per compatibility policy
DELETE FROM public.chat_requests
WHERE request_fingerprint IS NULL
   OR request_fingerprint = encode(digest(convert_to('legacy:' || user_id::text || ':' || idempotency_key, 'UTF8'), 'sha256'), 'hex')
   OR request_fingerprint !~ '^[0-9a-fA-F]{64}$';

-- ============================================================================
-- 5. ENFORCE STRICT TABLE CONSTRAINTS
-- ============================================================================

ALTER TABLE public.chat_requests
    ALTER COLUMN request_fingerprint SET NOT NULL;

ALTER TABLE public.chat_requests
    DROP CONSTRAINT IF EXISTS chat_requests_fingerprint_hex_check;

ALTER TABLE public.chat_requests
    ADD CONSTRAINT chat_requests_fingerprint_hex_check
    CHECK (request_fingerprint ~ '^[0-9a-fA-F]{64}$');

-- ============================================================================
-- 6. REINFORCE SEARCH PATH ON ALL SECURITY DEFINER RPCS
-- ============================================================================

ALTER FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.complete_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.fail_chat_request(TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.interrupt_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.retry_chat_request(TEXT) SET search_path = public, extensions, pg_temp;
ALTER FUNCTION public.reconcile_chat_request(TEXT, UUID) SET search_path = public, extensions, pg_temp;

-- ============================================================================
-- 7. AUDIT & RE-ASSERT LEAST-PRIVILEGE TABLE & RPC PERMISSIONS
-- ============================================================================

-- Ensure all direct mutations on chat_requests remain strictly revoked
REVOKE INSERT, UPDATE, DELETE ON public.chat_requests FROM authenticated, anon, public;
GRANT SELECT ON public.chat_requests TO authenticated;

-- Ensure execute on all lifecycle RPCs is granted strictly to authenticated
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
-- Migration: 011_foundational_memory_schema_and_security.sql
-- Description: Foundational PostgreSQL memory schema, decoupled vector embeddings table,
--              active embedding model registry, single-use journal consent ledger,
--              durable asynchronous extraction job queue, hardened RLS policies,
--              and least-privilege lifecycle mutation RPCs.

-- ============================================================================
-- 1. EXTENSIONS & DYNAMIC SEARCH PATH
-- ============================================================================

-- Enable pgvector extension if available
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 2. ACTIVE EMBEDDING MODEL REGISTRY
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.embedding_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    dimension INT NOT NULL,
    vector_column TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT embedding_models_provider_model_ver_key UNIQUE (provider, model, version)
);

-- Seed initial supported models
INSERT INTO public.embedding_models (provider, model, version, dimension, vector_column, is_active)
VALUES 
    ('gemini', 'text-embedding-004', 'v1', 768, 'embedding_768', TRUE),
    ('openai', 'text-embedding-3-small', 'v1', 1536, 'embedding_1536', FALSE)
ON CONFLICT (provider, model, version) DO UPDATE 
SET is_active = EXCLUDED.is_active;

-- ============================================================================
-- 3. ENHANCE CORE MEMORIES SCHEMA (NON-DESTRUCTIVE MIGRATION)
-- ============================================================================

-- Add new columns with safe defaults to preserve any existing records
ALTER TABLE public.memories
    ADD COLUMN IF NOT EXISTS memory_type TEXT DEFAULT 'fact',
    ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'explicit_user_statement',
    ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS confirmation_status TEXT DEFAULT 'confirmed',
    ADD COLUMN IF NOT EXISTS lifecycle_status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS review_after TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_confirmed_at TIMESTAMPTZ DEFAULT now(),
    ADD COLUMN IF NOT EXISTS superseded_by_id UUID REFERENCES public.memories(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS previous_version_id UUID REFERENCES public.memories(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS root_memory_id UUID REFERENCES public.memories(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS source_conversation_id UUID REFERENCES public.conversations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS access_count INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb NOT NULL;

-- Conservative mapping of legacy categories without fabricating domain information
UPDATE public.memories SET
    memory_type = CASE 
        WHEN category = 'preference' THEN 'preference'
        ELSE 'fact'
    END,
    category = CASE 
        WHEN category = 'preference' THEN 'general'
        WHEN category IN ('work', 'personal') THEN category
        ELSE 'general'
    END,
    root_memory_id = id,
    last_confirmed_at = created_at
WHERE root_memory_id IS NULL;

-- Replace legacy category check constraint with orthogonal taxonomy constraints
ALTER TABLE public.memories
    DROP CONSTRAINT IF EXISTS memories_category_check;

ALTER TABLE public.memories
    ADD CONSTRAINT memories_memory_type_check 
        CHECK (memory_type IN ('fact', 'preference', 'goal', 'project', 'context', 'observation')),
    ADD CONSTRAINT memories_category_check 
        CHECK (category IN ('personal', 'work', 'technical', 'health_lifestyle', 'financial', 'general')),
    ADD CONSTRAINT memories_lifecycle_status_check 
        CHECK (lifecycle_status IN ('active', 'superseded', 'expired', 'archived', 'rejected')),
    ADD CONSTRAINT memories_confirmation_status_check 
        CHECK (confirmation_status IN ('confirmed', 'unconfirmed', 'rejected', 'system_asserted')),
    ADD CONSTRAINT memories_origin_check 
        CHECK (origin IN ('explicit_user_statement', 'inferred_dialogue', 'user_direct_input', 'system_import')),
    ADD CONSTRAINT memories_confidence_range_check 
        CHECK (confidence >= 0.0 AND confidence <= 1.0);

-- Enforce NOT NULL on core attributes
ALTER TABLE public.memories
    ALTER COLUMN memory_type SET NOT NULL,
    ALTER COLUMN category SET NOT NULL,
    ALTER COLUMN origin SET NOT NULL,
    ALTER COLUMN confidence SET NOT NULL,
    ALTER COLUMN confirmation_status SET NOT NULL,
    ALTER COLUMN lifecycle_status SET NOT NULL,
    ALTER COLUMN last_confirmed_at SET NOT NULL,
    ALTER COLUMN access_count SET NOT NULL;

-- Performance indexes for active retrieval and lineage lookups
CREATE INDEX IF NOT EXISTS idx_memories_active_retrieval
    ON public.memories(user_id, lifecycle_status, memory_type)
    WHERE lifecycle_status = 'active';

CREATE INDEX IF NOT EXISTS idx_memories_lineage
    ON public.memories(root_memory_id, previous_version_id);

CREATE INDEX IF NOT EXISTS idx_memories_fts
    ON public.memories USING GIN (to_tsvector('simple', content));

-- ============================================================================
-- 4. DECOUPLED AUXILIARY VECTOR EMBEDDINGS
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.memory_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL REFERENCES public.memories(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    dimension INT NOT NULL,
    embedding_768 vector(768),
    embedding_1536 vector(1536),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT memory_embeddings_unique_model UNIQUE (memory_id, provider, model, version)
);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_user_memory
    ON public.memory_embeddings(user_id, memory_id);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_768_hnsw
    ON public.memory_embeddings USING hnsw (embedding_768 vector_cosine_ops)
    WHERE is_active = TRUE AND embedding_768 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_1536_hnsw
    ON public.memory_embeddings USING hnsw (embedding_1536 vector_cosine_ops)
    WHERE is_active = TRUE AND embedding_1536 IS NOT NULL;

-- ============================================================================
-- 5. SINGLE-USE JOURNAL CONSENT LEDGER
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.consumed_consent_tokens (
    nonce UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    scope TEXT NOT NULL,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_consumed_consent_user_conv
    ON public.consumed_consent_tokens(user_id, conversation_id, idempotency_key);

-- ============================================================================
-- 6. DURABLE ASYNCHRONOUS EXTRACTION QUEUE
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.memory_extraction_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    source_message_id UUID NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead_letter')),
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    last_error TEXT,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    locked_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT memory_extraction_jobs_unique_msg UNIQUE (user_id, source_message_id)
);

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_poll
    ON public.memory_extraction_jobs(status, scheduled_at, lease_expires_at)
    WHERE status IN ('pending', 'failed', 'processing');

-- ============================================================================
-- 7. REINFORCE LEAST-PRIVILEGE GRANTS & RLS POLICIES
-- ============================================================================

-- Revoke all direct client write access
REVOKE ALL ON public.memories FROM anon, authenticated, public;
REVOKE ALL ON public.memory_embeddings FROM anon, authenticated, public;
REVOKE ALL ON public.consumed_consent_tokens FROM anon, authenticated, public;
REVOKE ALL ON public.memory_extraction_jobs FROM anon, authenticated, public;
REVOKE ALL ON public.embedding_models FROM anon, authenticated, public;

-- Grant selective read-only access to authenticated clients
GRANT SELECT ON public.memories TO authenticated;
GRANT SELECT ON public.embedding_models TO authenticated;

-- Ensure RLS is enabled and forced
ALTER TABLE public.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories FORCE ROW LEVEL SECURITY;

ALTER TABLE public.memory_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_embeddings FORCE ROW LEVEL SECURITY;

ALTER TABLE public.consumed_consent_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.consumed_consent_tokens FORCE ROW LEVEL SECURITY;

ALTER TABLE public.memory_extraction_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_extraction_jobs FORCE ROW LEVEL SECURITY;

ALTER TABLE public.embedding_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.embedding_models FORCE ROW LEVEL SECURITY;

-- Drop legacy permissive policies on memories
DROP POLICY IF EXISTS "memories_all_own" ON public.memories;
DROP POLICY IF EXISTS "memories_select_own" ON public.memories;

-- Read-only RLS policy for memories
CREATE POLICY "memories_select_own" ON public.memories
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

-- Read-only RLS policy for embedding models
DROP POLICY IF EXISTS "embedding_models_select" ON public.embedding_models;
CREATE POLICY "embedding_models_select" ON public.embedding_models
    FOR SELECT TO authenticated
    USING (true);

-- ============================================================================
-- 8. HARDENED PROCEDURAL MUTATION RPCS (SECURITY DEFINER)
-- ============================================================================

-- Function: create_memory_rpc
-- Authenticated RPC to create an active or candidate memory
CREATE OR REPLACE FUNCTION public.create_memory_rpc(
    p_content TEXT,
    p_memory_type TEXT,
    p_category TEXT,
    p_importance INT DEFAULT 3,
    p_origin TEXT DEFAULT 'user_direct_input',
    p_confirmation_status TEXT DEFAULT 'confirmed',
    p_expires_at TIMESTAMPTZ DEFAULT NULL,
    p_review_after TIMESTAMPTZ DEFAULT NULL,
    p_source_message_id UUID DEFAULT NULL,
    p_source_conversation_id UUID DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_memory_id UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_content) > 10000 THEN
        RAISE EXCEPTION 'Memory content exceeds maximum permitted length' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.memories (
        user_id,
        content,
        memory_type,
        category,
        importance,
        origin,
        confirmation_status,
        lifecycle_status,
        expires_at,
        review_after,
        source_message_id,
        source_conversation_id,
        metadata
    ) VALUES (
        v_user_id,
        trim(p_content),
        p_memory_type,
        p_category,
        COALESCE(p_importance, 3),
        COALESCE(p_origin, 'user_direct_input'),
        COALESCE(p_confirmation_status, 'confirmed'),
        'active',
        p_expires_at,
        p_review_after,
        p_source_message_id,
        p_source_conversation_id,
        COALESCE(p_metadata, '{}'::jsonb)
    ) RETURNING id INTO v_memory_id;

    -- Root pointer defaults to self
    UPDATE public.memories SET root_memory_id = v_memory_id WHERE id = v_memory_id;

    RETURN v_memory_id;
END;
$$;

-- Function: confirm_memory_rpc
-- Transitions confirmation_status from unconfirmed to confirmed
CREATE OR REPLACE FUNCTION public.confirm_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_rows INT;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    UPDATE public.memories
    SET confirmation_status = 'confirmed',
        last_confirmed_at = now(),
        updated_at = now()
    WHERE id = p_memory_id 
      AND user_id = v_user_id
      AND lifecycle_status = 'active';

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION 'Memory not found or not in confirmable state' USING ERRCODE = 'P0002';
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: reject_memory_rpc
-- Rejects a candidate or unconfirmed memory
CREATE OR REPLACE FUNCTION public.reject_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_rows INT;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    UPDATE public.memories
    SET confirmation_status = 'rejected',
        lifecycle_status = 'rejected',
        updated_at = now()
    WHERE id = p_memory_id 
      AND user_id = v_user_id;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION 'Memory not found' USING ERRCODE = 'P0002';
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: supersede_memory_rpc
-- Atomically supersedes an existing active memory and registers its successor
CREATE OR REPLACE FUNCTION public.supersede_memory_rpc(
    p_old_memory_id UUID,
    p_new_content TEXT,
    p_memory_type TEXT DEFAULT NULL,
    p_category TEXT DEFAULT NULL,
    p_importance INT DEFAULT NULL,
    p_metadata JSONB DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_old public.memories%ROWTYPE;
    v_new_id UUID;
    v_root UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    IF p_new_content IS NULL OR length(trim(p_new_content)) = 0 THEN
        RAISE EXCEPTION 'New memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    -- Fetch and lock old memory
    SELECT * INTO v_old
    FROM public.memories
    WHERE id = p_old_memory_id 
      AND user_id = v_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target memory to supersede not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_old.lifecycle_status != 'active' THEN
        RAISE EXCEPTION 'Cannot supersede memory with lifecycle status: %', v_old.lifecycle_status USING ERRCODE = '22023';
    END IF;

    v_root := COALESCE(v_old.root_memory_id, v_old.id);

    -- Insert successor record
    INSERT INTO public.memories (
        user_id,
        content,
        memory_type,
        category,
        importance,
        origin,
        confirmation_status,
        lifecycle_status,
        previous_version_id,
        root_memory_id,
        metadata
    ) VALUES (
        v_user_id,
        trim(p_new_content),
        COALESCE(p_memory_type, v_old.memory_type),
        COALESCE(p_category, v_old.category),
        COALESCE(p_importance, v_old.importance),
        v_old.origin,
        'confirmed',
        'active',
        v_old.id,
        v_root,
        COALESCE(p_metadata, v_old.metadata)
    ) RETURNING id INTO v_new_id;

    -- Update predecessor to superseded status
    UPDATE public.memories
    SET lifecycle_status = 'superseded',
        superseded_by_id = v_new_id,
        updated_at = now()
    WHERE id = v_old.id;

    RETURN v_new_id;
END;
$$;

-- Function: archive_memory_rpc
-- Archives an active memory
CREATE OR REPLACE FUNCTION public.archive_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_rows INT;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    UPDATE public.memories
    SET lifecycle_status = 'archived',
        updated_at = now()
    WHERE id = p_memory_id 
      AND user_id = v_user_id
      AND lifecycle_status = 'active';

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION 'Memory not found or not in active state' USING ERRCODE = 'P0002';
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: delete_memory_rpc
-- Deletes a memory, cascading to auxiliary embeddings
CREATE OR REPLACE FUNCTION public.delete_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_rows INT;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    DELETE FROM public.memories
    WHERE id = p_memory_id 
      AND user_id = v_user_id;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION 'Memory not found' USING ERRCODE = 'P0002';
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: purge_all_memories_rpc
-- GDPR Right to be Forgotten: cascades to embeddings and jobs
CREATE OR REPLACE FUNCTION public.purge_all_memories_rpc()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_rows INT;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    DELETE FROM public.memories
    WHERE user_id = v_user_id;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    DELETE FROM public.memory_extraction_jobs
    WHERE user_id = v_user_id;

    RETURN v_rows;
END;
$$;

-- Function: consume_journal_consent_rpc
-- Atomically records single-use journal consent, rejecting replayed nonces
CREATE OR REPLACE FUNCTION public.consume_journal_consent_rpc(
    p_nonce UUID,
    p_conversation_id UUID,
    p_idempotency_key TEXT,
    p_scope TEXT,
    p_expires_at TIMESTAMPTZ
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    IF now() > p_expires_at THEN
        RAISE EXCEPTION 'Consent token has expired' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.consumed_consent_tokens (
        nonce,
        user_id,
        conversation_id,
        idempotency_key,
        scope,
        expires_at
    ) VALUES (
        p_nonce,
        v_user_id,
        p_conversation_id,
        p_idempotency_key,
        p_scope,
        p_expires_at
    );

    RETURN TRUE;
EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION 'Consent token has already been consumed (replay rejected)' USING ERRCODE = '23505';
END;
$$;

-- ============================================================================
-- 9. GRANT RPC EXECUTION TO AUTHENTICATED
-- ============================================================================

REVOKE ALL ON FUNCTION public.create_memory_rpc FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.confirm_memory_rpc FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.reject_memory_rpc FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.supersede_memory_rpc FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.archive_memory_rpc FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.delete_memory_rpc FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.purge_all_memories_rpc FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.consume_journal_consent_rpc FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.create_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.reject_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.supersede_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.archive_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.delete_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.purge_all_memories_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.consume_journal_consent_rpc TO authenticated;

-- Migration: 012_memory_database_integrity_and_security_corrections.sql
-- Description: Corrects legacy memory provenance, hardens create_memory_rpc and journal consent,
--              enforces embedding dimension and model registry integrity, establishes auren_worker
--              access model, and strengthens memory lifecycle transitions and concurrency protection.

-- ============================================================================
-- 1. DEFINE WORKER ROLE & PRIVILEGE FOUNDATION
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker') THEN
        CREATE ROLE auren_worker NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO auren_worker, authenticated, anon;

-- ============================================================================
-- 2. TAXONOMY EXTENSION & LEGACY PROVENANCE CORRECTION
-- ============================================================================

-- Allow 'user_direct_edit', 'chat_inferred', 'journal_inferred', 'system_asserted', 'legacy_import' in origin
ALTER TABLE public.memories
    DROP CONSTRAINT IF EXISTS memories_origin_check;

ALTER TABLE public.memories
    ADD CONSTRAINT memories_origin_check
        CHECK (origin IN (
            'explicit_user_statement',
            'inferred_dialogue',
            'user_direct_input',
            'user_direct_edit',
            'chat_inferred',
            'journal_inferred',
            'system_asserted',
            'legacy_import'
        ));

-- Allow 'forgotten' in lifecycle_status
ALTER TABLE public.memories
    DROP CONSTRAINT IF EXISTS memories_lifecycle_status_check;

ALTER TABLE public.memories
    ADD CONSTRAINT memories_lifecycle_status_check
        CHECK (lifecycle_status IN ('active', 'superseded', 'expired', 'archived', 'rejected', 'forgotten'));

-- Unconfirmed memories must have NULL last_confirmed_at; drop NOT NULL on last_confirmed_at
ALTER TABLE public.memories
    ALTER COLUMN last_confirmed_at DROP NOT NULL,
    ALTER COLUMN last_confirmed_at DROP DEFAULT;

-- Ensure confirmed memories have last_confirmed_at populated
ALTER TABLE public.memories
    DROP CONSTRAINT IF EXISTS memories_confirmed_requires_timestamp_check;

ALTER TABLE public.memories
    ADD CONSTRAINT memories_confirmed_requires_timestamp_check
        CHECK (confirmation_status != 'confirmed' OR last_confirmed_at IS NOT NULL);

-- Default new memories to 'user_direct_input', 'unconfirmed', and 0.7 confidence
ALTER TABLE public.memories
    ALTER COLUMN origin SET DEFAULT 'user_direct_input',
    ALTER COLUMN confirmation_status SET DEFAULT 'unconfirmed',
    ALTER COLUMN confidence SET DEFAULT 0.7;

-- Correct legacy memory records:
-- Legacy records from migration 001 that had synthetic 'explicit_user_statement' or 'system_import'
-- are corrected to 'legacy_import', 'unconfirmed', confidence 0.5, and last_confirmed_at NULL.
UPDATE public.memories
SET 
    origin = 'legacy_import',
    confirmation_status = 'unconfirmed',
    confidence = 0.5,
    last_confirmed_at = NULL
WHERE origin IN ('explicit_user_statement', 'system_import');

-- ============================================================================
-- 3. EMBEDDING REGISTRY PURPOSE & ACTIVATION INTEGRITY
-- ============================================================================

ALTER TABLE public.embedding_models
    ADD COLUMN IF NOT EXISTS purpose TEXT NOT NULL DEFAULT 'retrieval';

ALTER TABLE public.embedding_models
    DROP CONSTRAINT IF EXISTS embedding_models_purpose_check;

ALTER TABLE public.embedding_models
    ADD CONSTRAINT embedding_models_purpose_check
        CHECK (purpose IN ('retrieval', 'classification', 'clustering'));

-- Enforce exactly one active model per embedding purpose
CREATE UNIQUE INDEX IF NOT EXISTS idx_embedding_models_single_active_per_purpose
    ON public.embedding_models(purpose)
    WHERE is_active = TRUE;

-- Safe seed: DO NOTHING on conflict so user-selected active model is never reset
INSERT INTO public.embedding_models (provider, model, version, dimension, vector_column, purpose, is_active)
VALUES 
    ('gemini', 'text-embedding-004', 'v1', 768, 'embedding_768', 'retrieval', TRUE),
    ('openai', 'text-embedding-3-small', 'v1', 1536, 'embedding_1536', 'retrieval', FALSE)
ON CONFLICT (provider, model, version) DO NOTHING;

-- Atomic model activation RPC
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
    SELECT purpose, dimension INTO v_purpose, v_dim
    FROM public.embedding_models
    WHERE provider = p_provider AND model = p_model AND version = p_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Embedding model %/%/% not registered', p_provider, p_model, p_version USING ERRCODE = 'P0002';
    END IF;

    -- Deactivate current active model for this purpose
    UPDATE public.embedding_models
    SET is_active = FALSE
    WHERE purpose = v_purpose AND is_active = TRUE;

    -- Activate target model
    UPDATE public.embedding_models
    SET is_active = TRUE
    WHERE provider = p_provider AND model = p_model AND version = p_version;

    RETURN TRUE;
END;
$$;

-- ============================================================================
-- 4. EMBEDDING VECTOR DIMENSION & MODEL CONSISTENCY
-- ============================================================================

ALTER TABLE public.memory_embeddings
    DROP CONSTRAINT IF EXISTS memory_embeddings_vector_dimension_check;

ALTER TABLE public.memory_embeddings
    ADD CONSTRAINT memory_embeddings_vector_dimension_check
        CHECK (
            (dimension = 768 AND embedding_768 IS NOT NULL AND embedding_1536 IS NULL) OR
            (dimension = 1536 AND embedding_1536 IS NOT NULL AND embedding_768 IS NULL)
        );

-- Trigger to validate model existence, registered dimension, and user_id ownership
CREATE OR REPLACE FUNCTION public.fn_validate_memory_embedding()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_model_dim INT;
    v_mem_user_id UUID;
BEGIN
    SELECT dimension INTO v_model_dim
    FROM public.embedding_models
    WHERE provider = NEW.provider AND model = NEW.model AND version = NEW.version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Embedding model %/%/% is not registered in embedding_models', NEW.provider, NEW.model, NEW.version USING ERRCODE = '22023';
    END IF;

    IF v_model_dim != NEW.dimension THEN
        RAISE EXCEPTION 'Embedding dimension % does not match registered model dimension % for %/%/%', NEW.dimension, v_model_dim, NEW.provider, NEW.model, NEW.version USING ERRCODE = '22023';
    END IF;

    SELECT user_id INTO v_mem_user_id
    FROM public.memories
    WHERE id = NEW.memory_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Memory % not found', NEW.memory_id USING ERRCODE = 'P0002';
    END IF;

    IF NEW.user_id != v_mem_user_id THEN
        RAISE EXCEPTION 'Embedding user_id % does not match memory owner %', NEW.user_id, v_mem_user_id USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validate_memory_embedding ON public.memory_embeddings;
CREATE TRIGGER trg_validate_memory_embedding
    BEFORE INSERT OR UPDATE ON public.memory_embeddings
    FOR EACH ROW EXECUTE FUNCTION public.fn_validate_memory_embedding();

-- ============================================================================
-- 5. DATABASE-LEVEL LIFECYCLE IMMUTABILITY GUARD
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

    -- Superseded memories are terminal
    IF OLD.lifecycle_status = 'superseded' AND NEW.lifecycle_status != 'superseded' THEN
        RAISE EXCEPTION 'Illegal lifecycle transition: superseded memories cannot be reactivated' USING ERRCODE = '22023';
    END IF;

    -- Forgotten memories are terminal
    IF OLD.lifecycle_status = 'forgotten' AND NEW.lifecycle_status != 'forgotten' THEN
        RAISE EXCEPTION 'Illegal lifecycle transition: forgotten memories are terminal' USING ERRCODE = '22023';
    END IF;

    -- Rejected memories cannot be confirmed or revived
    IF OLD.confirmation_status = 'rejected' AND NEW.confirmation_status = 'confirmed' THEN
        RAISE EXCEPTION 'Illegal transition: rejected memories cannot be confirmed' USING ERRCODE = '22023';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_memories_lifecycle_guard ON public.memories;
CREATE TRIGGER trg_memories_lifecycle_guard
    BEFORE UPDATE ON public.memories
    FOR EACH ROW EXECUTE FUNCTION public.fn_memories_lifecycle_guard();

-- ============================================================================
-- 6. HARDENED CLIENT & WORKER RPC FUNCTIONS
-- ============================================================================

-- Function: create_memory_rpc (Public Authenticated Client RPC)
DROP FUNCTION IF EXISTS public.create_memory_rpc(TEXT, TEXT, TEXT, INT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, UUID, UUID, JSONB);
CREATE OR REPLACE FUNCTION public.create_memory_rpc(
    p_content TEXT,
    p_memory_type TEXT,
    p_category TEXT,
    p_importance INT DEFAULT 3,
    p_origin TEXT DEFAULT 'user_direct_input',
    p_confirmation_status TEXT DEFAULT 'confirmed',
    p_confidence REAL DEFAULT NULL,
    p_expires_at TIMESTAMPTZ DEFAULT NULL,
    p_review_after TIMESTAMPTZ DEFAULT NULL,
    p_source_message_id UUID DEFAULT NULL,
    p_source_conversation_id UUID DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_memory_id UUID;
    v_msg_user_id UUID;
    v_msg_conv_id UUID;
    v_confidence REAL;
    v_last_confirmed TIMESTAMPTZ;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    -- Prevent ordinary authenticated users from assigning system_asserted or legacy_import
    IF p_origin = 'system_asserted' OR p_confirmation_status = 'system_asserted' THEN
        RAISE EXCEPTION 'Forbidden: system_asserted status is reserved for trusted platform operations' USING ERRCODE = '42501';
    END IF;

    IF p_origin = 'legacy_import' THEN
        RAISE EXCEPTION 'Forbidden: legacy_import origin cannot be assigned via client RPC' USING ERRCODE = '42501';
    END IF;

    -- Validate origin
    IF p_origin NOT IN ('user_direct_input', 'user_direct_edit', 'chat_inferred', 'journal_inferred') THEN
        RAISE EXCEPTION 'Invalid origin: %', p_origin USING ERRCODE = '22023';
    END IF;

    -- Validate confirmation_status
    IF p_confirmation_status NOT IN ('confirmed', 'unconfirmed') THEN
        RAISE EXCEPTION 'Invalid confirmation_status: %', p_confirmation_status USING ERRCODE = '22023';
    END IF;

    -- Inferred memories MUST NOT be created as confirmed
    IF p_origin IN ('chat_inferred', 'journal_inferred') AND p_confirmation_status = 'confirmed' THEN
        RAISE EXCEPTION 'Contradictory provenance: inferred memories must be unconfirmed upon creation' USING ERRCODE = '22023';
    END IF;

    -- Content validation
    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_content) > 10000 THEN
        RAISE EXCEPTION 'Memory content exceeds maximum permitted length' USING ERRCODE = '22023';
    END IF;

    -- Type and category validation
    IF p_memory_type NOT IN ('fact', 'preference', 'goal', 'project', 'context', 'observation') THEN
        RAISE EXCEPTION 'Invalid memory_type: %', p_memory_type USING ERRCODE = '22023';
    END IF;

    IF p_category NOT IN ('personal', 'work', 'technical', 'health_lifestyle', 'financial', 'general') THEN
        RAISE EXCEPTION 'Invalid category: %', p_category USING ERRCODE = '22023';
    END IF;

    IF p_importance IS NOT NULL AND (p_importance < 1 OR p_importance > 5) THEN
        RAISE EXCEPTION 'Importance must be between 1 and 5' USING ERRCODE = '22023';
    END IF;

    -- Expiration validation
    IF p_expires_at IS NOT NULL AND p_expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'expires_at must be in the future' USING ERRCODE = '22023';
    END IF;

    IF p_review_after IS NOT NULL AND p_review_after <= clock_timestamp() THEN
        RAISE EXCEPTION 'review_after must be in the future' USING ERRCODE = '22023';
    END IF;

    IF p_expires_at IS NOT NULL AND p_review_after IS NOT NULL AND p_review_after >= p_expires_at THEN
        RAISE EXCEPTION 'review_after must be earlier than expires_at' USING ERRCODE = '22023';
    END IF;

    -- Confidence assignment
    IF p_confidence IS NOT NULL THEN
        IF p_confidence < 0.0 OR p_confidence > 1.0 THEN
            RAISE EXCEPTION 'Confidence must be between 0.0 and 1.0' USING ERRCODE = '22023';
        END IF;
        v_confidence := p_confidence;
    ELSE
        IF p_confirmation_status = 'confirmed' THEN
            v_confidence := 1.0;
        ELSE
            v_confidence := 0.7;
        END IF;
    END IF;

    -- Conversation ownership validation
    IF p_source_conversation_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.conversations
            WHERE id = p_source_conversation_id AND user_id = v_user_id
        ) THEN
            RAISE EXCEPTION 'Conversation not found or access denied: %', p_source_conversation_id USING ERRCODE = '42501';
        END IF;
    END IF;

    -- Message ownership and conversation consistency validation
    IF p_source_message_id IS NOT NULL THEN
        SELECT c.user_id, m.conversation_id
        INTO v_msg_user_id, v_msg_conv_id
        FROM public.messages m
        JOIN public.conversations c ON c.id = m.conversation_id
        WHERE m.id = p_source_message_id;

        IF NOT FOUND OR v_msg_user_id != v_user_id THEN
            RAISE EXCEPTION 'Source message not found or access denied: %', p_source_message_id USING ERRCODE = '42501';
        END IF;

        IF p_source_conversation_id IS NOT NULL AND v_msg_conv_id != p_source_conversation_id THEN
            RAISE EXCEPTION 'Source message % does not belong to conversation %', p_source_message_id, p_source_conversation_id USING ERRCODE = '22023';
        END IF;

        IF p_source_conversation_id IS NULL THEN
            p_source_conversation_id := v_msg_conv_id;
        END IF;
    END IF;

    IF p_confirmation_status = 'confirmed' THEN
        v_last_confirmed := clock_timestamp();
    ELSE
        v_last_confirmed := NULL;
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
        expires_at,
        review_after,
        last_confirmed_at,
        source_message_id,
        source_conversation_id,
        metadata
    ) VALUES (
        v_user_id,
        trim(p_content),
        p_memory_type,
        p_category,
        COALESCE(p_importance, 3),
        p_origin,
        v_confidence,
        p_confirmation_status,
        'active',
        p_expires_at,
        p_review_after,
        v_last_confirmed,
        p_source_message_id,
        p_source_conversation_id,
        COALESCE(p_metadata, '{}'::jsonb)
    ) RETURNING id INTO v_memory_id;

    UPDATE public.memories SET root_memory_id = v_memory_id WHERE id = v_memory_id;

    RETURN v_memory_id;
END;
$$;

-- Function: create_system_asserted_memory_rpc (Platform-Controlled Trusted RPC)
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
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_user_id) THEN
        RAISE EXCEPTION 'Target user % does not exist', p_user_id USING ERRCODE = 'P0002';
    END IF;

    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
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

-- Function: confirm_memory_rpc
CREATE OR REPLACE FUNCTION public.confirm_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_mem public.memories%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_mem
    FROM public.memories
    WHERE id = p_memory_id AND user_id = v_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Memory not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_mem.confirmation_status = 'rejected' THEN
        RAISE EXCEPTION 'Cannot confirm previously rejected memory' USING ERRCODE = '22023';
    END IF;

    IF v_mem.lifecycle_status != 'active' THEN
        RAISE EXCEPTION 'Cannot confirm memory with lifecycle status: %', v_mem.lifecycle_status USING ERRCODE = '22023';
    END IF;

    IF v_mem.confirmation_status = 'confirmed' THEN
        RETURN TRUE;
    END IF;

    UPDATE public.memories
    SET confirmation_status = 'confirmed',
        confidence = 1.0,
        last_confirmed_at = clock_timestamp(),
        updated_at = clock_timestamp()
    WHERE id = p_memory_id;

    RETURN TRUE;
END;
$$;

-- Function: reject_memory_rpc
CREATE OR REPLACE FUNCTION public.reject_memory_rpc(p_memory_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_mem public.memories%ROWTYPE;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_mem
    FROM public.memories
    WHERE id = p_memory_id AND user_id = v_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Memory not found or access denied' USING ERRCODE = 'P0002';
    END IF;

    IF v_mem.lifecycle_status = 'superseded' THEN
        RAISE EXCEPTION 'Cannot reject superseded memory' USING ERRCODE = '22023';
    END IF;

    UPDATE public.memories
    SET confirmation_status = 'rejected',
        lifecycle_status = 'archived',
        updated_at = clock_timestamp()
    WHERE id = p_memory_id;

    RETURN TRUE;
END;
$$;

-- Function: supersede_memory_rpc
DROP FUNCTION IF EXISTS public.supersede_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB);
CREATE OR REPLACE FUNCTION public.supersede_memory_rpc(
    p_old_memory_id UUID,
    p_new_content TEXT,
    p_memory_type TEXT DEFAULT NULL,
    p_category TEXT DEFAULT NULL,
    p_importance INT DEFAULT NULL,
    p_origin TEXT DEFAULT NULL,
    p_confirmation_status TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_old public.memories%ROWTYPE;
    v_new_id UUID;
    v_root UUID;
    v_target_origin TEXT;
    v_target_confirmation TEXT;
    v_target_last_confirmed TIMESTAMPTZ;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    IF p_new_content IS NULL OR length(trim(p_new_content)) = 0 THEN
        RAISE EXCEPTION 'New memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_new_content) > 10000 THEN
        RAISE EXCEPTION 'New memory content exceeds maximum length' USING ERRCODE = '22023';
    END IF;

    -- Concurrency-safe exclusive lock on target memory
    SELECT * INTO v_old
    FROM public.memories
    WHERE id = p_old_memory_id 
      AND user_id = v_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target memory to supersede not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_old.lifecycle_status != 'active' THEN
        RAISE EXCEPTION 'Cannot supersede memory with lifecycle status: %', v_old.lifecycle_status USING ERRCODE = '22023';
    END IF;

    IF v_old.confirmation_status = 'rejected' THEN
        RAISE EXCEPTION 'Cannot supersede rejected memory' USING ERRCODE = '22023';
    END IF;

    -- Determine confirmation status without automatically manufacturing confirmation
    IF p_confirmation_status IS NOT NULL THEN
        IF p_confirmation_status NOT IN ('confirmed', 'unconfirmed') THEN
            RAISE EXCEPTION 'Invalid confirmation_status: %', p_confirmation_status USING ERRCODE = '22023';
        END IF;
        v_target_confirmation := p_confirmation_status;
    ELSE
        -- Preserve predecessor confirmation status
        v_target_confirmation := v_old.confirmation_status;
    END IF;

    IF p_origin IS NOT NULL THEN
        IF p_origin NOT IN ('user_direct_input', 'user_direct_edit', 'chat_inferred', 'journal_inferred') THEN
            RAISE EXCEPTION 'Invalid origin: %', p_origin USING ERRCODE = '22023';
        END IF;
        v_target_origin := p_origin;
    ELSE
        v_target_origin := 'user_direct_edit';
    END IF;

    IF v_target_origin IN ('chat_inferred', 'journal_inferred') AND v_target_confirmation = 'confirmed' THEN
        RAISE EXCEPTION 'Contradictory provenance: inferred memories must be unconfirmed upon creation' USING ERRCODE = '22023';
    END IF;

    IF v_target_confirmation = 'confirmed' THEN
        v_target_last_confirmed := clock_timestamp();
    ELSE
        v_target_last_confirmed := NULL;
    END IF;

    v_root := COALESCE(v_old.root_memory_id, v_old.id);

    -- Insert successor record preserving lineage and source references
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
        previous_version_id,
        root_memory_id,
        source_conversation_id,
        source_message_id,
        last_confirmed_at,
        metadata
    ) VALUES (
        v_user_id,
        trim(p_new_content),
        COALESCE(p_memory_type, v_old.memory_type),
        COALESCE(p_category, v_old.category),
        COALESCE(p_importance, v_old.importance),
        v_target_origin,
        v_old.confidence,
        v_target_confirmation,
        'active',
        v_old.id,
        v_root,
        v_old.source_conversation_id,
        v_old.source_message_id,
        v_target_last_confirmed,
        COALESCE(p_metadata, v_old.metadata)
    ) RETURNING id INTO v_new_id;

    -- Update predecessor to superseded status
    UPDATE public.memories
    SET lifecycle_status = 'superseded',
        superseded_by_id = v_new_id,
        updated_at = clock_timestamp()
    WHERE id = v_old.id;

    RETURN v_new_id;
END;
$$;

-- Function: consume_journal_consent_rpc (Hardened Single-Use Consent RPC)
CREATE OR REPLACE FUNCTION public.consume_journal_consent_rpc(
    p_nonce UUID,
    p_conversation_id UUID,
    p_idempotency_key TEXT,
    p_scope TEXT,
    p_expires_at TIMESTAMPTZ
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_conv_owner UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    -- Validate non-empty request identity fields
    IF p_nonce IS NULL THEN
        RAISE EXCEPTION 'Consent nonce cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_conversation_id IS NULL THEN
        RAISE EXCEPTION 'Consent conversation_id cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_idempotency_key IS NULL OR length(trim(p_idempotency_key)) = 0 THEN
        RAISE EXCEPTION 'Consent idempotency_key cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_scope IS NULL OR length(trim(p_scope)) = 0 THEN
        RAISE EXCEPTION 'Consent scope cannot be empty' USING ERRCODE = '22023';
    END IF;

    -- Validate permitted consent scopes
    IF trim(p_scope) NOT IN ('journal.read', 'journal.read_write', 'journal.summarize') THEN
        RAISE EXCEPTION 'Invalid consent scope: %', p_scope USING ERRCODE = '22023';
    END IF;

    -- Validate token expiration and maximum lifetime window (15 minutes)
    IF p_expires_at IS NULL THEN
        RAISE EXCEPTION 'Consent expires_at cannot be null' USING ERRCODE = '22023';
    END IF;

    IF clock_timestamp() > p_expires_at THEN
        RAISE EXCEPTION 'Consent token has expired' USING ERRCODE = '22023';
    END IF;

    IF p_expires_at > (clock_timestamp() + INTERVAL '15 minutes') THEN
        RAISE EXCEPTION 'Consent token lifetime exceeds maximum permitted window of 15 minutes' USING ERRCODE = '22023';
    END IF;

    -- Verify authenticated user owns the supplied conversation
    SELECT user_id INTO v_conv_owner
    FROM public.conversations
    WHERE id = p_conversation_id;

    IF NOT FOUND OR v_conv_owner != v_user_id THEN
        RAISE EXCEPTION 'Conversation not found or access denied: %', p_conversation_id USING ERRCODE = '42501';
    END IF;

    -- Atomic single-use nonce consumption
    INSERT INTO public.consumed_consent_tokens (
        nonce,
        user_id,
        conversation_id,
        idempotency_key,
        scope,
        expires_at
    ) VALUES (
        p_nonce,
        v_user_id,
        p_conversation_id,
        trim(p_idempotency_key),
        trim(p_scope),
        p_expires_at
    );

    RETURN TRUE;
EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION 'Consent token has already been consumed (replay rejected)' USING ERRCODE = '23505';
END;
$$;

-- Function: enqueue_memory_extraction_job_rpc (Client Enqueue RPC)
CREATE OR REPLACE FUNCTION public.enqueue_memory_extraction_job_rpc(
    p_conversation_id UUID,
    p_source_message_id UUID
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_msg_user_id UUID;
    v_msg_conv_id UUID;
    v_job_id UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    -- Verify message exists, caller owns it, and it belongs to p_conversation_id
    SELECT c.user_id, m.conversation_id
    INTO v_msg_user_id, v_msg_conv_id
    FROM public.messages m
    JOIN public.conversations c ON c.id = m.conversation_id
    WHERE m.id = p_source_message_id;

    IF NOT FOUND OR v_msg_user_id != v_user_id THEN
        RAISE EXCEPTION 'Message not found or access denied: %', p_source_message_id USING ERRCODE = '42501';
    END IF;

    IF v_msg_conv_id != p_conversation_id THEN
        RAISE EXCEPTION 'Message % does not belong to conversation %', p_source_message_id, p_conversation_id USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.memory_extraction_jobs (
        user_id,
        conversation_id,
        source_message_id,
        status,
        scheduled_at
    ) VALUES (
        v_user_id,
        p_conversation_id,
        p_source_message_id,
        'pending',
        clock_timestamp()
    )
    ON CONFLICT (user_id, source_message_id) DO UPDATE
    SET updated_at = clock_timestamp()
    RETURNING id INTO v_job_id;

    RETURN v_job_id;
END;
$$;

-- Function: claim_memory_extraction_jobs_rpc (Worker Atomic Claim RPC)
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
    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    WITH claimed AS (
        SELECT j.id AS claimed_id
        FROM public.memory_extraction_jobs j
        WHERE (j.status = 'pending' AND j.scheduled_at <= clock_timestamp())
           OR (j.status = 'processing' AND j.lease_expires_at < clock_timestamp() AND j.attempts < j.max_attempts)
        ORDER BY j.scheduled_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT p_batch_size
    )
    UPDATE public.memory_extraction_jobs j
    SET status = 'processing',
        locked_by = p_worker_id,
        locked_at = clock_timestamp(),
        lease_expires_at = clock_timestamp() + (p_lease_seconds || ' seconds')::INTERVAL,
        attempts = j.attempts + 1,
        updated_at = clock_timestamp()
    FROM claimed
    WHERE j.id = claimed.claimed_id
    RETURNING j.id, j.user_id, j.conversation_id, j.source_message_id, j.attempts, j.max_attempts;
END;
$$;

-- Function: complete_memory_extraction_job_rpc (Worker Complete RPC)
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
    v_rows INT;
BEGIN
    UPDATE public.memory_extraction_jobs
    SET status = 'completed',
        locked_by = NULL,
        lease_expires_at = NULL,
        updated_at = clock_timestamp()
    WHERE id = p_job_id AND locked_by = p_worker_id AND status = 'processing';

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION 'Job % not found or not locked by worker %', p_job_id, p_worker_id USING ERRCODE = 'P0002';
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: fail_memory_extraction_job_rpc (Worker Fail / Dead-Letter RPC)
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
    v_attempts INT;
    v_max INT;
BEGIN
    SELECT attempts, max_attempts INTO v_attempts, v_max
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id AND locked_by = p_worker_id AND status = 'processing';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found or not locked by worker %', p_job_id, p_worker_id USING ERRCODE = 'P0002';
    END IF;

    IF p_retry AND v_attempts < v_max THEN
        -- Requeue with exponential backoff
        UPDATE public.memory_extraction_jobs
        SET status = 'pending',
            locked_by = NULL,
            locked_at = NULL,
            lease_expires_at = NULL,
            last_error = p_error,
            scheduled_at = clock_timestamp() + (POWER(2, v_attempts) * 5 || ' seconds')::INTERVAL,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    ELSE
        -- Dead-letter
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

-- Function: reap_stale_extraction_jobs_rpc (Worker Stale Lease Reclaimer)
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
    -- Move exhausted leases to dead_letter
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

-- Function: insert_extracted_memory_rpc (Worker Inferred Memory Ingestion with Deduplication)
CREATE OR REPLACE FUNCTION public.insert_extracted_memory_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_content TEXT,
    p_memory_type TEXT,
    p_category TEXT,
    p_importance INT DEFAULT 3,
    p_confidence REAL DEFAULT 0.7,
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
    SELECT * INTO v_job
    FROM public.memory_extraction_jobs
    WHERE id = p_job_id AND locked_by = p_worker_id AND status = 'processing';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % is not active or not locked by worker %', p_job_id, p_worker_id USING ERRCODE = 'P0002';
    END IF;

    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    -- Deduplication: check if identical memory already exists from this source message
    SELECT id INTO v_existing_id
    FROM public.memories
    WHERE user_id = v_job.user_id
      AND source_message_id = v_job.source_message_id
      AND content = trim(p_content)
      AND lifecycle_status = 'active';

    IF FOUND THEN
        RETURN v_existing_id;
    END IF;

    -- Insert candidate inferred memory (strictly unconfirmed)
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
        COALESCE(p_confidence, 0.7),
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

-- ============================================================================
-- 7. REINFORCE ACCESS CONTROL AND RPC PERMISSIONS
-- ============================================================================

-- Revoke direct table mutations
REVOKE ALL ON public.memories FROM anon, authenticated, public;
REVOKE ALL ON public.memory_embeddings FROM anon, authenticated, public;
REVOKE ALL ON public.consumed_consent_tokens FROM anon, authenticated, public;
REVOKE ALL ON public.memory_extraction_jobs FROM anon, authenticated, public;
REVOKE ALL ON public.embedding_models FROM anon, authenticated, public;

-- Grant selective read-only access to authenticated clients
GRANT SELECT ON public.memories TO authenticated;
GRANT SELECT ON public.embedding_models TO authenticated;

-- Grant selective read-only access to auren_worker
GRANT SELECT ON public.memories TO auren_worker;
GRANT SELECT ON public.memory_embeddings TO auren_worker;
GRANT SELECT ON public.memory_extraction_jobs TO auren_worker;
GRANT SELECT ON public.embedding_models TO auren_worker;

-- RLS policies for worker read access
DROP POLICY IF EXISTS "memories_worker_select" ON public.memories;
CREATE POLICY "memories_worker_select" ON public.memories
    FOR SELECT TO auren_worker
    USING (true);

DROP POLICY IF EXISTS "memory_embeddings_worker_select" ON public.memory_embeddings;
CREATE POLICY "memory_embeddings_worker_select" ON public.memory_embeddings
    FOR SELECT TO auren_worker
    USING (true);

DROP POLICY IF EXISTS "extraction_jobs_worker_select" ON public.memory_extraction_jobs;
CREATE POLICY "extraction_jobs_worker_select" ON public.memory_extraction_jobs
    FOR SELECT TO auren_worker
    USING (true);

-- Revoke all function executions by default
REVOKE ALL ON FUNCTION public.create_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.create_system_asserted_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.confirm_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.reject_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.supersede_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.archive_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.delete_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.purge_all_memories_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.consume_journal_consent_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.enqueue_memory_extraction_job_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.activate_embedding_model_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.claim_memory_extraction_jobs_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.complete_memory_extraction_job_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.fail_memory_extraction_job_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.reap_stale_extraction_jobs_rpc FROM PUBLIC, anon, authenticated, auren_worker;
REVOKE ALL ON FUNCTION public.insert_extracted_memory_rpc FROM PUBLIC, anon, authenticated, auren_worker;

-- Grant user RPCs to authenticated role
GRANT EXECUTE ON FUNCTION public.create_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.reject_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.supersede_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.archive_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.delete_memory_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.purge_all_memories_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.consume_journal_consent_rpc TO authenticated;
GRANT EXECUTE ON FUNCTION public.enqueue_memory_extraction_job_rpc TO authenticated;

-- Grant worker / platform RPCs to auren_worker role
GRANT EXECUTE ON FUNCTION public.claim_memory_extraction_jobs_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.complete_memory_extraction_job_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.fail_memory_extraction_job_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.reap_stale_extraction_jobs_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.create_system_asserted_memory_rpc TO auren_worker;
GRANT EXECUTE ON FUNCTION public.activate_embedding_model_rpc TO auren_worker;
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
-- Migration: 014_consent_hmac_and_worker_lease_hardening.sql
-- Description: Binds actual requested date_range in consumed_consent_tokens and RPC,
--              establishes lease-generation token protection against same-worker and cross-worker
--              stale claim execution, and hardens worker SECURITY DEFINER caller authentication using SESSION_USER.

-- ============================================================================
-- 1. BIND DATE_RANGE IN CONSUMED CONSENT TOKENS
-- ============================================================================

ALTER TABLE public.consumed_consent_tokens
    ADD COLUMN IF NOT EXISTS date_range TEXT NOT NULL DEFAULT 'unspecified';

-- Drop previous 5-argument version of consume_journal_consent_rpc
DROP FUNCTION IF EXISTS public.consume_journal_consent_rpc(UUID, UUID, TEXT, TEXT, TIMESTAMPTZ);

-- Recreate consume_journal_consent_rpc with p_date_range binding
CREATE OR REPLACE FUNCTION public.consume_journal_consent_rpc(
    p_nonce UUID,
    p_conversation_id UUID,
    p_idempotency_key TEXT,
    p_scope TEXT,
    p_date_range TEXT,
    p_expires_at TIMESTAMPTZ
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_conv_owner UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Unauthorized: authenticated session required' USING ERRCODE = '42501';
    END IF;

    -- Validate non-empty request identity fields
    IF p_nonce IS NULL THEN
        RAISE EXCEPTION 'Consent nonce cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_conversation_id IS NULL THEN
        RAISE EXCEPTION 'Consent conversation_id cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_idempotency_key IS NULL OR length(trim(p_idempotency_key)) = 0 THEN
        RAISE EXCEPTION 'Consent idempotency_key cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_scope IS NULL OR length(trim(p_scope)) = 0 THEN
        RAISE EXCEPTION 'Consent scope cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF p_date_range IS NULL OR length(trim(p_date_range)) = 0 THEN
        RAISE EXCEPTION 'Consent date_range cannot be empty' USING ERRCODE = '22023';
    END IF;

    -- Validate permitted consent scopes
    IF trim(p_scope) NOT IN ('journal.read', 'journal.read_write', 'journal.summarize') THEN
        RAISE EXCEPTION 'Invalid consent scope: %', p_scope USING ERRCODE = '22023';
    END IF;

    -- Validate token expiration and maximum lifetime window (15 minutes)
    IF p_expires_at IS NULL THEN
        RAISE EXCEPTION 'Consent expires_at cannot be null' USING ERRCODE = '22023';
    END IF;

    IF clock_timestamp() > p_expires_at THEN
        RAISE EXCEPTION 'Consent token has expired' USING ERRCODE = '22023';
    END IF;

    IF p_expires_at > (clock_timestamp() + INTERVAL '15 minutes') THEN
        RAISE EXCEPTION 'Consent token lifetime exceeds maximum permitted window of 15 minutes' USING ERRCODE = '22023';
    END IF;

    -- Verify authenticated user owns the supplied conversation
    SELECT user_id INTO v_conv_owner
    FROM public.conversations
    WHERE id = p_conversation_id;

    IF NOT FOUND OR v_conv_owner != v_user_id THEN
        RAISE EXCEPTION 'Conversation not found or access denied: %', p_conversation_id USING ERRCODE = '42501';
    END IF;

    -- Atomic single-use nonce consumption storing exact requested date range
    INSERT INTO public.consumed_consent_tokens (
        nonce,
        user_id,
        conversation_id,
        idempotency_key,
        scope,
        date_range,
        expires_at
    ) VALUES (
        p_nonce,
        v_user_id,
        p_conversation_id,
        trim(p_idempotency_key),
        trim(p_scope),
        trim(p_date_range),
        p_expires_at
    );

    RETURN TRUE;
EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION 'Consent token has already been consumed (replay rejected)' USING ERRCODE = '23505';
END;
$$;

-- ============================================================================
-- 2. LEASE-GENERATION PROTECTION ON EXTRACTION JOBS
-- ============================================================================

ALTER TABLE public.memory_extraction_jobs
    ADD COLUMN IF NOT EXISTS claim_token UUID DEFAULT gen_random_uuid() NOT NULL;

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_claim_token
    ON public.memory_extraction_jobs(id, claim_token);

-- ============================================================================
-- 3. HARDENED WORKER RPC FUNCTIONS WITH LEASE-GENERATION TOKENS
-- ============================================================================

-- Function: claim_memory_extraction_jobs_rpc
DROP FUNCTION IF EXISTS public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT);

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
    claim_token UUID,
    attempts INT,
    max_attempts INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    -- Verify caller session identity using SESSION_USER (not CURRENT_USER)
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_worker_id) > 255 THEN
        RAISE EXCEPTION 'Worker ID exceeds maximum length of 255 characters' USING ERRCODE = '22023';
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
        claim_token = gen_random_uuid(),  -- Fresh lease-generation token
        attempts = j.attempts + 1,
        updated_at = clock_timestamp()
    FROM candidate
    WHERE j.id = candidate.candidate_id
    RETURNING j.id, j.user_id, j.conversation_id, j.source_message_id, j.claim_token, j.attempts, j.max_attempts;
END;
$$;

-- Function: complete_memory_extraction_job_rpc
DROP FUNCTION IF EXISTS public.complete_memory_extraction_job_rpc(UUID, TEXT);
DROP FUNCTION IF EXISTS public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID);

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
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
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

    -- Lease-generation token check: prevents stale worker executions
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has been reclaimed or lease regenerated', p_job_id USING ERRCODE = '22023';
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
DROP FUNCTION IF EXISTS public.fail_memory_extraction_job_rpc(UUID, TEXT, TEXT, BOOLEAN);
DROP FUNCTION IF EXISTS public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN);

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
    v_sanitized_error TEXT;
BEGIN
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
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

    -- Lease-generation token check
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has been reclaimed or lease regenerated', p_job_id USING ERRCODE = '22023';
    END IF;

    -- Reject failure update if lease has expired
    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; failure update rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    -- Sanitize and bound error message length (max 1000 characters)
    v_sanitized_error := substr(trim(COALESCE(p_error, 'Extraction failed without specific error details')), 1, 1000);

    IF p_retry AND v_job.attempts < v_job.max_attempts THEN
        UPDATE public.memory_extraction_jobs
        SET status = 'pending',
            locked_by = NULL,
            locked_at = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),  -- Invalidate claim on requeue
            last_error = v_sanitized_error,
            scheduled_at = clock_timestamp() + (POWER(2, v_job.attempts) * 5 || ' seconds')::INTERVAL,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    ELSE
        -- Terminal dead-letter state
        UPDATE public.memory_extraction_jobs
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),  -- Invalidate claim
            last_error = v_sanitized_error,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: insert_extracted_memory_rpc
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, TEXT, TEXT, TEXT, INT, REAL, JSONB);
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB);

CREATE OR REPLACE FUNCTION public.insert_extracted_memory_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_claim_token UUID,
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
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
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

    -- Lease-generation token check
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has been reclaimed or lease regenerated; ingestion rejected', p_job_id USING ERRCODE = '22023';
    END IF;

    -- Reject ingestion if lease has expired
    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; ingestion rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
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

    IF p_importance IS NOT NULL AND (p_importance < 1 OR p_importance > 5) THEN
        RAISE EXCEPTION 'Importance must be between 1 and 5' USING ERRCODE = '22023';
    END IF;

    -- Deduplication check: return existing ID if identical memory already stored
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
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    -- Move exhausted leases to dead_letter (strictly terminal, new claim_token)
    UPDATE public.memory_extraction_jobs
    SET status = 'dead_letter',
        locked_by = NULL,
        lease_expires_at = NULL,
        claim_token = gen_random_uuid(),
        last_error = 'Lease expired and max attempts exceeded',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts >= p_max_retries;

    GET DIAGNOSTICS v_dead_lettered = ROW_COUNT;

    -- Return recoverable expired leases to pending (generates new claim_token)
    UPDATE public.memory_extraction_jobs
    SET status = 'pending',
        locked_by = NULL,
        locked_at = NULL,
        lease_expires_at = NULL,
        claim_token = gen_random_uuid(),
        last_error = 'Lease expired; automatically recovered for retry',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts < p_max_retries;

    GET DIAGNOSTICS v_reaped = ROW_COUNT;

    RETURN v_reaped + v_dead_lettered;
END;
$$;

-- Function: create_system_asserted_memory_rpc (Hardened SESSION_USER identity check)
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
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
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

    -- Strict taxonomy validation
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

-- Function: activate_embedding_model_rpc (Hardened SESSION_USER identity check)
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
    -- Verify caller session identity
    IF NOT (
        pg_has_role(SESSION_USER, 'auren_worker', 'MEMBER')
        OR SESSION_USER = 'auren_worker'
        OR pg_has_role(SESSION_USER, 'postgres', 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unauthorized: caller (%) is not a member of auren_worker role', SESSION_USER USING ERRCODE = '42501';
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
-- 4. PERMISSION GRANTS & REVOCATIONS
-- ============================================================================

-- Revoke all by default
REVOKE ALL ON FUNCTION public.consume_journal_consent_rpc(UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.reap_stale_extraction_jobs_rpc(INT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_system_asserted_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.activate_embedding_model_rpc(TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;

-- Grant client consent consumption to authenticated
GRANT EXECUTE ON FUNCTION public.consume_journal_consent_rpc(UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ) TO authenticated;

-- Grant worker RPCs exclusively to auren_worker
GRANT EXECUTE ON FUNCTION public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.reap_stale_extraction_jobs_rpc(INT) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.create_system_asserted_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.activate_embedding_model_rpc(TEXT, TEXT, TEXT) TO auren_worker;
-- Migration: 015_worker_authorization_and_consent_hardening.sql
-- Description: Removes implicit PostgreSQL administrator access from worker-only RPCs,
--              establishes strict session-role membership verification via is_authorized_worker_session(),
--              enforces claim-token validation prior to idempotency in completion RPC,
--              implements in-database regex sanitization of worker failure error messages,
--              and adds an auditable administrative emergency maintenance procedure.

-- ============================================================================
-- 1. STRICT WORKER SESSION AUTHORIZATION HELPER
-- ============================================================================

CREATE OR REPLACE FUNCTION public.is_authorized_worker_session()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    WITH RECURSIVE member_tree AS (
        SELECT member, roleid
        FROM pg_auth_members
        WHERE member = (SELECT oid FROM pg_roles WHERE rolname = SESSION_USER)
        UNION
        SELECT m.member, m.roleid
        FROM pg_auth_members m
        JOIN member_tree mt ON m.member = mt.roleid
    )
    SELECT (
        SESSION_USER = 'auren_worker'
        OR EXISTS (
            SELECT 1
            FROM member_tree mt
            WHERE mt.roleid = (SELECT oid FROM pg_roles WHERE rolname = 'auren_worker')
        )
    );
$$;

-- ============================================================================
-- 2. HARDENED WORKER RPC FUNCTIONS
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
    claim_token UUID,
    attempts INT,
    max_attempts INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    -- Verify caller session identity: strictly requires membership in auren_worker role
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_worker_id) > 255 THEN
        RAISE EXCEPTION 'Worker ID exceeds maximum length of 255 characters' USING ERRCODE = '22023';
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
        claim_token = gen_random_uuid(),  -- Fresh lease-generation token
        attempts = j.attempts + 1,
        updated_at = clock_timestamp()
    FROM candidate
    WHERE j.id = candidate.candidate_id
    RETURNING j.id, j.user_id, j.conversation_id, j.source_message_id, j.claim_token, j.attempts, j.max_attempts;
END;
$$;

-- Function: complete_memory_extraction_job_rpc
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
    -- Verify caller session identity
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER USING ERRCODE = '42501';
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

    -- Strict Claim Token Check: MUST match current job claim token, even if already completed
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has a different claim token', p_job_id USING ERRCODE = '22023';
    END IF;

    -- Safe Idempotency: if already completed under this exact claim token, return TRUE
    IF v_job.status = 'completed' THEN
        RETURN TRUE;
    END IF;

    -- Only processing jobs locked by this worker may transition to completed
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
    -- Verify caller session identity
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER USING ERRCODE = '42501';
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

    -- Strict Claim Token Check
    IF v_job.claim_token != p_claim_token THEN
        RAISE EXCEPTION 'Stale claim token: job % has a different claim token', p_job_id USING ERRCODE = '22023';
    END IF;

    IF v_job.status != 'processing' OR v_job.locked_by != trim(p_worker_id) THEN
        RAISE EXCEPTION 'Job % is not locked by worker %', p_job_id, p_worker_id USING ERRCODE = '42501';
    END IF;

    IF v_job.lease_expires_at < clock_timestamp() THEN
        RAISE EXCEPTION 'Job % lease expired at %; failure update rejected', p_job_id, v_job.lease_expires_at USING ERRCODE = '22023';
    END IF;

    -- In-database active error sanitization: scrub API keys, bearer tokens, JWTs, and passwords
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
            claim_token = gen_random_uuid(),  -- Fresh token on requeue
            last_error = v_sanitized_error,
            scheduled_at = clock_timestamp() + (POWER(2, v_job.attempts) * 5 || ' seconds')::INTERVAL,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    ELSE
        -- Terminal dead-letter state
        UPDATE public.memory_extraction_jobs
        SET status = 'dead_letter',
            locked_by = NULL,
            lease_expires_at = NULL,
            claim_token = gen_random_uuid(),  -- Invalidate claim
            last_error = v_sanitized_error,
            updated_at = clock_timestamp()
        WHERE id = p_job_id;
    END IF;

    RETURN TRUE;
END;
$$;

-- Function: insert_extracted_memory_rpc
CREATE OR REPLACE FUNCTION public.insert_extracted_memory_rpc(
    p_job_id UUID,
    p_worker_id TEXT,
    p_claim_token UUID,
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
    -- Verify caller session identity
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER USING ERRCODE = '42501';
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
        RAISE EXCEPTION 'Stale claim token: job % has a different claim token; ingestion rejected', p_job_id USING ERRCODE = '22023';
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

    IF length(p_content) > 10000 THEN
        RAISE EXCEPTION 'Memory content exceeds maximum permitted length' USING ERRCODE = '22023';
    END IF;

    IF p_memory_type NOT IN ('fact', 'preference', 'goal', 'project', 'context', 'observation') THEN
        RAISE EXCEPTION 'Invalid memory_type: %', p_memory_type USING ERRCODE = '22023';
    END IF;

    IF p_category NOT IN ('personal', 'work', 'technical', 'health_lifestyle', 'financial', 'general') THEN
        RAISE EXCEPTION 'Invalid category: %', p_category USING ERRCODE = '22023';
    END IF;

    IF p_importance IS NOT NULL AND (p_importance < 1 OR p_importance > 5) THEN
        RAISE EXCEPTION 'Importance must be between 1 and 5' USING ERRCODE = '22023';
    END IF;

    -- Deduplication check: return existing ID if identical memory already stored
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
    -- Verify caller session identity
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER USING ERRCODE = '42501';
    END IF;

    -- Move exhausted leases to dead_letter (strictly terminal, new claim_token)
    UPDATE public.memory_extraction_jobs
    SET status = 'dead_letter',
        locked_by = NULL,
        lease_expires_at = NULL,
        claim_token = gen_random_uuid(),
        last_error = 'Lease expired and max attempts exceeded',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts >= p_max_retries;

    GET DIAGNOSTICS v_dead_lettered = ROW_COUNT;

    -- Return recoverable expired leases to pending (generates new claim_token)
    UPDATE public.memory_extraction_jobs
    SET status = 'pending',
        locked_by = NULL,
        locked_at = NULL,
        lease_expires_at = NULL,
        claim_token = gen_random_uuid(),
        last_error = 'Lease expired; automatically recovered for retry',
        updated_at = clock_timestamp()
    WHERE status = 'processing'
      AND lease_expires_at < clock_timestamp()
      AND attempts < p_max_retries;

    GET DIAGNOSTICS v_reaped = ROW_COUNT;

    RETURN v_reaped + v_dead_lettered;
END;
$$;

-- Function: create_system_asserted_memory_rpc
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
    -- Verify caller session identity
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER USING ERRCODE = '42501';
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
    -- Verify caller session identity
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER USING ERRCODE = '42501';
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
-- 3. AUDITABLE ADMINISTRATIVE EMERGENCY MAINTENANCE PROCEDURE
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.admin_maintenance_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_user_name TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id UUID,
    reason TEXT NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.admin_maintenance_audit_log ENABLE ROW LEVEL SECURITY;

-- Deny all access to admin_maintenance_audit_log from client roles
REVOKE ALL ON TABLE public.admin_maintenance_audit_log FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.admin_emergency_reset_job_rpc(
    p_job_id UUID,
    p_reason TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    -- Administrative check: requires session user to be an actual administrator
    IF NOT (
        COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = SESSION_USER), FALSE)
        OR SESSION_USER = 'postgres'
        OR (EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') AND pg_has_role(SESSION_USER, 'postgres', 'MEMBER'))
    ) THEN
        RAISE EXCEPTION 'Unauthorized: administrative access required' USING ERRCODE = '42501';
    END IF;

    IF p_job_id IS NULL THEN
        RAISE EXCEPTION 'Job ID cannot be null' USING ERRCODE = '22023';
    END IF;

    IF p_reason IS NULL OR length(trim(p_reason)) < 10 THEN
        RAISE EXCEPTION 'Administrative maintenance requires an explicit reason (minimum 10 characters)' USING ERRCODE = '22023';
    END IF;

    UPDATE public.memory_extraction_jobs
    SET status = 'pending',
        locked_by = NULL,
        locked_at = NULL,
        lease_expires_at = NULL,
        claim_token = gen_random_uuid(),
        last_error = 'Admin emergency reset: ' || substr(trim(p_reason), 1, 200),
        updated_at = clock_timestamp()
    WHERE id = p_job_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Job % not found', p_job_id USING ERRCODE = 'P0002';
    END IF;

    INSERT INTO public.admin_maintenance_audit_log (session_user_name, action, target_id, reason)
    VALUES (SESSION_USER, 'admin_emergency_reset_job', p_job_id, trim(p_reason));

    RETURN TRUE;
END;
$$;

-- ============================================================================
-- 4. PERMISSION GRANTS & REVOCATIONS
-- ============================================================================

-- Revoke all worker functions from PUBLIC, anon, authenticated
REVOKE ALL ON FUNCTION public.is_authorized_worker_session() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.reap_stale_extraction_jobs_rpc(INT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_system_asserted_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.activate_embedding_model_rpc(TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.admin_emergency_reset_job_rpc(UUID, TEXT) FROM PUBLIC, anon, authenticated;

-- Grant worker RPCs exclusively to auren_worker
GRANT EXECUTE ON FUNCTION public.is_authorized_worker_session() TO auren_worker;
GRANT EXECUTE ON FUNCTION public.claim_memory_extraction_jobs_rpc(TEXT, INT, INT) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.complete_memory_extraction_job_rpc(UUID, TEXT, UUID) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.reap_stale_extraction_jobs_rpc(INT) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.create_system_asserted_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB) TO auren_worker;
GRANT EXECUTE ON FUNCTION public.activate_embedding_model_rpc(TEXT, TEXT, TEXT) TO auren_worker;
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
-- Score(m) = 0.35 * S_sem(m) + 0.30 * S_lex(m) + 0.15 * (importance / 5.0) + D(m) + 0.10 * conf(m)
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
-- ============================================================================
-- AUREN — Phase 3B.2.2 Step 2B: Retrieval Identity, Migration Upgrade Safety
-- and Worker Service Reconciliation
-- Forward migration upgrading from baseline 20261116000016
-- ============================================================================

-- ============================================================================
-- 1. EMBEDDING REGISTRY UPDATE: ACTIVATE GEMINI-EMBEDDING-2 (768-DIM)
-- ============================================================================

-- Deactivate existing active models for retrieval to respect the partial index:
-- idx_embedding_models_single_active_per_purpose ON embedding_models(purpose) WHERE is_active IS TRUE;
UPDATE public.embedding_models
SET is_active = FALSE
WHERE purpose = 'retrieval';

-- Register and activate Google gemini-embedding-2 (768 dimensions).
-- Keep text-embedding-004 in historical registry data as inactive (retired 14 Jan 2026).
INSERT INTO public.embedding_models (
    provider,
    model,
    version,
    dimension,
    vector_column,
    purpose,
    is_active
)
VALUES 
    ('gemini', 'gemini-embedding-2', 'v1', 768, 'embedding_768', 'retrieval', TRUE),
    ('gemini', 'text-embedding-004', 'v1', 768, 'embedding_768', 'retrieval', FALSE),
    ('openai', 'text-embedding-3-small', 'v1', 1536, 'embedding_1536', 'retrieval', FALSE)
ON CONFLICT (provider, model, version) DO UPDATE 
SET is_active = EXCLUDED.is_active,
    dimension = EXCLUDED.dimension,
    vector_column = EXCLUDED.vector_column,
    purpose = EXCLUDED.purpose;

-- ============================================================================
-- 2. WORKER ROLE RECONCILIATION & STRICT TABLE PRIVILEGE ENFORCEMENT
-- ============================================================================

-- Reconcile worker role definitions:
-- auren_worker is NOLOGIN NOINHERIT (group role for RPC execution privilege)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker') THEN
        ALTER ROLE auren_worker NOLOGIN NOINHERIT;
    ELSE
        CREATE ROLE auren_worker NOLOGIN NOINHERIT;
    END IF;

    -- auren_worker_service is the dedicated login role possessing membership in auren_worker
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker_service') THEN
        CREATE ROLE auren_worker_service WITH LOGIN;
    END IF;
    GRANT auren_worker TO auren_worker_service;
END $$;

-- Revoke direct table privileges from auren_worker.
-- All worker queue interactions, source message fetches, and memory writes must use
-- SECURITY DEFINER RPCs exclusively.
REVOKE ALL ON TABLE public.messages FROM auren_worker;
REVOKE ALL ON TABLE public.journal_entries FROM auren_worker;
REVOKE ALL ON TABLE public.memories FROM auren_worker;
REVOKE ALL ON TABLE public.memory_embeddings FROM auren_worker;
REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE public.memory_extraction_jobs FROM auren_worker;
DROP POLICY IF EXISTS "extraction_jobs_worker_select" ON public.memory_extraction_jobs;

-- ============================================================================
-- 3. EPISTEMIC PROVENANCE & MEMORY INGESTION RPC WITH FULL MODEL IDENTITY
-- ============================================================================

-- Drop prior function signatures to eliminate signature ambiguity
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, REAL, JSONB);
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector);
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector, TEXT);
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector, TEXT, TEXT, TEXT, INT);

-- Function: insert_extracted_memory_rpc
-- Enforces:
-- 1. Valid worker claim token and unexpired lease.
-- 2. Non-quarantined, dialogue-originating source message.
-- 3. Inferred dialogue provenance: origin='chat_inferred', confirmation_status='unconfirmed'.
-- 4. Rejection of worker-created 'system_asserted' memories.
-- 5. Deduplication against existing active memories from same source turn.
-- 6. Atomic embedding persistence validating full (provider, model, version, dimension) identity.
-- 7. Disallows new embedding generation using retired models (e.g. text-embedding-004).
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
    p_embedding_768 vector(768) DEFAULT NULL,
    p_model TEXT DEFAULT 'gemini-embedding-2',
    p_provider TEXT DEFAULT 'gemini',
    p_version TEXT DEFAULT 'v1',
    p_dimension INT DEFAULT 768
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
    v_model TEXT;
    v_provider TEXT;
    v_version TEXT;
    v_dimension INT;
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    IF p_claim_token IS NULL THEN
        RAISE EXCEPTION 'Claim token cannot be null' USING ERRCODE = '22023';
    END IF;

    -- Validate extraction job existence, claim ownership, and lease validity
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

    -- Content validation
    IF p_content IS NULL OR length(trim(p_content)) = 0 THEN
        RAISE EXCEPTION 'Memory content cannot be empty' USING ERRCODE = '22023';
    END IF;

    IF length(p_content) > 10000 THEN
        RAISE EXCEPTION 'Memory content exceeds maximum permitted length' USING ERRCODE = '22023';
    END IF;

    -- Validate memory_type domain
    IF p_memory_type NOT IN ('fact', 'preference', 'goal', 'project', 'context', 'observation') THEN
        RAISE EXCEPTION 'Invalid memory_type: %', p_memory_type USING ERRCODE = '22023';
    END IF;

    -- Validate category domain
    IF p_category NOT IN ('personal', 'work', 'technical', 'health_lifestyle', 'financial', 'general') THEN
        RAISE EXCEPTION 'Invalid category: %', p_category USING ERRCODE = '22023';
    END IF;

    -- Importance range [1, 5]
    IF p_importance IS NULL OR p_importance < 1 OR p_importance > 5 THEN
        RAISE EXCEPTION 'Importance must be between 1 and 5' USING ERRCODE = '22023';
    END IF;

    -- Confidence range [0.0, 1.0] if provided
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

    -- Deduplication: check if exact content already exists for this user from this source turn
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

    -- Validate embedding identity before memory insertion if vector embedding is provided
    IF p_embedding_768 IS NOT NULL THEN
        v_model := COALESCE(trim(p_model), 'gemini-embedding-2');
        v_provider := COALESCE(trim(p_provider), 'gemini');
        v_version := COALESCE(trim(p_version), 'v1');
        v_dimension := COALESCE(p_dimension, 768);

        -- Disallow new generation using retired model text-embedding-004
        IF v_model = 'text-embedding-004' THEN
            RAISE EXCEPTION 'Model text-embedding-004 is retired and cannot be used for new embeddings'
                USING ERRCODE = 'P0003';
        END IF;

        -- Verify that the specified embedding model is registered, active, and configured for retrieval
        IF NOT EXISTS (
            SELECT 1 FROM public.embedding_models
            WHERE provider = v_provider
              AND model = v_model
              AND version = v_version
              AND dimension = v_dimension
              AND purpose = 'retrieval'
              AND is_active = TRUE
        ) THEN
            RAISE EXCEPTION 'Embedding model %/%/% (%-dim) is not an active registered retrieval model',
                v_provider, v_model, v_version, v_dimension USING ERRCODE = 'P0002';
        END IF;
    END IF;

    -- Insert active unconfirmed memory with inferred dialogue provenance
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
            v_provider,
            v_model,
            v_version,
            v_dimension,
            p_embedding_768,
            TRUE
        )
        ON CONFLICT (memory_id, provider, model, version) DO UPDATE
        SET embedding_768 = EXCLUDED.embedding_768,
            dimension = EXCLUDED.dimension,
            is_active = TRUE;
    END IF;

    RETURN v_memory_id;
END;
$$;

REVOKE ALL ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector, TEXT, TEXT, TEXT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector, TEXT, TEXT, TEXT, INT) TO auren_worker;

-- ============================================================================
-- 4. HYBRID MEMORY RETRIEVAL RPC WITH COMPLETE MODEL IDENTITY & LEXICAL FALLBACK
-- ============================================================================

-- Drop previous signatures to eliminate ambiguity
DROP FUNCTION IF EXISTS public.search_memories_hybrid_rpc(TEXT, vector, INT, REAL);
DROP FUNCTION IF EXISTS public.search_memories_hybrid_rpc(TEXT, vector, INT, REAL, TEXT);
DROP FUNCTION IF EXISTS public.search_memories_hybrid_rpc(TEXT, vector, INT, REAL, TEXT, TEXT, TEXT, INT);

-- Function: search_memories_hybrid_rpc
-- Mathematical Scoring Formulation:
-- Score(m) = 0.40 * S_sem(m) + 0.25 * S_lex(m) + 0.15 * (importance / 5.0) + D(m) + 0.10 * conf(m)
-- Bounds:
-- - S_sem in [0.0, 1.0] (isolated strictly to active registered embedding model identity)
-- - S_lex in [0.0, 1.0) via ts_rank_cd(..., 32)
-- - Normalized importance in [0.03, 0.15]
-- - Recency decay D(m) in (0, 0.10]
-- - Confidence in [0.0, 0.10] with 0.50 fallback
-- Total Score strictly in [0.0, 1.0].
--
-- Model Identity Isolation:
-- Resolves complete registered identity (provider, model, version, dimension) for active retrieval.
-- Query embeddings and document embeddings must match the complete 4-tuple.
--
-- Lexical Fallback Under Semantic Thresholds:
-- If p_min_similarity > 0, candidates with compatible embeddings must meet s_sem >= p_min_similarity.
-- Candidates without compatible embeddings remain eligible through lexical retrieval (s_lex > 0).
-- Incompatible or missing vectors contribute strictly 0.0 to S_sem.
CREATE OR REPLACE FUNCTION public.search_memories_hybrid_rpc(
    p_query_text TEXT,
    p_query_embedding vector(768) DEFAULT NULL,
    p_limit INT DEFAULT 5,
    p_min_similarity REAL DEFAULT 0.0,
    p_model TEXT DEFAULT NULL,
    p_provider TEXT DEFAULT NULL,
    p_version TEXT DEFAULT NULL,
    p_dimension INT DEFAULT NULL
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
    v_target_provider TEXT;
    v_target_model TEXT;
    v_target_version TEXT;
    v_target_dimension INT;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;

    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 50 THEN
        p_limit := 5;
    END IF;

    -- Validate query components
    v_has_embedding := (p_query_embedding IS NOT NULL);
    v_has_text := (p_query_text IS NOT NULL AND length(trim(p_query_text)) > 0);

    -- Parse websearch tsquery safely
    IF v_has_text THEN
        v_tsquery := plainto_tsquery('english', p_query_text);
        IF v_tsquery = ''::tsquery THEN
            v_has_text := FALSE;
            v_tsquery := NULL;
        END IF;
    ELSE
        v_tsquery := NULL;
    END IF;

    -- Establish target embedding space for active retrieval.
    -- Prevent cross-model and cross-version contamination.
    IF p_model IS NOT NULL OR p_provider IS NOT NULL OR p_version IS NOT NULL OR p_dimension IS NOT NULL THEN
        SELECT provider, model, version, dimension
        INTO v_target_provider, v_target_model, v_target_version, v_target_dimension
        FROM public.embedding_models
        WHERE purpose = 'retrieval'
          AND is_active = TRUE
          AND (p_provider IS NULL OR provider = trim(p_provider))
          AND (p_model IS NULL OR model = trim(p_model))
          AND (p_version IS NULL OR version = trim(p_version))
          AND (p_dimension IS NULL OR dimension = p_dimension)
        LIMIT 1;
    ELSE
        SELECT provider, model, version, dimension
        INTO v_target_provider, v_target_model, v_target_version, v_target_dimension
        FROM public.embedding_models
        WHERE purpose = 'retrieval'
          AND is_active = TRUE
        LIMIT 1;
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
            -- Component 1: Semantic similarity S_sem in [0, 1] strictly matching target model identity
            (CASE
                WHEN v_has_embedding AND v_target_model IS NOT NULL AND emb.embedding_768 IS NOT NULL THEN
                    GREATEST(0.0::real, LEAST(1.0::real, (1.0 - (emb.embedding_768 <=> p_query_embedding))::real))
                ELSE 0.0::real
            END) AS s_sem,
            -- Component 2: Lexical rank S_lex in [0, 1) using ts_rank_cd flag 32
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
            (0.10::real * COALESCE(m.confidence::real, 0.50::real)) AS s_conf,
            -- Compatibility flag: whether candidate possesses an active embedding in target space
            (v_has_embedding AND v_target_model IS NOT NULL AND emb.embedding_768 IS NOT NULL) AS has_compatible_emb
        FROM public.memories m
        LEFT JOIN LATERAL (
            SELECT me.embedding_768
            FROM public.memory_embeddings me
            WHERE me.memory_id = m.id
              AND me.user_id = v_user_id
              AND me.is_active = TRUE
              AND v_target_model IS NOT NULL
              AND me.provider = v_target_provider
              AND me.model = v_target_model
              AND me.version = v_target_version
              AND me.dimension = v_target_dimension
              AND me.embedding_768 IS NOT NULL
            ORDER BY me.created_at DESC
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
    WHERE (
        -- If min_similarity is 0 (or null), all active memories are eligible (scored by rank formula)
        (p_min_similarity IS NULL OR p_min_similarity <= 0.0)
        -- If no query embedding was supplied, candidate must have text match (or empty query)
        OR (v_has_embedding IS FALSE AND (v_has_text IS FALSE OR s.s_lex > 0))
        -- If candidate has compatible embedding, semantic threshold applies
        OR (s.has_compatible_emb AND s.s_sem >= p_min_similarity)
        -- If candidate lacks compatible embedding, it remains eligible through lexical retrieval
        OR (NOT s.has_compatible_emb AND v_has_text AND s.s_lex > 0)
    )
    ORDER BY score DESC
    LIMIT p_limit;
END;
$$;

REVOKE ALL ON FUNCTION public.search_memories_hybrid_rpc(TEXT, vector, INT, REAL, TEXT, TEXT, TEXT, INT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.search_memories_hybrid_rpc(TEXT, vector, INT, REAL, TEXT, TEXT, TEXT, INT) TO authenticated;
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
-- =============================================================================
-- Migration 021: Omnisearch Support & Cross-Entity Record Links
-- Phase 3C.5: Reflective Intelligence & Omnisearch
-- =============================================================================
-- Introduces:
--   1. record_links — user-isolated cross-entity relationship graph with RLS.
--   2. Full-text search indexes on tasks, projects, goals (pg_trgm trigrams).
--   3. Composite indexes on conversations and messages for search efficiency.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Enable pg_trgm extension (safe no-op if already present)
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- 2. record_links table — tenant-isolated cross-entity relationship store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS record_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL
                        CHECK (source_type IN ('conversation','message','memory','task','project','goal')),
    source_id       UUID NOT NULL,
    target_type     TEXT NOT NULL
                        CHECK (target_type IN ('conversation','message','memory','task','project','goal')),
    target_id       UUID NOT NULL,
    relationship_type TEXT NOT NULL DEFAULT 'related'
                        CHECK (relationship_type IN ('related','supports','contradicts','supersedes','derived_from','referenced_in')),
    confidence      NUMERIC(4,3) NOT NULL DEFAULT 1.000
                        CHECK (confidence >= 0 AND confidence <= 1),
    is_inferred     BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Prevent duplicate links between the same pair in the same direction
    CONSTRAINT record_links_unique_pair UNIQUE (user_id, source_type, source_id, target_type, target_id, relationship_type)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_record_links_user     ON record_links (user_id);
CREATE INDEX IF NOT EXISTS idx_record_links_source   ON record_links (user_id, source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_record_links_target   ON record_links (user_id, target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_record_links_inferred ON record_links (user_id, is_inferred);

-- updated_at trigger
CREATE OR REPLACE FUNCTION set_record_links_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_record_links_updated_at ON record_links;
CREATE TRIGGER trg_record_links_updated_at
    BEFORE UPDATE ON record_links
    FOR EACH ROW EXECUTE FUNCTION set_record_links_updated_at();

-- ---------------------------------------------------------------------------
-- 3. Row-Level Security on record_links
-- ---------------------------------------------------------------------------
ALTER TABLE record_links ENABLE ROW LEVEL SECURITY;

-- Drop any old policies first (idempotent)
DROP POLICY IF EXISTS record_links_select ON record_links;
DROP POLICY IF EXISTS record_links_insert ON record_links;
DROP POLICY IF EXISTS record_links_update ON record_links;
DROP POLICY IF EXISTS record_links_delete ON record_links;

CREATE POLICY record_links_select ON record_links
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY record_links_insert ON record_links
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY record_links_update ON record_links
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY record_links_delete ON record_links
    FOR DELETE TO authenticated
    USING (user_id = auth.uid());

-- Revoke anon access
REVOKE ALL ON record_links FROM anon;

-- ---------------------------------------------------------------------------
-- 4. Full-text / trigram search indexes on productivity tables
-- ---------------------------------------------------------------------------

-- tasks
CREATE INDEX IF NOT EXISTS idx_tasks_title_trgm
    ON tasks USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_tasks_description_trgm
    ON tasks USING gin (description gin_trgm_ops)
    WHERE description IS NOT NULL;

-- projects
CREATE INDEX IF NOT EXISTS idx_projects_name_trgm
    ON projects USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_projects_description_trgm
    ON projects USING gin (description gin_trgm_ops)
    WHERE description IS NOT NULL;

-- goals
CREATE INDEX IF NOT EXISTS idx_goals_title_trgm
    ON goals USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_goals_description_trgm
    ON goals USING gin (description gin_trgm_ops)
    WHERE description IS NOT NULL;

-- conversations (title search)
CREATE INDEX IF NOT EXISTS idx_conversations_title_trgm
    ON conversations USING gin (title gin_trgm_ops)
    WHERE title IS NOT NULL;

-- messages (content full-text search)
CREATE INDEX IF NOT EXISTS idx_messages_content_trgm
    ON messages USING gin (content gin_trgm_ops)
    WHERE content IS NOT NULL;

-- memories (content full-text search) — backup to vector retrieval
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm
    ON memories USING gin (content gin_trgm_ops)
    WHERE lifecycle_status IN ('active', 'superseded');

-- ---------------------------------------------------------------------------
-- 5. Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE record_links IS
    'Phase 3C.5: Tenant-isolated cross-entity relationship graph for Reflective Intelligence. '
    'Rows are strictly owned by user_id via RLS. is_inferred=TRUE marks AI-suggested links '
    'that have not been confirmed by the user.';

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

-- Migration: Add cryptographic integrity signature column to journal_entries
-- Supports RFC 8785 canonical JSON and HMAC-SHA256 integrity verification.

ALTER TABLE public.journal_entries
ADD COLUMN IF NOT EXISTS integrity_signature TEXT;

COMMENT ON COLUMN public.journal_entries.integrity_signature IS
'RFC 8785 canonical JSON HMAC-SHA256 integrity signature for tamper detection.';
-- Migration: RPC for background worker to securely retrieve user extraction preferences

CREATE OR REPLACE FUNCTION public.get_user_extraction_preferences_rpc(
    p_user_id UUID,
    p_worker_id TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_prefs JSONB;
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user does not possess the auren_worker role'
            USING ERRCODE = '42501';
    END IF;

    SELECT preferences INTO v_prefs FROM public.profiles WHERE id = p_user_id;
    RETURN COALESCE(v_prefs, '{}'::jsonb);
END;
$$;

REVOKE ALL ON FUNCTION public.get_user_extraction_preferences_rpc(UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_user_extraction_preferences_rpc(UUID, TEXT) TO auren_worker;
