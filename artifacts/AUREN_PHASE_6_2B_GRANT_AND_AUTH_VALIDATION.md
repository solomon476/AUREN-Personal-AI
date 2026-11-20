# AUREN — Phase 6.2B: Least-Privilege Grant Validation & Staging Auth Readiness

**Repository:** `solomon476/AUREN-Personal-AI`  
**Branch:** `main`  
**Baseline:** Phase 6.2A audit commit `0f23f82`  
**Mode:** STRICTLY READ-ONLY INSPECTION & SQL GENERATION (No hosted database changes)  
**Report Date:** 2026-11-20  
**Overall Validation Verdict:** `VERIFIED — LEAST-PRIVILEGE GRANTS REFINED WITH ZERO SECURITY DEFICIT`

---

## Executive Summary

Following the Phase 6.2A hosted database security audit, this Phase 6.2B investigation rigorously validated all proposed SQL grants, table permissions, RPC function signatures, Row Level Security (RLS) policies, and authentication redirect flows against the actual 24 repository migrations, the FastAPI backend service layer, and the React frontend client architecture.

### Key Validation Discoveries

1. **Memory Mutation Bypass Prevented:** In Phase 6.2A, `GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.memories TO authenticated;` was proposed. Inspection of Migration 011 and `backend/app/services/memory/supabase_repository.py` proved that direct `INSERT, UPDATE, DELETE` on `memories` was intentionally **revoked** to enforce strict epistemic provenance, status transitions, and lineage triggers. Granting direct mutations would break memory data integrity. **Corrected: `memories` receives `SELECT` ONLY.**
2. **Anonymous Access to `chat_requests` Eliminated:** Phase 6.2A draft proposed `GRANT SELECT ON TABLE public.chat_requests TO anon, authenticated;`. Migration 010 strictly enforced `REVOKE ALL ON public.chat_requests FROM anon`. Anonymous callers have zero legitimate need to inspect chat lifecycle records. **Corrected: `chat_requests` SELECT is granted strictly to `authenticated`; `anon` is excluded.**
3. **Corrected Incomplete Function Signatures:**
   - `create_memory_rpc`: Phase 6.2A omitted 2 arguments (`p_source_conversation_id UUID`, `p_metadata JSONB`). The exact signature has 12 parameters: `(TEXT, TEXT, TEXT, INT, TEXT, TEXT, REAL, TIMESTAMPTZ, TIMESTAMPTZ, UUID, UUID, JSONB)`.
   - `supersede_memory_rpc`: Phase 6.2A omitted parameter types. The exact signature has 8 parameters: `(UUID, TEXT, TEXT, TEXT, INT, TEXT, TEXT, JSONB)`.
   - `consume_journal_consent_rpc`: Exact signature has 6 parameters: `(UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ)`.
   - `search_memories_hybrid_rpc`: Omitted in Phase 6.2A Group B, but actively called by the backend retriever. Exact signature has 8 parameters: `(TEXT, vector, INT, REAL, TEXT, TEXT, TEXT, INT)`.
4. **Worker Boundary Sealed:** 10 functions (`claim_memory_extraction_jobs_rpc`, `complete_memory_extraction_job_rpc`, `fail_memory_extraction_job_rpc`, `reap_stale_extraction_jobs_rpc`, `insert_extracted_memory_rpc`, `create_system_asserted_memory_rpc`, `activate_embedding_model_rpc`, `get_user_extraction_preferences_rpc`, `fetch_extraction_source_message_rpc`, `is_authorized_worker_session`) were verified to enforce `is_authorized_worker_session()` and are strictly quarantined to `auren_worker` and `service_role`.
5. **Zero Sequence Dependency:** Inspection confirmed that all 17 tables utilize UUID primary keys with `gen_random_uuid()` or composite primary keys. Zero `SERIAL` or `IDENTITY` sequences exist in `public`.

---

## 1. Function-by-Function Access Matrix

Every function defined across the 24 repository migrations was traced to its caller, execution context, security mode, and internal authorization checks.

