-- ============================================================================
-- AUREN — STAGING LEAST-PRIVILEGE PERMISSION GRANTS (PHASE 6.2B FINALIZED)
-- Idempotent, least-privilege security hardening for public schema.
-- ============================================================================

-- 1. SCHEMA USAGE
GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- 2. USER TABLES: FULL CRUD (Enforced by Row Level Security)
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE 
    public.profiles,
    public.projects,
    public.tasks,
    public.conversations,
    public.messages,
    public.journal_entries,
    public.goals,
    public.milestones,
    public.briefings,
    public.record_links
TO authenticated;

-- 3. USER TABLES: RESTRICTED READ-ONLY ACCESS
-- Memories: Direct INSERT/UPDATE/DELETE revoked to protect epistemic provenance.
GRANT SELECT ON TABLE public.memories TO authenticated;

-- Chat Requests: Direct INSERT/UPDATE/DELETE revoked to enforce idempotency matrix.
-- Anon access is strictly revoked.
GRANT SELECT ON TABLE public.chat_requests TO authenticated;

-- Embedding Models: Read-only active model lookup for hybrid search.
GRANT SELECT ON TABLE public.embedding_models TO authenticated;

-- 4. SEQUENCES: DEFENSIVE USAGE
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- 5. CHAT LIFECYCLE RPC FUNCTIONS (Callable by authenticated callers)
GRANT EXECUTE ON FUNCTION public.claim_chat_request(TEXT, UUID, UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.complete_chat_request(TEXT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fail_chat_request(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.interrupt_chat_request(TEXT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.retry_chat_request(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.reconcile_chat_request(TEXT, UUID) TO authenticated;

-- 6. MEMORY MANAGEMENT RPC FUNCTIONS (Callable by authenticated callers)
GRANT EXECUTE ON FUNCTION public.create_memory_rpc(
    TEXT, TEXT, TEXT, INT, TEXT, TEXT, REAL, TIMESTAMPTZ, TIMESTAMPTZ, UUID, UUID, JSONB
) TO authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_memory_rpc(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.reject_memory_rpc(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.supersede_memory_rpc(
    UUID, TEXT, TEXT, TEXT, INT, TEXT, TEXT, JSONB
) TO authenticated;
GRANT EXECUTE ON FUNCTION public.archive_memory_rpc(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.delete_memory_rpc(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.restore_memory_rpc(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.outdate_memory_rpc(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.purge_all_memories_rpc() TO authenticated;
GRANT EXECUTE ON FUNCTION public.enqueue_memory_extraction_job_rpc(UUID, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.search_memories_hybrid_rpc(
    TEXT, vector, INT, REAL, TEXT, TEXT, TEXT, INT
) TO authenticated;

-- 7. JOURNAL CONSENT & RECORD LINK RPC FUNCTIONS
GRANT EXECUTE ON FUNCTION public.consume_journal_consent_rpc(
    UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ
) TO authenticated;
GRANT EXECUTE ON FUNCTION public.validate_record_link_endpoints() TO authenticated;
GRANT EXECUTE ON FUNCTION public.validate_record_link_endpoints() TO service_role;

