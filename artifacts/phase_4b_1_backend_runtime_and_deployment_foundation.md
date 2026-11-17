# AUREN Phase 4B.1: Backend Runtime Corrections & Deployment Foundation

> [!IMPORTANT]
> **Status:** Implementation Verified & Tested Locally ✅  
> **Repository:** `solomon476/AUREN-Personal-AI`  
> **Baseline Commit:** `0b3dea6d8b801649a699606df5d72f4fb76e2101`  
> **Implementation Date:** 17 November 2026  
> **Scope:** Runtime defect fixes, dependency declarations, deployment manifests, regression testing, and staging RLS planning. No cloud resources created, no migrations run, no commits pushed.

---

## 1. Verified Baseline

| Property | Value | Verification Source |
|---|---|---|
| **Branch** | `main` | `git branch --show-current` |
| **Baseline Commit SHA** | `0b3dea6d8b801649a699606df5d72f4fb76e2101` | `git rev-parse HEAD` |
| **Remote Tracking** | `origin/main` at `0b3dea6d8b801649a699606df5d72f4fb76e2101` | `git rev-parse origin/main` |
| **Initial Working Tree** | Clean on tracked files | `git status --short` |
| **Python Environment** | Python 3.14.8 (`>=3.12` required by `pyproject.toml`) | `.venv/bin/python3 --version` |

---

## 2. Actual Root Causes of Identified Defects

### 2.1 Missing Runtime Dependency Declarations

