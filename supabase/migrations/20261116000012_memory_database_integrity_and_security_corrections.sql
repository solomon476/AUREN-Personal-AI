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
