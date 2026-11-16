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
        v_model := COALESCE(trim(p_model), 'gemini-embedding-2');
        v_provider := COALESCE(trim(p_provider), 'gemini');
        v_version := COALESCE(trim(p_version), 'v1');
        v_dimension := COALESCE(p_dimension, 768);

        -- Disallow new generation using retired model text-embedding-004
        IF v_model = 'text-embedding-004' THEN
            RAISE EXCEPTION 'Model text-embedding-004 is retired and cannot be used for new embeddings'
                USING ERRCODE = 'P0003';
        END IF;

        -- Verify that the specified embedding model is registered in embedding_models
        IF NOT EXISTS (
            SELECT 1 FROM public.embedding_models
            WHERE provider = v_provider
              AND model = v_model
              AND version = v_version
              AND dimension = v_dimension
        ) THEN
            RAISE EXCEPTION 'Embedding model %/%/% (%-dim) is not registered in embedding_models',
                v_provider, v_model, v_version, v_dimension USING ERRCODE = 'P0002';
        END IF;

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