- **`asyncpg`:**
  - *Root Cause:* While the interactive FastAPI web API communicates with Supabase exclusively via PostgREST HTTP REST endpoints (`httpx.AsyncClient`), the asynchronous background worker ([backend/app/services/memory/runner.py](file:///home/kali/AUREN/backend/app/services/memory/runner.py#L10)) has a hard top-level import `import asyncpg` and connects directly to PostgreSQL via `asyncpg.create_pool` (lines 92–96). Furthermore, the PostgreSQL migration integrity test suite ([backend/tests/test_memory_database.py](file:///home/kali/AUREN/backend/tests/test_memory_database.py)) imports `asyncpg`.
  - *Impact:* While `asyncpg` was installed in the local developer virtual environment, it was missing from both [backend/requirements.txt](file:///home/kali/AUREN/backend/requirements.txt) and [backend/pyproject.toml](file:///home/kali/AUREN/backend/pyproject.toml). Any clean container build or deployment attempting to run the memory worker would immediately crash with `ModuleNotFoundError: No module named 'asyncpg'`.
- **`google-genai`:**
  - *Root Cause:* Google Gemini adapters ([backend/app/services/llm/gemini.py](file:///home/kali/AUREN/backend/app/services/llm/gemini.py#L37) and [backend/app/services/embeddings/gemini.py](file:///home/kali/AUREN/backend/app/services/embeddings/gemini.py#L53)) dynamically import `from google import genai` and `from google.genai import types`.
  - *Impact:* `google-genai>=3.0.0` was present in `requirements.txt` but was omitted from [backend/pyproject.toml](file:///home/kali/AUREN/backend/pyproject.toml). Build systems relying on PEP 517/518 (`pip install .`) failed to install the Google GenAI SDK.

### 2.2 Inconsistent Authenticated-User Attribute Access

- *Root Cause:*
  - In [backend/app/models/user.py](file:///home/kali/AUREN/backend/app/models/user.py#L10), the canonical domain model is defined as:
    ```python
    class AuthenticatedUser(BaseModel):
        id: UUID = Field(..., description="Unique Supabase Auth User ID (sub claim)")
        email: Optional[str] = None
        role: str = "authenticated"
        token: Optional[str] = None
        app_metadata: Dict[str, Any] = Field(default_factory=dict)
        user_metadata: Dict[str, Any] = Field(default_factory=dict)
    ```
  - Eight out of ten API routers (`auth.py`, `chat.py`, `memories.py`, `tasks.py`, `projects.py`, `goals.py`, `productivity.py`) correctly access `user.id` or `current_user.id`.
  - However, in [backend/app/api/v1/search.py](file:///home/kali/AUREN/backend/app/api/v1/search.py#L69) and [backend/app/api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L68), the author referenced `user.user_id` across 8 call sites.
  - Existing tests for search and reflection invoked service classes directly with synthetic UUIDs and never called the FastAPI HTTP routes via `TestClient`. Consequently, this bug was hidden during unit testing.
  - *Impact:* Any authenticated browser call to `/api/v1/search` or `/api/v1/reflection/*` in production would crash with `AttributeError: 'AuthenticatedUser' object has no attribute 'user_id'`.

### 2.3 Absence of Deployment Manifests

- *Root Cause:* The repository was developed as a monorepo with `frontend/` and `backend/` subdirectories, but contained zero PaaS manifests (`Procfile`, `railway.toml`).
- *Impact:* PaaS platforms (Railway, Render) cannot automatically deduce how to start both the Web API service and the background Memory Worker service.

---

## 3. Dependency Decisions & Justifications

| Package | Constraint | Added To | Technical Justification |
|---|---|---|---|
| **`asyncpg`** | `>=0.29.0` | `requirements.txt` & `pyproject.toml` | **Required.** Native PostgreSQL asynchronous connection pool used by `MemoryExtractionWorker` and `WorkerRunner` ([runner.py#L92](file:///home/kali/AUREN/backend/app/services/memory/runner.py#L92)) for atomic job claiming, 122-bit UUIDv4 token fencing, and vector ingestion. Installed version in verified venv is `0.32.0`. |
| **`google-genai`** | `>=3.0.0` | `pyproject.toml` (already in `requirements.txt`) | **Required.** Official Google GenAI SDK used for chat generation (`gemini-2.5-flash`) and vector embeddings (`gemini-embedding-2`). Missing from `pyproject.toml` dependencies block. Installed version in verified venv is `3.3.0`. |

**Clean Environment Verification:**
`pip check` executed against the virtual environment returned:
```
No broken requirements found.
```

---

## 4. Authenticated-User Interface Canonicalization

### 4.1 Canonical Definition

The canonical attribute representing the unique user identifier throughout the AUREN platform is **`user.id`** (representing the Supabase Auth `sub` claim UUID).

### 4.2 Code Changes Applied

1. **Source Call Sites Updated to Canonical `user.id`:**
   - [backend/app/api/v1/search.py#L69](file:///home/kali/AUREN/backend/app/api/v1/search.py#L69):
     `user_id=user.id` (was `user.user_id`)
   - [backend/app/api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py):
     - Line 68 (`get_insights`): `user.id` (was `user.user_id`)
     - Line 80 (`get_contradictions`): `user.id` (was `user.user_id`)
     - Line 93 (`get_staleness`): `user.id` (was `user.user_id`)
     - Line 113 (`get_relationships`): `user.id` (was `user.user_id`)
     - Line 136 (`create_link`): `user.id` (was `user.user_id`)
     - Line 159 (`list_links`): `user.id` (was `user.user_id`)
     - Line 173 (`delete_link`): `user.id` (was `user.user_id`)
2. **Compatibility Property Added to Model:**
   In [backend/app/models/user.py#L18-L21](file:///home/kali/AUREN/backend/app/models/user.py#L18-L21):
   ```python
   @property
   def user_id(self) -> UUID:
       """Compatibility property aliasing the canonical id attribute (Supabase Auth sub UUID)."""
       return self.id
   ```
   *Architectural Rationale:* While all existing internal routers now use the canonical `user.id`, adding `@property def user_id` ensures defense-in-depth against third-party integrations, background workers, or future endpoints inadvertently expecting `user_id`.

---

## 5. Deployment Configuration Design (Railway)

AUREN requires two independently executable services sharing the same database:

### 5.1 Service A — Web API (`auren-api`)

- **Role:** Public HTTP API gateway and real-time SSE streaming server.
- **Process Type:** Web Service (binds to public HTTP port).
- **Start Command:**
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}
  ```
- **Uvicorn Worker Concurrency Analysis:**
  - *Architectural Safety:* The FastAPI application is completely stateless: all user sessions, conversations, and messages are persisted in PostgreSQL via PostgREST. JWT tokens are verified offline or via cached JWKS. There are no shared in-memory dictionaries, stateful locks, or local singleton background threads in `app.main:app`. Therefore, running multiple Uvicorn workers (`--workers 2`) is architecturally safe and race-free.
  - *Resource Sizing & Safety Recommendation:* In lightweight container environments (such as Railway's 512MB RAM tier), each Python process consumes ~70MB–100MB of resident memory. Because FastAPI is fully asynchronous (async/await I/O with `asyncio`), a single worker process (`--workers 1`) can effortlessly handle hundreds of concurrent SSE streaming connections with minimal memory overhead. Setting `--workers ${WEB_CONCURRENCY:-1}` safely defaults to 1 worker (leaving >400MB RAM for request buffers and the Python runtime) while allowing dynamic scaling via environment variable.
- **Configuration Details:**
  - Binds to `0.0.0.0` and respects platform `$PORT`.
  - Disables reverse proxy response buffering via `X-Accel-Buffering: no`.
  - Decoupled 15s heartbeats (`: heartbeat\n\n`) keep long-lived SSE connections active.
  - Health check path: `/api/v1/health` (HTTP 200).
  - Graceful shutdown handles SIGTERM cleanly within ASGI lifecycle.

### 5.2 Service B — Memory Extraction Worker (`auren-worker`)

- **Role:** Asynchronous background polling worker extracting persistent memories from completed dialogue.
- **Process Type:** Background Worker (private process; **no** public port exposed).
- **Start Command:**
  ```bash
  python -m app.services.memory.runner
  ```
- **Worker Concurrency & Competing Instance Analysis:**
  - *Database Concurrency Guarantees:* The database schema incorporates cryptographic claim-token fencing and exclusive lease management:
    - `claim_memory_extraction_jobs_rpc` uses atomic row locking with lease expiration (`FOR UPDATE SKIP LOCKED` semantics).
    - Each claimed job receives a fresh 122-bit UUIDv4 `claim_token` and an active lease expiration timestamp (`NOW() + lease_seconds`).
    - Stale worker protection: Completion/failure RPCs (`complete_memory_extraction_job_rpc`, `fail_memory_extraction_job_rpc`) verify the active lease and the exact `claim_token`. If an expired worker tries to finalize a job after another worker reclaimed it, the database strictly rejects the stale submission.
    - Epistemic ingestion deduplication: `insert_extracted_memory_rpc` checks for identical content before inserting.
  - *Single Instance Recommendation:* While multiple worker instances are concurrency-safe at the database level, running a single worker container instance with internal concurrency (`concurrency=2`, batch size 5) is optimal for a personal AI assistant. A single instance eliminates idle connection overhead and prevents unnecessary database pool contention.
- **Configuration Details:**
  - Continuously polls `public.memory_extraction_jobs` via `claim_memory_extraction_jobs_rpc`.
  - Concurrency: 2 in-flight extraction tasks; batch size: 5 jobs; lease duration: 300 seconds.
  - Security Boundary: Connects via direct PostgreSQL DSN as login role `auren_worker_service` (migration 017), which inherits `auren_worker` (`NOLOGIN NOINHERIT`). It cannot access raw journal entries.
  - Graceful shutdown: POSIX SIGINT/SIGTERM handlers wait up to 30s for active extraction tasks to finalize before closing the `asyncpg` pool.

### 5.3 Deployment Manifest Files Created

1. [backend/Procfile](file:///home/kali/AUREN/backend/Procfile) & [Procfile](file:///home/kali/AUREN/Procfile):
   ```
   web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}
   worker: python -m app.services.memory.runner
   ```
2. [backend/railway.toml](file:///home/kali/AUREN/backend/railway.toml) & [railway.toml](file:///home/kali/AUREN/railway.toml):
   ```toml
   [build]
   builder = "NIXPACKS"
   buildCommand = "pip install -r requirements.txt"

   [deploy]
   startCommand = "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"
   healthcheckPath = "/api/v1/health"
   healthcheckTimeout = 100
   restartPolicyType = "ON_FAILURE"
   restartPolicyMaxRetries = 10
   ```

---

## 6. Complete Environment Variable Inventory

> [!CAUTION]
> In accordance with mandatory restrictions, **NO secret values** are printed or committed. Only variable names, purposes, service scopes, and requirements are listed.

| Variable Name | Purpose | Secret? | Required By | Mandatory? | Default |
|---|---|---|---|---|---|
| `ENVIRONMENT` | Runtime classification (`production`, `staging`, `development`) | No | Both | Yes | `"development"` |
| `PORT` | Bind port for ASGI web server (injected by PaaS) | No | Web API | No | `8000` |
| `HOST` | Bind address for ASGI web server | No | Web API | No | `"0.0.0.0"` |
| `CORS_ORIGINS` | JSON list of permitted browser origins | No | Web API | **Yes** | `["http://localhost:5173", ...]` |
| `SUPABASE_URL` | Base HTTPS URL of hosted Supabase project | No | Both | **Yes** | `None` |
| `SUPABASE_ANON_KEY` | Public Supabase anon client key | No (Public) | Web API | **Yes** | `None` |
| `SUPABASE_JWT_SECRET` | Supabase JWT Secret for offline HS256 verification | **Yes** | Web API | Recommended | `None` |
| `SUPABASE_JWKS_URL` | Optional asymmetric JWKS URL | No | Web API | No | Derived from `SUPABASE_URL` |
| `LLM_PROVIDER` | LLM provider adapter name | No | Both | No | `"gemini"` |
| `LLM_API_KEY` | Google Gemini API key for completions and extraction | **Yes** | Both | **Yes** | `None` |
| `LLM_MODEL` | Gemini chat model | No | Both | No | `"gemini-2.5-flash"` |
| `EMBEDDING_PROVIDER` | Embedding provider adapter name | No | Worker | No | `"gemini"` |
| `EMBEDDING_API_KEY` | Google Gemini API key for vector generation | **Yes** | Worker | No | Falls back to `LLM_API_KEY` |
| `EMBEDDING_MODEL` | Active embedding model (dimension 768) | No | Worker | No | `"gemini-embedding-2"` |
| `JOURNAL_HMAC_SECRET` | 256-bit secret for signing/validating consent tokens | **Yes** | Web API | **Yes (Fail-closed; $\ge 32$ chars, high entropy)** | `None` |
| `WORKER_DATABASE_URL` | Direct Postgres DSN for `auren_worker_service` | **Yes** | Worker | **Yes** | `None` |
| `MEMORY_WORKER_ENABLED` | Toggles memory extraction worker execution | No | Worker | No | `True` |
| `MEMORY_WORKER_POLL_INTERVAL_SECONDS` | Poll sleep duration | No | Worker | No | `2.0` |
| `MEMORY_WORKER_BATCH_SIZE` | Max extraction jobs claimed per cycle | No | Worker | No | `5` |
| `MEMORY_WORKER_LEASE_SECONDS` | Job claim lease hold duration | No | Worker | No | `300` |
| `MEMORY_WORKER_CONCURRENCY` | Concurrent worker extraction tasks | No | Worker | No | `2` |

---

## 7. CORS Assessment

### 7.1 Verified Frontend Origins

From Phase 3C deployment verification and Vercel inspect:
- **Verified Production Deployment:** `https://frontend-alpha-steel-64.vercel.app`
- **Team Production Alias:** `https://frontend-solian-wolves.vercel.app`
- **Git Branch Alias:** `https://frontend-git-main-solian-wolves.vercel.app`
- **Local Development Origins:** `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`

### 7.2 CORS Enforcement Rules

1. **Credentials Support:** Because the frontend sends session tokens and cookies, the backend middleware specifies `allow_credentials=True`. Under browser security specifications (W3C CORS), wildcard origin `*` is **strictly disallowed** when credentials are enabled.
2. **Explicit Allowed Origins:** In production, `CORS_ORIGINS` must be explicitly configured as:
   ```json
   ["https://frontend-alpha-steel-64.vercel.app", "https://frontend-solian-wolves.vercel.app", "https://frontend-git-main-solian-wolves.vercel.app"]
   ```
3. **Preflight Testing:** Verified in [backend/tests/test_deployment_startup.py#L29-L50](file:///home/kali/AUREN/backend/tests/test_deployment_startup.py#L29-L50): requests with permitted origins receive matching `access-control-allow-origin`, while untrusted origins (`https://malicious-site.example.com`) are rejected without access-control headers.

---

## 8. Testing Results

### 8.1 Automated Test Execution Summary

Executed command:
```bash
cd /home/kali/AUREN/backend && .venv/bin/pytest -v
```

```
======================= 307 passed, 5 skipped in 41.64s ========================
```

- **Total Test Cases Collected:** 312
- **Passed:** **307**
- **Failed:** **0**
- **Skipped:** **5** (the 5 live hosted Supabase RLS tests; see Section 9)

### 8.2 New Tests Added in This Milestone

Two dedicated test suites were implemented:

1. [backend/tests/test_search_and_reflection_api.py](file:///home/kali/AUREN/backend/tests/test_search_and_reflection_api.py) (6 tests):
   - `test_authenticated_user_property_parity`: Verifies `u.id == u.user_id` on `AuthenticatedUser`.
   - `test_search_endpoint_unauthenticated_rejected`: HTTP 401 on unauthenticated `/api/v1/search`.
   - `test_reflection_endpoints_unauthenticated_rejected`: HTTP 401 across all reflection endpoints.
   - `test_search_endpoint_authenticated_user_propagation`: Verifies `/api/v1/search` runs without `AttributeError` and passes `user.id` to `OmnisearchService.search`.
   - `test_reflection_endpoints_authenticated_user_propagation`: Verifies `/insights`, `/contradictions`, `/staleness`, and `/relationships` pass `user.id` to `ReflectionService`.
   - `test_user_identity_isolation_and_no_substitution`: Verifies User A cannot spoof User B by query parameter or header injection.
2. [backend/tests/test_deployment_startup.py](file:///home/kali/AUREN/backend/tests/test_deployment_startup.py) (6 tests):
   - `test_api_startup_and_health`: FastAPI ASGI app initialization and `/health` probe.
   - `test_cors_origin_policy`: Origin whitelisting and foreign origin rejection.
   - `test_worker_startup_rejects_nologin_role`: Verifies `WorkerRunner` rejects `auren_worker` in `WORKER_DATABASE_URL`.
   - `test_worker_startup_requires_database_url_when_no_pool`: Fail-fast when no DSN or pool provided.
   - `test_worker_startup_disabled_flag`: Clean bypass when `MEMORY_WORKER_ENABLED=false`.
   - `test_deployment_configuration_files_exist`: Structural validation of `Procfile` and `railway.toml`.

---

## 9. Tests Skipped & Reasons

The only skipped tests in the entire suite are the five hosted Supabase RLS tests in [backend/tests/test_supabase_rls_integration.py](file:///home/kali/AUREN/backend/tests/test_supabase_rls_integration.py#L27):

```python
requires_live_supabase = pytest.mark.skipif(
    not (SUPABASE_URL and SUPABASE_ANON_KEY and USER_A_TOKEN and USER_B_TOKEN),
    reason="Live Supabase integration credentials not configured in environment."
)
```

1. `test_live_rls_isolation_tasks` (Line 72)
2. `test_live_rls_isolation_journal_entries` (Line 168)
3. `test_live_rls_isolation_conversations` (Line 196)
4. `test_live_rls_isolation_messages` (Line 246)
5. `test_live_rls_isolation_chat_requests` (Line 311)

**Reason for Skip:** These tests are strictly designed to run against a live hosted Supabase project and require real authenticated user sessions (`USER_A_TOKEN` and `USER_B_TOKEN`). Per the mandatory restrictions of Phase 4B.1, remote test execution was not authorized.

---

## 10. Staging Supabase RLS Verification Plan

### 10.1 Test Implementation Analysis

1. **Do they create, modify, or delete records?**
   - **Yes.** User A and User B insert tasks, journal entries, conversations, messages, and initiate chat requests.
   - However, every test function wraps operations in a `try...finally` block that explicitly deletes created test records by exact UUID (`?id=eq.<uuid>`).
2. **Can they affect unrelated users?**
   - **No.** All inserts and queries are explicitly parameterized with random test UUIDs (`uuid.uuid4()`) and scoped strictly to the token of User A or User B. Unrelated records are never queried without filtering, modified, or deleted.
3. **Do they require two independent authenticated users?**
   - **Yes.** By definition, verifying multi-tenant isolation requires two valid user sessions (`User A` and `User B`) issued by Supabase Auth with distinct `sub` UUIDs.
4. **Do they assume a disposable database?**
   - **No**, because records are cleaned up via `finally` blocks. However, running against production is bad practice because immutable audit tables or incomplete error rollbacks could leave test artifacts.
5. **Can they safely run against a dedicated staging project?**
   - **Yes, absolutely.** Running against a staging Supabase project mirroring migrations 001–022 is the recommended, risk-free methodology.

### 10.2 Step-by-Step Staging Execution Procedure

1. **Target Environment Setup:**
   - Provision or select a dedicated Supabase staging project with migrations 001–022 applied.
   - Create two test users in Supabase Auth: `test_user_a@auren.local` and `test_user_b@auren.local`.
2. **Token Generation:**
   - Generate valid JWT session tokens for User A and User B via Supabase Auth API (`POST /auth/v1/token?grant_type=password`).
3. **Execution Command:**
   ```bash
   SUPABASE_URL="https://<staging-ref>.supabase.co" \
   SUPABASE_ANON_KEY="<staging-anon-key>" \
   SUPABASE_USER_A_TOKEN="<user-a-jwt>" \
   SUPABASE_USER_B_TOKEN="<user-b-jwt>" \
   pytest backend/tests/test_supabase_rls_integration.py -v
   ```
4. **Acceptance Criteria:**
   - All 5 test cases must report `PASSED`.
   - Zero skips, zero failures.
   - Evidence log must be captured and reviewed prior to production deployment.

---

## 11. Security Implications

1. **Zero Secret Leakage:** No credentials, API keys, database passwords, or JWT secrets were printed, exposed, or committed to Git.
2. **Role Boundaries Maintained:**
   - The interactive web API continues to query PostgREST using only the caller's JWT bearer token. It has no access to the Supabase `service_role` key.
   - The memory worker connects using `auren_worker_service` and cannot log in as the `NOLOGIN` role `auren_worker`.
3. **Authorization Preserved:**
   - The fix to `search.py` and `reflection.py` strictly derives user identity from `get_current_user` (the cryptographically verified JWT `sub` claim).
   - Identity parameter injection attacks (e.g. `?user_id=<other_user>`) are completely ignored.

---

## 12. Remaining Deployment Blockers (Prior to Phase 4B.2)

1. **Execution of the 5 Hosted Supabase RLS Tests:** Multi-user data isolation on live PostgREST must be empirically proven by executing the staging plan.
2. **Railway Project Provisioning:** Railway project creation, service definition (`auren-api` and `auren-worker`), and environment variable population in the Railway dashboard.
3. **Frontend Variable Update:** After backend deployment, `VITE_API_BASE_URL` must be updated in Vercel project settings, followed by a frontend rebuild.

---

*Report generated: 2026-11-17 · Commit: `0b3dea6` · Conversation: `b7cea535-b917-4f28-9c42-2a03574d18ce`*
