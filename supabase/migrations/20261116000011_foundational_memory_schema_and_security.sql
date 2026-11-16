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