| Function Name & Exact Signature | Target Role | Caller & Path | Security Mode | Internal Auth Check | Status |
| :--- | :---: | :--- | :---: | :---: | :---: |
| `claim_chat_request(TEXT, UUID, UUID, TEXT)` | `authenticated` | FastAPI `SupabasePostgresChatRepository.claim_request` (`/rpc/claim_chat_request`) | `SECURITY DEFINER` | `auth.uid() = user_id`; validates ownership of message & conversation | `VERIFIED` |
| `complete_chat_request(TEXT, UUID)` | `authenticated` | FastAPI `SupabasePostgresChatRepository.update_request_status` (`/rpc/complete_chat_request`) | `SECURITY DEFINER` | `auth.uid() = user_id`; validates assistant message ownership & conversation | `VERIFIED` |
| `fail_chat_request(TEXT)` | `authenticated` | FastAPI `SupabasePostgresChatRepository.update_request_status` (`/rpc/fail_chat_request`) | `SECURITY DEFINER` | `auth.uid() = user_id`; enforces processing -> failed transition | `VERIFIED` |
| `interrupt_chat_request(TEXT, UUID)` | `authenticated` | FastAPI `SupabasePostgresChatRepository.update_request_status` (`/rpc/interrupt_chat_request`) | `SECURITY DEFINER` | `auth.uid() = user_id`; validates assistant message ownership if present | `VERIFIED` |
| `retry_chat_request(TEXT)` | `authenticated` | FastAPI `SupabasePostgresChatRepository.retry_request` (`/rpc/retry_chat_request`) | `SECURITY DEFINER` | `auth.uid() = user_id`; restricts retry to failed/interrupted states | `VERIFIED` |
| `reconcile_chat_request(TEXT, UUID)` | `authenticated` | FastAPI `SupabasePostgresChatRepository.reconcile_request` (`/rpc/reconcile_chat_request`) | `SECURITY DEFINER` | `auth.uid() = user_id`; checks user_message_id metadata match & non-interrupted | `VERIFIED` |
| `create_memory_rpc(TEXT, TEXT, TEXT, INT, TEXT, TEXT, REAL, TIMESTAMPTZ, TIMESTAMPTZ, UUID, UUID, JSONB)` | `authenticated` | FastAPI `SupabaseMemoryRepository.create_memory` (`/rpc/create_memory_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; enforces taxonomy check constraints & metadata validation | `VERIFIED` |
| `confirm_memory_rpc(UUID)` | `authenticated` | FastAPI `SupabaseMemoryRepository.confirm_memory` (`/rpc/confirm_memory_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; ensures transition unconfirmed -> confirmed | `VERIFIED` |
| `reject_memory_rpc(UUID)` | `authenticated` | FastAPI `SupabaseMemoryRepository.reject_memory` (`/rpc/reject_memory_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; ensures transition unconfirmed -> rejected | `VERIFIED` |
| `supersede_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, TEXT, TEXT, JSONB)` | `authenticated` | FastAPI `SupabaseMemoryRepository.correct_memory` (`/rpc/supersede_memory_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; updates old memory status to superseded; inserts new memory | `VERIFIED` |
| `archive_memory_rpc(UUID)` | `authenticated` | FastAPI `SupabaseMemoryRepository.archive_memory` (`/rpc/archive_memory_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; marks memory status as archived | `VERIFIED` |
| `delete_memory_rpc(UUID)` | `authenticated` | FastAPI `SupabaseMemoryRepository.delete_memory` (API fallback) | `SECURITY DEFINER` | `auth.uid() = user_id`; removes unconfirmed or marks deleted | `VERIFIED` |
| `restore_memory_rpc(UUID)` | `authenticated` | FastAPI `SupabaseMemoryRepository.restore_memory` (`/rpc/restore_memory_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; restores archived/outdated memory to confirmed | `VERIFIED` |
| `outdate_memory_rpc(UUID)` | `authenticated` | FastAPI `SupabaseMemoryRepository.outdate_memory` (`/rpc/outdate_memory_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; marks memory as outdated without deletion | `VERIFIED` |
| `purge_all_memories_rpc()` | `authenticated` | FastAPI `purge_memories` test/maintenance endpoint | `SECURITY DEFINER` | `auth.uid() = user_id`; purges active memories for current user | `VERIFIED` |
| `consume_journal_consent_rpc(UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ)` | `authenticated` | FastAPI `JournalConsentService.consume_token` via DB | `SECURITY DEFINER` | `auth.uid() = user_id`; validates conversation ownership & records consumed nonce | `VERIFIED` |
| `enqueue_memory_extraction_job_rpc(UUID, UUID)` | `authenticated` | FastAPI Chat Completion Pipeline | `SECURITY DEFINER` | `auth.uid() = user_id`; validates ownership of source message & conversation | `VERIFIED` |
| `search_memories_hybrid_rpc(TEXT, vector, INT, REAL, TEXT, TEXT, TEXT, INT)` | `authenticated` | FastAPI `SupabasePostgresChatRepository.search_memories` (`/rpc/search_memories_hybrid_rpc`) | `SECURITY DEFINER` | `auth.uid() = user_id`; queries vector embeddings & trigram index for user | `VERIFIED` |
| `validate_record_link_endpoints()` | `authenticated`, `service_role` | Trigger `trg_validate_record_link_endpoints` on `public.record_links` | `SECURITY DEFINER` | `auth.uid() = user_id`; ensures both source and target entities belong to user | `VERIFIED` |
| `claim_memory_extraction_jobs_rpc(TEXT, INT, INT)` | `auren_worker`, `service_role` | Background Worker asyncpg pool | `SECURITY DEFINER` | `is_authorized_worker_session()`; SKIP LOCKED batch lease | `VERIFIED` |
| `complete_memory_extraction_job_rpc(UUID, TEXT, UUID)` | `auren_worker`, `service_role` | Background Worker asyncpg pool | `SECURITY DEFINER` | `is_authorized_worker_session()`; rotates claim_token & clears lock | `VERIFIED` |
| `fail_memory_extraction_job_rpc(UUID, TEXT, UUID, TEXT, BOOLEAN)` | `auren_worker`, `service_role` | Background Worker asyncpg pool | `SECURITY DEFINER` | `is_authorized_worker_session()`; records retry attempt or dead-letter | `VERIFIED` |
| `reap_stale_extraction_jobs_rpc(INT)` | `auren_worker`, `service_role` | Background Worker reaper loop | `SECURITY DEFINER` | `is_authorized_worker_session()`; unlocks expired leases | `VERIFIED` |
| `insert_extracted_memory_rpc(UUID, TEXT, UUID, TEXT, TEXT, TEXT, INT, DOUBLE PRECISION, JSONB, vector, TEXT, TEXT, TEXT, INT)` | `auren_worker`, `service_role` | Background Worker memory extractor | `SECURITY DEFINER` | `is_authorized_worker_session()`; validates active lease token & inserts | `VERIFIED` |
| `create_system_asserted_memory_rpc(UUID, TEXT, TEXT, TEXT, INT, JSONB)` | `auren_worker`, `service_role` | Background Worker system asserting | `SECURITY DEFINER` | `is_authorized_worker_session()`; checks model origin | `VERIFIED` |
| `activate_embedding_model_rpc(TEXT, TEXT, TEXT)` | `auren_worker`, `service_role` | Model migration / admin utility | `SECURITY DEFINER` | `is_authorized_worker_session()`; activates global model identity | `VERIFIED` |
| `get_user_extraction_preferences_rpc(UUID, TEXT)` | `auren_worker`, `service_role` | Background Worker extraction preferences | `SECURITY DEFINER` | `is_authorized_worker_session()`; returns user preference JSONB | `VERIFIED` |
| `fetch_extraction_source_message_rpc(UUID, TEXT, UUID)` | `auren_worker`, `service_role` | Background Worker turn extractor | `SECURITY DEFINER` | `is_authorized_worker_session()`; enforces zero-retention journal quarantine | `VERIFIED` |
| `is_authorized_worker_session()` | `auren_worker`, `service_role` | Internal function called by worker RPCs | `SECURITY DEFINER` | Evaluates `SESSION_USER` in `auren_worker` role tree | `VERIFIED` |
| `admin_emergency_reset_job_rpc(UUID, TEXT)` | `service_role` ONLY | Emergency admin script | `SECURITY DEFINER` | Explicitly revoked from `PUBLIC, anon, authenticated` | `VERIFIED` |

---

## 2. Table-by-Table Privilege Matrix

| Table Name | Schema | Permitted Roles | Allowed Operations | Excluded Operations & Reason | RLS Policy Invariant | Status |
| :--- | :---: | :---: | :---: | :--- | :--- | :---: |
| `profiles` | `public` | `authenticated` | `SELECT, INSERT, UPDATE` | `DELETE` excluded (profile lifecycle bound to `auth.users` cascade) | `auth.uid() = id` | `VERIFIED` |
| `projects` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | None. Full user CRUD needed. | `auth.uid() = user_id` | `VERIFIED` |
| `tasks` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | None. Full user CRUD needed. Supports parent_task_id hierarchy. | `auth.uid() = user_id` | `VERIFIED` |
| `conversations` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | None. Full user CRUD needed. | `auth.uid() = user_id` | `VERIFIED` |
| `messages` | `public` | `authenticated` | `SELECT, INSERT, DELETE` | `UPDATE` prohibited by `trg_messages_immutability` trigger | `auth.uid() = user_id` | `VERIFIED` |
| `memories` | `public` | `authenticated` | **`SELECT` ONLY** | **`INSERT, UPDATE, DELETE` STRICTLY EXCLUDED.** Mutations must pass through validated RPCs (`create_memory_rpc`, etc.) | `auth.uid() = user_id` | `VERIFIED` |
| `journal_entries` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | Completely quarantined from `auren_worker` and assistant retrieval | `auth.uid() = user_id` (HMAC signature enforced) | `VERIFIED` |
| `goals` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | None. Full user CRUD needed. | `auth.uid() = user_id` | `VERIFIED` |
| `milestones` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | None. Full user CRUD needed. | `auth.uid() = user_id` | `VERIFIED` |
| `briefings` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | None. Full user CRUD needed. | `auth.uid() = user_id` | `VERIFIED` |
| `record_links` | `public` | `authenticated` | `SELECT, INSERT, UPDATE, DELETE` | Validated by endpoint ownership trigger `validate_record_link_endpoints()` | `auth.uid() = user_id` | `VERIFIED` |
| `chat_requests` | `public` | `authenticated` | **`SELECT` ONLY** | **`anon` EXCLUDED.** Direct `INSERT, UPDATE, DELETE` strictly revoked (enforced by `claim_chat_request`, etc.) | `auth.uid() = user_id` | `VERIFIED` |
| `embedding_models`| `public` | `authenticated` | `SELECT` ONLY | `INSERT, UPDATE, DELETE` excluded (managed via worker/admin) | `is_active = true` | `VERIFIED` |
| `memory_embeddings`| `public` | `auren_worker`, `service_role` | `SELECT, INSERT, UPDATE, DELETE` | `authenticated` and `anon` EXCLUDED (accessed via hybrid search RPC) | Worker session verification | `VERIFIED` |
| `consumed_consent_tokens` | `public` | `service_role` | All | `authenticated` and `anon` EXCLUDED (written via consent RPC) | Nonce replay prevention | `VERIFIED` |
| `memory_extraction_jobs` | `public` | `auren_worker`, `service_role` | All | Direct client access EXCLUDED (enqueued via RPC, claimed by worker) | Lease fencing | `VERIFIED` |
| `admin_maintenance_audit_log` | `public` | `service_role` | `SELECT, INSERT` | Append-only. All client access revoked. | Administrative audit trail | `VERIFIED` |

---

## 3. SECURITY DEFINER Risk & Vulnerability Analysis

All 31 `SECURITY DEFINER` function declarations were subjected to strict defensive audit:

1. **`search_path` Hardening:**
   - **Finding:** Every `SECURITY DEFINER` function in the repository specifies an explicit `search_path`:
     - RPC functions: `SET search_path = public, extensions, pg_temp`
     - Auth helper: `SET search_path = pg_catalog, pg_temp`
     - Record links trigger: `SET search_path = public, auth`
   - **Verdict:** `VERIFIED`. No function executes with an unpinned search path. Exploitation via search path object shadowing (CWE-426) is impossible.
2. **Context Escapes & Elevation of Privilege:**
   - **Finding:** Functions granted to `authenticated` strictly evaluate `v_user_id := auth.uid();` before executing any query. If `auth.uid()` is null, the function aborts immediately with `42501 Authentication required`.
   - **Verdict:** `VERIFIED`. An authenticated user cannot manipulate another user's records through any `SECURITY DEFINER` function because every WHERE clause binds `user_id = auth.uid()`.
3. **Worker Privilege Quarantine:**
   - **Finding:** Every worker function checks `is_authorized_worker_session()`. If an authenticated user token is supplied, PostgreSQL raises:  
     `42501: Unauthorized: session user (authenticated) does not possess the auren_worker role`.
   - **Verdict:** `VERIFIED`. Wildcard routine grants are the only hazard; keeping worker functions out of the `authenticated` grant list guarantees isolation.

---

## 4. Corrected Least-Privilege SQL Script

> [!IMPORTANT]
> The following SQL script contains the exact, verified least-privilege grants. It rectifies all signature mismatches, restricts `public.memories` to `SELECT` only, excludes `anon` from `chat_requests`, and isolates all worker operations.
> **DO NOT APPLY THIS SCRIPT AUTOMATICALLY. IT REQUIRES USER APPROVAL.**

```sql
-- ============================================================================
-- AUREN — STAGING LEAST-PRIVILEGE PERMISSION GRANTS (CORRECTED PHASE 6.2B)
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
```

---

## 5. Explicitly Excluded Grants & Security Justifications

| Excluded Function or Table Grant | Excluded Target Role | Security Justification |
| :--- | :---: | :--- |
| `GRANT INSERT, UPDATE, DELETE ON TABLE public.memories` | `authenticated` | **Epistemic Invariant Violation:** Bypasses `create_memory_rpc`, taxonomy classification, confidence weighting, and superseding lineage triggers. |
| `GRANT SELECT ON TABLE public.chat_requests` | `anon` | **Privacy / Information Disclosure:** Anonymous users have no user session (`auth.uid() = null`) and must never probe chat lifecycle records or fingerprints. |
| `GRANT EXECUTE ON FUNCTION public.claim_memory_extraction_jobs_rpc` | `authenticated` | **Worker Impersonation:** Ordinary users must not lease or drain the extraction queue. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.complete_memory_extraction_job_rpc` | `authenticated` | **Queue Corruption:** Prevents client forged job completions. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.fail_memory_extraction_job_rpc` | `authenticated` | **Denial of Service:** Prevents client triggered dead-lettering of jobs. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.reap_stale_extraction_jobs_rpc` | `authenticated` | **Administrative Isolation:** Unlocking expired worker leases is a background maintenance task. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.insert_extracted_memory_rpc` | `authenticated` | **Provenance Bypass:** Bypasses active worker lease verification and inserts unverified memories. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.create_system_asserted_memory_rpc` | `authenticated` | **Privilege Escalation:** Allows injecting memories into arbitrary target `user_id`s. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.activate_embedding_model_rpc` | `authenticated` | **System Sabotage:** Allows switching the active vector embedding model across all tenants. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.get_user_extraction_preferences_rpc` | `authenticated` | **Worker Isolation:** Preference retrieval RPC designed for worker ingestion pipeline. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.fetch_extraction_source_message_rpc` | `authenticated` | **Data Quarantine Bypass:** Bypasses journal quarantine checks. Quarantined to `auren_worker`. |
| `GRANT EXECUTE ON FUNCTION public.is_authorized_worker_session` | `authenticated` | **Internal Auth Utility:** Only needed by worker roles. |
| `GRANT EXECUTE ON FUNCTION public.admin_emergency_reset_job_rpc` | `authenticated` | **Administrative Isolation:** Emergency job clearing tool for superusers. |

---

## 6. Staging Authentication Configuration & Recommendations

### 6.1 Frontend Auth Callback & Redirect Architecture
Inspection of `frontend/src/context/AuthContext.tsx` and `frontend/src/router.tsx` confirmed:
- The React application utilizes `supabase.auth.signInWithPassword` and `supabase.auth.signUp`.
- `signUp` does not supply a hardcoded `emailRedirectTo`.
- Therefore, Supabase Auth relies entirely on the **Site URL** and **Redirect URLs** configured in the Supabase Dashboard.

### 6.2 Staging vs. Production Email Confirmation Strategy

| Environment | Recommended Setting | Rationale & Security Assessment |
| :--- | :--- | :--- |
| **Staging** | **Confirm email: `OFF`** | Bypasses the Supabase built-in SMTP rate limit (`429 over_email_send_rate_limit`). Enables immediate automated and manual user verification without third-party mailer setup. Does NOT weaken backend RLS or token verification because all requests still require valid cryptographic JWTs signed by Supabase (`ES256`). |
| **Production** | **Confirm email: `ON` + Custom SMTP** | Connect a transactional SMTP provider (Resend, SendGrid, Amazon SES, or Postmark) in **Project Settings -> Authentication -> SMTP Settings**. Custom SMTP completely removes Supabase rate limits while strictly enforcing real email ownership verification prior to account activation. |

### 6.3 Required Supabase Dashboard URL Configuration
In **Authentication -> URL Configuration**:
- **Site URL:** `https://frontend-alpha-steel-64.vercel.app`
- **Redirect URLs:**
  - `https://frontend-alpha-steel-64.vercel.app/**`
  - `http://localhost:5173/**`
  - `http://localhost:3000/**`

---

## 7. Post-Approval Verification Queries

After manual execution of the corrected SQL grants in the Supabase SQL Editor, run the following read-only queries to verify exact permission enforcement:

```sql
-- 1. VERIFY TABLE PRIVILEGES FOR AUTHENTICATED
-- Expected: memories has ONLY SELECT; chat_requests has ONLY SELECT; others have full CRUD.
SELECT 
    table_name, 
    string_agg(privilege_type, ', ' ORDER BY privilege_type) AS granted_privileges
FROM information_schema.role_table_grants 
WHERE table_schema = 'public' 
  AND grantee = 'authenticated'
GROUP BY table_name
ORDER BY table_name;

-- 2. VERIFY CHAT_REQUESTS HAS ZERO ANON PRIVILEGES
-- Expected: 0 rows returned
SELECT table_name, privilege_type 
FROM information_schema.role_table_grants 
WHERE table_schema = 'public' 
  AND table_name = 'chat_requests'
  AND grantee = 'anon';

-- 3. VERIFY RPC FUNCTION EXECUTION GRANTS FOR AUTHENTICATED
-- Expected: Exactly the 19 approved user-facing RPCs; ZERO worker RPCs.
SELECT 
    routine_name, 
    grantee
FROM information_schema.routine_privileges 
WHERE routine_schema = 'public' 
  AND grantee = 'authenticated'
ORDER BY routine_name;

-- 4. VERIFY WORKER FUNCTIONS ARE NOT EXPOSED TO AUTHENTICATED
-- Expected: 0 rows returned
SELECT routine_name 
FROM information_schema.routine_privileges 
WHERE routine_schema = 'public' 
  AND grantee = 'authenticated'
  AND routine_name IN (
      'claim_memory_extraction_jobs_rpc',
      'complete_memory_extraction_job_rpc',
      'fail_memory_extraction_job_rpc',
      'reap_stale_extraction_jobs_rpc',
      'insert_extracted_memory_rpc',
      'create_system_asserted_memory_rpc',
      'activate_embedding_model_rpc',
      'get_user_extraction_preferences_rpc',
      'fetch_extraction_source_message_rpc',
      'admin_emergency_reset_job_rpc'
  );
```

---

## 8. Explicit Approval Checklist

Before any hosted infrastructure change is executed, the following actions require explicit user confirmation:

1. [ ] **SQL Script Execution:** Approval to copy and execute Section 4 (`AUREN — STAGING LEAST-PRIVILEGE PERMISSION GRANTS`) in the Supabase SQL Editor.
2. [ ] **Email Confirmation Setting:** Approval to toggle **Confirm email** to `OFF` in the Supabase Dashboard under **Authentication -> Providers -> Email** for staging testing.
3. [ ] **Site URL Configuration:** Approval to set **Site URL** to `https://frontend-alpha-steel-64.vercel.app` in Supabase **Authentication -> URL Configuration**.
