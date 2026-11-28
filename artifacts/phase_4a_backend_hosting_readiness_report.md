# AUREN Phase 4A: Backend Hosting Readiness, Security & Deployment Planning

> [!IMPORTANT]
> **Status:** READ-ONLY Assessment Complete  
> **Repository:** `solomon476/AUREN-Personal-AI`  
> **Git Baseline:** Commit `0b3dea6d8b801649a699606df5d72f4fb76e2101` on branch `main` (fast-forward synchronized with `origin/main`)  
> **Assessment Date:** 17 November 2026  
> **Scope:** Strictly read-only investigation. No services deployed, no infrastructure modified, no secrets exposed.

---

## 1. Executive Summary

The AUREN frontend is successfully deployed to Vercel at `https://frontend-alpha-steel-64.vercel.app` with all Phase 3C routes returning HTTP 200 and 9/9 Playwright tests passing. However, the FastAPI backend has not yet been deployed to a public cloud host. As a consequence, all API-dependent user actions currently fail on the live website with `NetworkError` due to the client bundle falling back to `http://localhost:8000/api/v1`.

This assessment establishes the technical, architectural, security, and operational prerequisites for deploying the backend.

### Key Conclusions

1. **Architecture Portability:** The backend is built on FastAPI and uses a bifurcated runtime model:
   - **Interactive Web API:** Stateless ASGI process (`uvicorn app.main:app`) communicating with Supabase via PostgREST over asynchronous HTTP (`httpx.AsyncClient`). It enforces Row Level Security (RLS) dynamically using the caller's JWT bearer token.
   - **Asynchronous Memory Worker:** Standalone long-running daemon (`python -m app.services.memory.runner`) connecting to PostgreSQL via `asyncpg` connection pool under the dedicated login role `auren_worker_service`.
2. **Hosting Recommendation:** **Railway** is recommended as the primary hosting platform (with **Render** as secondary fallback). Railway supports both the Web API service and the Background Worker service within a single project, provides seamless GitHub autodeploy, natively streams Server-Sent Events (SSE) without proxy buffering or artificial timeouts, and operates within an estimated **\$5.00 – \$7.00 / month** budget.
3. **Pre-Deployment Code Corrections Required (Blockers):**
   - **Missing Dependencies:** `backend/pyproject.toml` is missing `asyncpg` and `google-genai>=3.0.0`; `backend/requirements.txt` is missing `asyncpg`. A cloud build relying on `pyproject.toml` or running the background worker will crash with `ModuleNotFoundError`.
   - **Attribute Bug in Reflection & Search Endpoints:** `backend/app/api/v1/search.py` (line 69) and `backend/app/api/v1/reflection.py` (lines 68, 80, 93, 113, 136, 159, 173) reference `user.user_id`, but `AuthenticatedUser` in `backend/app/models/user.py` only defines `id: UUID`. Calling these endpoints in production will raise an unhandled `AttributeError`.
   - **Missing Deployment Files:** The repository currently has zero container or PaaS deployment manifests (no `Dockerfile`, `Procfile`, `railway.toml`, or `render.yaml`).
4. **Security & RLS Readiness:**
   - Database operations for normal users strictly use PostgREST with the caller's bearer token. No service-role key is ever exposed or used for user requests.
   - The memory worker uses claim-token fencing (122-bit UUIDv4 tokens) and lease-based locking to prevent race conditions and re-ingestion.
   - **Critical Outstanding Requirement:** Five hosted Supabase RLS test cases in `backend/tests/test_supabase_rls_integration.py` remain skipped due to unconfigured test credentials. Local PostgreSQL tests mock `auth.uid()` and cannot substitute for live hosted verification.
5. **Frontend Rebuild Requirement:** Changing `VITE_API_BASE_URL` in Vercel requires a new frontend production build because Vite statically inlines `import.meta.env.*` expressions during compilation.

---

## 2. Verified Repository Baseline

| Property | Value | Verification Command / Source |
|---|---|---|
| **Local Branch** | `main` | `git branch --show-current` |
| **Local HEAD SHA** | `0b3dea6d8b801649a699606df5d72f4fb76e2101` | `git rev-parse HEAD` |
| **Remote Origin** | `origin/main` | `git rev-parse origin/main` |
| **Commit Parity** | Local matches remote exactly (0 commits ahead / behind) | `git status -uno` |
| **Tracked Working Tree** | Clean (`M frontend/vercel.json` committed in `0b3dea6`) | `git status --short` |
| **Python Version** | `>=3.12` specified in `pyproject.toml` (local venv is `3.14.8`) | [pyproject.toml](file:///home/kali/AUREN/backend/pyproject.toml#L9) |
| **Active Migrations** | 22 forward migrations (`001` through `022`) | [supabase/migrations/](file:///home/kali/AUREN/supabase/migrations/) |
| **Target Commit Match** | **CONFIRMED** — identical to `0b3dea6` | Verified |

---

## 3. Backend Architecture & Runtime Entry Points

### 3.1 Architectural Decomposition

The backend follows a layered domain-driven architecture:

```
                               ┌─────────────────────────────────────────┐
                               │       Vercel Production Frontend        │
                               │  https://frontend-alpha-steel-64.vercel.app  │
                               └────────────────────┬────────────────────┘
                                                    │ HTTPS + Bearer JWT
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   FASTAPI WEB SERVICE                                  │
│                             Entry Point: app.main:app (ASGI)                           │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                  API Routers                                     │  │
│  │  /api/v1/health       Service telemetry and health probe                         │  │
│  │  /api/v1/auth         Profile and token identity validation                      │  │
│  │  /api/v1/chat         Conversations, message history, SSE completions            │  │
│  │  /api/v1/memories     Memory lifecycle (confirm, correct, reject, archive)       │  │
│  │  /api/v1/tasks        Task management, status mutations, project links           │  │
│  │  /api/v1/projects     Project workspace and progress tracking                    │  │
│  │  /api/v1/goals        Strategic goals and milestones                             │  │
│  │  /api/v1/productivity Aggregated dashboard telemetry                             │  │
│  │  /api/v1/search       Omnisearch cross-entity lexical retrieval                  │  │
│  │  /api/v1/reflection   Contradiction detection, staleness, relationship graph      │  │
│  └────────────────────────────────────────┬─────────────────────────────────────────┘  │
│                                           │                                            │
│                     httpx.AsyncClient     │ PostgREST REST API                         │
│                     (Caller Bearer JWT)   │ apikey: SUPABASE_ANON_KEY                  │
└───────────────────────────────────────────┼────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 HOSTED SUPABASE PROJECT                                │
│                                                                                        │
│  ┌─────────────────────────┐    ┌───────────────────────────────────────────────────┐  │
│  │     Supabase Auth       │    │           PostgreSQL Database (PostgREST)         │  │
│  │   JWKS / JWT Issuance   │    │  • 22 Applied Migrations (RLS Active on all)      │  │
│  └─────────────────────────┘    │  • auth.uid() Enforced per user                   │  │
│                                 │  • SECURITY DEFINER RPCs for atomic operations    │  │
│                                 └─────────────────────────▲─────────────────────────┘  │
└───────────────────────────────────────────────────────────┼────────────────────────────┘
                                                            │
                                  Dedicated DB Pool (asyncpg)│ Direct TCP Connection
                                  User: auren_worker_service│ Port 5432 / 6543
                                                            │
┌───────────────────────────────────────────────────────────┼────────────────────────────┘
│                             MEMORY EXTRACTION WORKER SERVICE                           │
│                  Entry Point: python -m app.services.memory.runner                     │
│                                                                                        │
│  • Polls public.memory_extraction_jobs via claim_memory_extraction_jobs_rpc            │
│  • Fenced execution using 122-bit UUIDv4 claim tokens and 300s leases                  │
│  • LLM Extraction via Google Gemini (`gemini-2.5-flash`)                               │
│  • 768-dim Vector Embeddings via Google Gemini (`gemini-embedding-2`)                   │
│  • Epistemic Ingestion via insert_extracted_memory_rpc (chat_inferred, unconfirmed)    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Entry Points

1. **Web API Entry Point:** [backend/app/main.py](file:///home/kali/AUREN/backend/app/main.py#L24)
   - Application instance: `app = FastAPI(...)`
   - Production launch command:
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --no-access-log
     ```
2. **Background Worker Entry Point:** [backend/app/services/memory/runner.py](file:///home/kali/AUREN/backend/app/services/memory/runner.py#L358)
   - CLI execution:
     ```bash
     python -m app.services.memory.runner
     ```
   - Operates independently from `app.main:app`. Can run as a separate container or secondary service.

### 3.3 All Endpoints & HTTP Verbs

| Router Module | Prefix | Method | Path | Summary / Responsibility |
|---|---|---|---|---|
| [api/v1/health.py](file:///home/kali/AUREN/backend/app/api/v1/health.py#L12) | `/api/v1` | `GET` | `/health` | Service health probe (operational status, version, env) |
| [api/v1/auth.py](file:///home/kali/AUREN/backend/app/api/v1/auth.py#L22) | `/api/v1/auth` | `GET` | `/me` | Authenticated user profile identity |
| [api/v1/chat.py](file:///home/kali/AUREN/backend/app/api/v1/chat.py#L48) | `/api/v1/chat` | `POST` | `/completions` | Real-time SSE streaming chat with decoupled heartbeats |
| [api/v1/chat.py](file:///home/kali/AUREN/backend/app/api/v1/chat.py#L107) | `/api/v1/chat` | `GET` | `/conversations` | List user-owned conversation threads |
| [api/v1/chat.py](file:///home/kali/AUREN/backend/app/api/v1/chat.py#L143) | `/api/v1/chat` | `POST` | `/conversations` | Create a new conversation thread |
| [api/v1/chat.py](file:///home/kali/AUREN/backend/app/api/v1/chat.py#L175) | `/api/v1/chat` | `PATCH` | `/conversations/{id}` | Rename a conversation thread |
| [api/v1/chat.py](file:///home/kali/AUREN/backend/app/api/v1/chat.py#L210) | `/api/v1/chat` | `DELETE` | `/conversations/{id}` | Delete conversation and cascade messages |
| [api/v1/chat.py](file:///home/kali/AUREN/backend/app/api/v1/chat.py#L240) | `/api/v1/chat` | `GET` | `/conversations/{id}/messages` | Get chronological message history |
| [api/v1/chat.py](file:///home/kali/AUREN/backend/app/api/v1/chat.py#L282) | `/api/v1/chat` | `GET` | `/conversations/{id}/messages/{msg_id}/context` | Memory provenance injected into message |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L38) | `/api/v1/memories` | `GET` | `/` | List memories with status/category filters |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L65) | `/api/v1/memories` | `POST` | `/` | Create user direct asserted memory |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L93) | `/api/v1/memories` | `GET` | `/{id}` | Get specific memory details |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L119) | `/api/v1/memories` | `POST` | `/{id}/confirm` | Confirm an unconfirmed/inferred memory |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L145) | `/api/v1/memories` | `POST` | `/{id}/reject` | Reject an inaccurate memory |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L171) | `/api/v1/memories` | `POST` | `/{id}/correct` | Correct memory with supersession lineage |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L201) | `/api/v1/memories` | `POST` | `/{id}/archive` | Soft-delete / archive memory |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L227) | `/api/v1/memories` | `POST` | `/{id}/restore` | Restore archived memory to active |
| [api/v1/memories.py](file:///home/kali/AUREN/backend/app/api/v1/memories.py#L253) | `/api/v1/memories` | `POST` | `/{id}/outdated` | Mark memory outdated without superseding |
| [api/v1/tasks.py](file:///home/kali/AUREN/backend/app/api/v1/tasks.py#L31) | `/api/v1/tasks` | `POST` | `/` | Create task |
| [api/v1/tasks.py](file:///home/kali/AUREN/backend/app/api/v1/tasks.py#L55) | `/api/v1/tasks` | `GET` | `/` | List tasks (supports filtering) |
| [api/v1/tasks.py](file:///home/kali/AUREN/backend/app/api/v1/tasks.py#L85) | `/api/v1/tasks` | `GET` | `/{id}` | Get task details |
| [api/v1/tasks.py](file:///home/kali/AUREN/backend/app/api/v1/tasks.py#L109) | `/api/v1/tasks` | `PATCH` | `/{id}` | Update task fields |
| [api/v1/tasks.py](file:///home/kali/AUREN/backend/app/api/v1/tasks.py#L137) | `/api/v1/tasks` | `POST` | `/{id}/status` | Transition task status |
| [api/v1/tasks.py](file:///home/kali/AUREN/backend/app/api/v1/tasks.py#L165) | `/api/v1/tasks` | `DELETE` | `/{id}` | Delete task |
| [api/v1/projects.py](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L31) | `/api/v1/projects` | `POST` | `/` | Create project |
| [api/v1/projects.py](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L55) | `/api/v1/projects` | `GET` | `/` | List projects |
| [api/v1/projects.py](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L82) | `/api/v1/projects` | `GET` | `/{id}` | Get project details |
| [api/v1/projects.py](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L106) | `/api/v1/projects` | `PATCH` | `/{id}` | Update project fields |
| [api/v1/projects.py](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L134) | `/api/v1/projects` | `POST` | `/{id}/status` | Transition project status |
| [api/v1/projects.py](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L162) | `/api/v1/projects` | `DELETE` | `/{id}` | Delete project (optional cascade tasks) |
| [api/v1/goals.py](file:///home/kali/AUREN/backend/app/api/v1/goals.py#L31) | `/api/v1/goals` | `POST` | `/` | Create strategic goal |
| [api/v1/goals.py](file:///home/kali/AUREN/backend/app/api/v1/goals.py#L55) | `/api/v1/goals` | `GET` | `/` | List goals |
| [api/v1/goals.py](file:///home/kali/AUREN/backend/app/api/v1/goals.py#L82) | `/api/v1/goals` | `GET` | `/{id}` | Get goal details |
| [api/v1/goals.py](file:///home/kali/AUREN/backend/app/api/v1/goals.py#L106) | `/api/v1/goals` | `PATCH` | `/{id}` | Update goal fields |
| [api/v1/goals.py](file:///home/kali/AUREN/backend/app/api/v1/goals.py#L134) | `/api/v1/goals` | `POST` | `/{id}/status` | Transition goal status |
| [api/v1/goals.py](file:///home/kali/AUREN/backend/app/api/v1/goals.py#L162) | `/api/v1/goals` | `DELETE` | `/{id}` | Delete goal |
| [api/v1/productivity.py](file:///home/kali/AUREN/backend/app/api/v1/productivity.py#L34) | `/api/v1/productivity` | `GET` | `/dashboard` | Aggregated metrics, overdue items, upcoming tasks |
| [api/v1/productivity.py](file:///home/kali/AUREN/backend/app/api/v1/productivity.py#L65) | `/api/v1/productivity` | `GET` | `/context` | Productivity context injection for chat |
| [api/v1/search.py](file:///home/kali/AUREN/backend/app/api/v1/search.py#L37) | `/api/v1/search` | `GET` | `/` | Omnisearch cross-entity lexical search |
| [api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L55) | `/api/v1/reflection` | `GET` | `/insights` | Overview of contradictions and staleness |
| [api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L72) | `/api/v1/reflection` | `GET` | `/contradictions` | Contradiction findings list |
| [api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L84) | `/api/v1/reflection` | `GET` | `/staleness` | Staleness review list |
| [api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L97) | `/api/v1/reflection` | `GET` | `/relationships` | Record graph cross-entity links |
| [api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L122) | `/api/v1/reflection` | `POST` | `/links` | Create user-confirmed record link |
| [api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L148) | `/api/v1/reflection` | `GET` | `/links` | List record links for entity |
| [api/v1/reflection.py](file:///home/kali/AUREN/backend/app/api/v1/reflection.py#L162) | `/api/v1/reflection` | `DELETE` | `/links/{id}` | Delete user record link |

---

## 4. Production Deployment Requirements

### 4.1 Server & Protocol Requirements

- **ASGI Web Server:** `uvicorn` (version `>=0.30.0`), running under standard event loop with `httptools` and `websockets` (from `uvicorn[standard]`).
- **HTTP/2 & Keep-Alive:** Supported out-of-the-box.
- **Server-Sent Events (SSE) Protocol:**
  - Endpoint `/api/v1/chat/completions` streams with `Content-Type: text/event-stream`.
  - Disables reverse proxy response buffering via `X-Accel-Buffering: no` and `Cache-Control: no-cache`.
  - Sends explicit SSE heartbeats (`: heartbeat\n\n`) every `CHAT_STREAM_HEARTBEAT_SECONDS` (15.0s) to keep intermediate proxies and cloud gateways from closing idle HTTP connections.
  - Client disconnect is proactively monitored via `raw_request.is_disconnected()`. On disconnect, in-flight LLM streaming task is cancelled cleanly and partial output is persisted with status `interrupted`.
- **Request Timeouts:**
  - Default chat completion timeout: `CHAT_STREAM_TIMEOUT_SECONDS = 60`.
  - PostgREST HTTP client timeout: 10.0s.
  - Gemini SDK timeout: 60.0s.

### 4.2 Database & Storage Requirements

- **File Storage:** None. AUREN currently has zero dependencies on local disk storage or external object stores (S3, Cloud Storage). All state is stored in PostgreSQL.
- **Connection Model for Web API:** Stateless HTTP connection to Supabase PostgREST (`https://<project-ref>.supabase.co/rest/v1`). No TCP connection exhaustion or persistent database sockets held by the web server.
- **Connection Model for Memory Worker:** Requires direct PostgreSQL connection pool (`asyncpg.create_pool`).
  - Min connections: 1, Max connections: 3–5.
  - Dedicated role: `auren_worker_service` (with login, holding `auren_worker` permissions).
  - Transaction-mode PgBouncer caution: If connecting via Supabase port 6543 (transaction pooler), `asyncpg` prepared statements must be disabled (`statement_cache_size=0`). If connecting via port 5432 (direct/session), standard settings apply.

---

## 5. Complete Environment Variable Inventory

Every environment variable utilized by the backend is centralized in [backend/app/core/config.py](file:///home/kali/AUREN/backend/app/core/config.py).

> [!CAUTION]
> In accordance with safety restrictions, **NO secret values** are revealed below. Only variable names, descriptions, source locations, and security classifications are listed.

| Category | Variable Name | Purpose | Secret? | Default Value | Required in Prod? | Source File & Line |
|---|---|---|---|---|---|---|
| **Server** | `ENVIRONMENT` | Runtime environment classification (`development`, `staging`, `production`) | No | `"development"` | Yes (set to `production`) | [config.py#L164](file:///home/kali/AUREN/backend/app/core/config.py#L164) |
| **Server** | `HOST` | Bind address for uvicorn | No | `"0.0.0.0"` | Optional | [config.py#L165](file:///home/kali/AUREN/backend/app/core/config.py#L165) |
| **Server** | `PORT` | Bind port for uvicorn (standard PaaS injects this automatically) | No | `8000` | Optional (PaaS sets) | [config.py#L166](file:///home/kali/AUREN/backend/app/core/config.py#L166) |
| **Server** | `CORS_ORIGINS` | Permitted browser origins (JSON string array in env) | No | `["http://localhost:5173", ...]` | **YES (Must include Vercel domain)** | [config.py#L167](file:///home/kali/AUREN/backend/app/core/config.py#L167) |
| **Auth** | `SUPABASE_URL` | Base HTTPS URL of hosted Supabase project | No | `None` | **YES** | [config.py#L174](file:///home/kali/AUREN/backend/app/core/config.py#L174) |
| **Auth** | `SUPABASE_ANON_KEY` | Public Supabase anon client key | No (Public client key) | `None` | **YES** | [config.py#L175](file:///home/kali/AUREN/backend/app/core/config.py#L175) |
| **Auth** | `SUPABASE_JWT_SECRET` | Supabase JWT Secret for offline HS256 signature verification | **YES** | `None` | Optional if JWKS URL works; **Recommended** | [config.py#L176](file:///home/kali/AUREN/backend/app/core/config.py#L176) |
| **Auth** | `SUPABASE_JWKS_URL` | Asymmetric key endpoint (`.../auth/v1/.well-known/jwks.json`) | No | Derived from `SUPABASE_URL` | Optional | [config.py#L177](file:///home/kali/AUREN/backend/app/core/config.py#L177) |
| **AI / LLM** | `LLM_PROVIDER` | Active LLM adapter identifier (`gemini`) | No | `"gemini"` | Optional | [config.py#L180](file:///home/kali/AUREN/backend/app/core/config.py#L180) |
| **AI / LLM** | `LLM_API_KEY` | Google Gemini API key for chat completion | **YES** | `None` | **YES** | [config.py#L181](file:///home/kali/AUREN/backend/app/core/config.py#L181) |
| **AI / LLM** | `LLM_MODEL` | Google Gemini model identifier | No | `"gemini-2.5-flash"` | Optional | [config.py#L182](file:///home/kali/AUREN/backend/app/core/config.py#L182) |
| **Embedding** | `EMBEDDING_PROVIDER` | Active embedding provider adapter (`gemini`) | No | `"gemini"` | Optional | [config.py#L185](file:///home/kali/AUREN/backend/app/core/config.py#L185) |
| **Embedding** | `EMBEDDING_API_KEY` | Google Gemini API key for vector generation | **YES** | `None` (falls back to `LLM_API_KEY`) | Optional (if `LLM_API_KEY` set) | [config.py#L186](file:///home/kali/AUREN/backend/app/core/config.py#L186) |
| **Embedding** | `EMBEDDING_MODEL` | Active embedding model (must match dimension 768) | No | `"gemini-embedding-2"` | Optional | [config.py#L187](file:///home/kali/AUREN/backend/app/core/config.py#L187) |
| **Database** | `CHAT_REPOSITORY_TYPE`| Database adapter mode (`auto`, `supabase`, `sqlite`) | No | `"auto"` (resolves `supabase` when `SUPABASE_URL` set) | Optional | [config.py#L190](file:///home/kali/AUREN/backend/app/core/config.py#L190) |
| **Privacy** | `JOURNAL_HMAC_SECRET` | 256-bit cryptographic secret for signing/validating journal consent tokens | **YES** | `None` (Fail-closed; validates entropy & length `>=32`) | **YES (Mandatory fail-closed validator)** | [config.py#L210](file:///home/kali/AUREN/backend/app/core/config.py#L210) |
| **Worker** | `WORKER_DATABASE_URL`| PostgreSQL DSN for `auren_worker_service` direct connection | **YES** | `None` | **YES (for background memory worker)** | [config.py#L202](file:///home/kali/AUREN/backend/app/core/config.py#L202) |
| **Worker** | `MEMORY_WORKER_ENABLED`| Flag to toggle background extraction worker | No | `True` | Optional | [config.py#L203](file:///home/kali/AUREN/backend/app/core/config.py#L203) |
| **Worker** | `MEMORY_WORKER_POLL_INTERVAL_SECONDS` | Worker poll cycle sleep interval | No | `2.0` | Optional | [config.py#L204](file:///home/kali/AUREN/backend/app/core/config.py#L204) |
| **Worker** | `MEMORY_WORKER_BATCH_SIZE` | Max extraction jobs claimed per polling cycle | No | `5` | Optional | [config.py#L205](file:///home/kali/AUREN/backend/app/core/config.py#L205) |
| **Worker** | `MEMORY_WORKER_LEASE_SECONDS` | Lease hold duration for claimed extraction jobs | No | `300` | Optional | [config.py#L206](file:///home/kali/AUREN/backend/app/core/config.py#L206) |
| **Worker** | `MEMORY_WORKER_CONCURRENCY` | Concurrent in-flight extraction job tasks | No | `2` | Optional | [config.py#L207](file:///home/kali/AUREN/backend/app/core/config.py#L207) |

### 5.1 Critical Security Gate on `JOURNAL_HMAC_SECRET`

`JOURNAL_HMAC_SECRET` has an automated Pydantic model validator ([config.py#L216-L245](file:///home/kali/AUREN/backend/app/core/config.py#L216-L245)). When `ENVIRONMENT=production` or `staging`:
1. It **cannot** be empty or None (fails fast at application startup).
2. It **cannot** match known default or insecure test strings.
3. It **must** be at least 32 characters (256 bits).
4. It **must** pass Shannon entropy screening ($\ge 3.0$ bits/character).
5. It **must** have $\ge 12$ unique characters.
6. It **must not** contain $\ge 6$ consecutive ascending characters (`123456`, `abcdef`).

**Production Generation Command:**
```bash
openssl rand -hex 32
# or
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 6. Hosting Provider Assessment

| Evaluation Dimension | Railway (Recommended Primary) | Render (Secondary Fallback) | Fly.io (Alternative) |
|---|---|---|---|
| **FastAPI Compatibility** | Excellent. Automatic Nixpacks detection or custom Dockerfile. | Good. Native Python environment. | Good. Runs via Dockerfile. |
| **Multi-Service Project Model** | **Native.** Can run Web API and Worker as 2 services in 1 project sharing env vars. | Supported, but requires paid plan for background worker. | Supported via multiple machines in `fly.toml`. |
| **SSE Streaming Support** | **Full support.** Proxies honor chunked transfer and `X-Accel-Buffering: no` without buffering. | Supported on paid tiers; free tier proxies suffer idle disconnects. | **Full support.** Configurable idle timeouts and raw TCP/HTTP streaming. |
| **Process Availability & Sleep** | **Always-on.** No idle spin-down on hobby/paid tiers. | ⚠️ **Free tier sleeps** after 15 min inactivity ($50\text{s}+$ cold start). Paid tier (\$7/mo) stays awake. | **Configurable.** Can keep 1 machine running 24/7 or autostop. |
| **Background Worker Capability** | Supported seamlessly as a background worker process. | ⚠️ Background workers are **not available on free tier** (\$7/mo Starter required). | Supported as a separate process in `fly.toml`. |
| **Deployment Simplicity** | **Highest.** Connects to GitHub `main`, detects Python, automatic deployments on push. | High. Similar GitHub integration. | Medium. Requires `flyctl` CLI and custom `fly.toml`. |
| **Logging & Telemetry** | Built-in streaming real-time logs, CPU/RAM charts, deploy rollbacks. | Good basic log view. | Good CLI logs (`fly logs`) + Prometheus metrics. |
| **Monthly Cost (Personal Assistant)** | **\$5.00 – \$7.00 / month** (usage-based, covers Web API + Worker). | **\$14.00 / month** (\$7 Web + \$7 Worker; free tier unusable due to sleep & no worker). | **\$5.00 – \$8.00 / month** (two 512MB shared-cpu machines). |

### Technical & Financial Justification

- **Why Railway is Primary:**
  1. AUREN requires an **always-on** background worker to extract memories and process vectors asynchronously. Railway allows deploying both the FastAPI web server and the extraction worker within the exact same project, sharing environment variables.
  2. A personal AI assistant requires immediate responsiveness; Render's free tier 50-second cold start is completely unacceptable for live chat interactions.
  3. Railway's HTTP proxy natively supports streaming HTTP responses and SSE without truncating connections or buffering tokens.
  4. Cost efficiency: Railway charges strictly for allocated RAM/vCPU time (~$0.000231/GB-hr, ~$0.000463/vCPU-hr). Two lightweight 256MB–512MB containers cost ~$5–$7/month.

- **Why Render is Fallback:**
  Render is technically capable on its paid tier ($7 Starter Web + $7 Background Worker = $14/month), offering high stability and zero infrastructure management, but costs double Railway for a single-user workload.

---

## 7. Recommended Hosting Architecture

```
                                      ┌─────────────────────────────────────────┐
                                      │       Vercel Production Frontend        │
                                      │  https://frontend-alpha-steel-64.vercel.app  │
                                      └────────────────────┬────────────────────┘
                                                           │ HTTPS API Requests + SSE
                                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              RAILWAY PROJECT: "auren-backend"                          │
│                                                                                        │
│  ┌──────────────────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │         Service 1: auren-api (Web)           │  │   Service 2: auren-worker      │  │
│  │                                              │  │                                │  │
│  │ • Command: uvicorn app.main:app              │  │ • Command:                     │  │
│  │     --host 0.0.0.0 --port $PORT              │  │     python -m                  │  │
│  │ • Resources: 512MB RAM, 0.5 vCPU             │  │     app.services.memory.runner │  │
│  │ • Exposes Public HTTPS Domain                │  │ • Resources: 256MB, 0.25 vCPU  │  │
│  │ • Healthcheck: /api/v1/health                │  │ • No public port exposed       │  │
│  └──────────────────────┬───────────────────────┘  └────────────────┬───────────────┘  │
│                         │                                           │                  │
└─────────────────────────┼───────────────────────────────────────────┼──────────────────┘
                          │ HTTPS PostgREST                           │ PostgreSQL TCP
                          │ (apikey + User Bearer JWT)                │ (auren_worker_service)
                          ▼                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                    HOSTED SUPABASE                                     │
│                         • PostgREST /rest/v1 (RLS Enforced)                            │
│                         • PostgreSQL Port 5432 / 6543                                  │
│                         • Auth & JWKS Endpoint                                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Supabase Security Assessment

### 8.1 Authentication & Authorization Verification

1. **JWT Verification Pathway:** [backend/app/core/security.py#L42-L135](file:///home/kali/AUREN/backend/app/core/security.py#L42-L135)
   - FastAPI dependency `get_current_user` extracts `Bearer <token>` from the HTTP `Authorization` header.
   - Dual-mode verification:
     - Primary: Asymmetric JWKS (`ES256`/`RS256`) fetched and cached from `SUPABASE_JWKS_URL` or `SUPABASE_URL/auth/v1/.well-known/jwks.json`.
     - Secondary: Symmetric `HS256` offline verification using `SUPABASE_JWT_SECRET`.
   - Validates audience (`audience="authenticated"`), expiry (`exp`), and ensures the `sub` claim is a valid UUID representing `user_id`.
2. **Service Role Isolation:**
   - The backend code **does not contain or require the Supabase `service_role` key** for any user API route.
   - All user data operations (chat, memory, tasks, projects, goals, search, reflection) query PostgREST using:
     ```python
     headers = {
         "apikey": settings.SUPABASE_ANON_KEY,
         "Authorization": f"Bearer {user.token}",
     }
     ```
   - This ensures PostgREST sets PostgreSQL session context `auth.uid() = user.id`. The backend cannot accidentally bypass RLS during normal operations.
3. **Database Role Privileges & Worker Security:**
   - Standard users execute under the `authenticated` role.
   - Table `chat_requests` has direct `INSERT`, `UPDATE`, and `DELETE` revoked from `authenticated` and `anon` ([migration 009, 010](file:///home/kali/AUREN/supabase/migrations/20261115000009_strict_lifecycle_matrix_and_exclusive_claim.sql)). All state mutations must occur through audited `SECURITY DEFINER` RPC functions (`claim_chat_request`, `complete_chat_request`, `fail_chat_request`).
   - The memory worker uses role `auren_worker_service` ([migration 017](file:///home/kali/AUREN/supabase/migrations/20261116000017_embedding_identity_lexical_fallback_and_worker_service.sql)), which inherits `auren_worker` (`NOLOGIN NOINHERIT`).
   - `auren_worker` has strictly bounded privileges: it can only execute worker RPCs (`claim_memory_extraction_jobs_rpc`, `insert_extracted_memory_rpc`, etc.) and cannot read raw journal entries.
4. **Journal Privacy Quarantine:**
   - Messages flagged with `contains_journal_data = true` or using journal consent tokens are quarantined by database trigger and RPC logic: **no memory extraction job is ever created** (zero retention guarantee).

---

## 9. Outstanding Hosted RLS Verification Requirements

> [!WARNING]
> **5 Hosted Supabase RLS Tests Currently Skipped**  
> Local tests in `test_postgresql_migrations_and_parity.py` execute against a temporary local PostgreSQL instance with mocked roles (`CREATE ROLE authenticated NOLOGIN`) and a synthetic `auth.uid()`. **They do not prove that the live hosted Supabase instance enforces RLS.**

### 9.1 The Five Skipped Test Cases

Located in [backend/tests/test_supabase_rls_integration.py](file:///home/kali/AUREN/backend/tests/test_supabase_rls_integration.py#L27):

```python
requires_live_supabase = pytest.mark.skipif(
    not (SUPABASE_URL and SUPABASE_ANON_KEY and USER_A_TOKEN and USER_B_TOKEN),
    reason="Live Supabase integration credentials not configured in environment."
)
```

| Test Function | Target Table / Resource | Specific Invariant Verified |
|---|---|---|
| `test_live_rls_isolation_tasks` (L72) | `public.tasks` | User A creates task, User B creates task. User A reading User B's task gets empty array (`[]`). User A updating or deleting User B's task affects 0 rows. Anonymous caller rejected with 401. |
| `test_live_rls_isolation_journal_entries` (L168) | `public.journal_entries` | Strict privacy isolation. User A journal entry is completely invisible to User B. Anonymous requests rejected. |
| `test_live_rls_isolation_conversations` (L196) | `public.conversations` | Conversation threads isolated between User A and User B. Cross-user reads and deletes denied by RLS. |
| `test_live_rls_isolation_messages` (L246) | `public.messages` | Messages strictly scoped to conversation and user. User A cannot read User B's messages or inject messages into User B's conversation. |
| `test_live_rls_isolation_chat_requests` (L311) | `public.chat_requests` & RPCs | Direct DML rejected by RLS. Claim exclusivity, fingerprint validation, and terminal state protection (`completed` cannot transition to `failed` or `retried`) enforced by database RPCs under live PostgREST. |

### 9.2 Acceptance Criteria & Required Evidence

To accept Supabase RLS as production-ready:
1. Two distinct test users (`User A` and `User B`) must be created in the target hosted Supabase Auth instance.
2. Valid session tokens (`SUPABASE_USER_A_TOKEN` and `SUPABASE_USER_B_TOKEN`), along with `SUPABASE_URL` and `SUPABASE_ANON_KEY`, must be supplied in a secure, non-committed test environment.
3. Run:
   ```bash
   pytest backend/tests/test_supabase_rls_integration.py -v
   ```
4. Output must show:
   ```
   5 passed, 0 skipped, 0 failed
   ```
5. A signed verification report capturing execution timestamps, HTTP status codes, and zero data leakage must be archived before opening production access.

---

## 10. Frontend Integration Requirements

### 10.1 Environment Variables Required on Vercel

When the backend is deployed, the following environment variable must be configured in the Vercel project settings:

```
VITE_API_BASE_URL=https://<your-railway-backend-domain>/api/v1
```

> [!IMPORTANT]
> **Vercel Rebuild Requirement:**  
> Vite statically replaces `import.meta.env.VITE_API_BASE_URL` with a literal string during `vite build`. Therefore, setting this environment variable in the Vercel dashboard **will not take effect until a new deployment build is triggered**. A simple cache purge or route refresh is insufficient.

### 10.2 Frontend Request Mechanics & Headers

1. **HTTP Client:** [frontend/src/api/client.ts](file:///home/kali/AUREN/frontend/src/api/client.ts#L29-L39)
   - Every API request checks `supabase.auth.getSession()`.
   - If a valid user session exists, it injects:
     ```
     Authorization: Bearer <session.access_token>
     Content-Type: application/json
     ```
2. **SSE Streaming Client:** [frontend/src/api/chat.ts](file:///home/kali/AUREN/frontend/src/api/chat.ts#L63-L162)
   - Uses `fetch` with `ReadableStream` reader (`getReader()`).
   - Sends:
     ```
     Accept: text/event-stream
     Authorization: Bearer <session.access_token>
     ```
   - Parses SSE chunks for events: `metadata`, `token`, `done`, `error`.
   - Automatically supports user cancellation via `AbortController` / `signal`.
3. **CORS Requirements:**
   - The backend `CORS_ORIGINS` must include:
     - `https://frontend-alpha-steel-64.vercel.app`
     - `https://frontend-solian-wolves.vercel.app`
     - `https://frontend-git-main-solian-wolves.vercel.app`
   - Permitted methods: `GET`, `POST`, `PATCH`, `DELETE`, `OPTIONS`.
   - Permitted headers: `Authorization`, `Content-Type`, `Accept`.
   - `allow_credentials=True`.

---

## 11. Estimated Operating Costs

Assumptions: Single-user personal AI assistant workload (~50–100 chat interactions/day, ~20–50 memory extractions/day, lightweight database usage).

| Service Component | Provider | Tier / Configuration | Monthly Cost | Notes |
|---|---|---|---|---|
| **Frontend Web Hosting** | Vercel | Hobby Tier | **\$0.00** | Free tier includes unlimited deployments, 100GB bandwidth, SSL. |
| **Database & Auth** | Supabase | Free Tier | **\$0.00** | Free tier includes 500MB PostgreSQL, 50,000 MAU, PostgREST API, 5GB egress. |
| **Backend Web API** | Railway | Usage-based (512MB RAM, 0.5 vCPU) | **\$3.50 – \$4.50** | Charged strictly on execution metrics (~$0.000231/GB-hr). |
| **Background Memory Worker** | Railway | Usage-based (256MB RAM, 0.2 vCPU) | **\$1.50 – \$2.50** | Continuous polling daemon. |
| **Chat LLM API** | Google Gemini | `gemini-2.5-flash` | **\$0.00 – \$1.50** | Free tier permits 15 RPM / 1,500 RPD. Paid rate: $0.075/1M input, $0.30/1M output. |
| **Embedding API** | Google Gemini | `gemini-embedding-2` | **\$0.00 – \$0.20** | 768-dim vectors. Negligible token consumption for personal memory. |
| **TOTAL ESTIMATED MONTHLY COST** | | | **\$5.00 – \$8.70 / month** | Highly economical; easily covered by Railway's standard plan. |

---

## 12. Deployment Risks & Mitigations

| Risk | Severity | Technical Description | Mitigation Strategy |
|---|---|---|---|
| **ModuleNotFoundError on deploy** | **BLOCKER** | `asyncpg` is missing from `requirements.txt` and `pyproject.toml`; `google-genai` is missing from `pyproject.toml`. | Add both to `pyproject.toml` and `asyncpg` to `requirements.txt` before deployment commit. |
| **AttributeError in Reflection/Search** | **BLOCKER** | `search.py` and `reflection.py` access `user.user_id` which does not exist on `AuthenticatedUser` (only `user.id` exists). | Add `@property def user_id(self) -> UUID: return self.id` to `AuthenticatedUser` in `backend/app/models/user.py`. |
| **Premature SSE Connection Closure** | High | Proxies or load balancers drop long-lived HTTP streams after 30–60s of silence. | Decoupled 15s heartbeats (`: heartbeat\n\n`) are already implemented in `chat_service.py` to keep connections active. |
| **CORS Preflight Failure** | High | Browser blocks API calls if production Vercel domain is not explicitly in `CORS_ORIGINS`. | Configure `CORS_ORIGINS` in Railway environment to include all Vercel production and preview domains. |
| **Worker Database Role Rejection** | Medium | `WORKER_DATABASE_URL` attempting to connect directly as `auren_worker` will fail because it is `NOLOGIN`. | Connect as `auren_worker_service` (migration 017), which has login privileges and inherits `auren_worker`. |
| **PgBouncer Prepared Statement Error** | Medium | `asyncpg` prepared statements fail if connected to Supabase transaction pooler (port 6543). | Connect to direct port 5432, or set `statement_cache_size=0` if using pooler port 6543. |
| **Journal HMAC Secret Validation Failure** | High | Backend startup crashes if `JOURNAL_HMAC_SECRET` is $<32$ characters, low entropy, or a default string. | Generate using `openssl rand -hex 32` and set securely in Railway dashboard. |

---

## 13. Prioritized Deployment Checklist

### Phase 1: Pre-Deployment Source Corrections (Immediate Prerequisite)
- [ ] Add `asyncpg>=0.29.0` to `backend/requirements.txt`.
- [ ] Add `asyncpg>=0.29.0` and `google-genai>=3.0.0` to `backend/pyproject.toml`.
- [ ] Add `user_id` property alias to `AuthenticatedUser` in `backend/app/models/user.py` (`@property def user_id(self) -> UUID: return self.id`).
- [ ] Create `Procfile` or `railway.toml` defining the web and worker processes.
- [ ] Run full local test suite to confirm zero regressions.

### Phase 2: Infrastructure Provisioning (Authorized Milestone)
- [ ] Create a Railway project named `auren-production`.
- [ ] Add Web Service (`auren-api`):
  - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
  - Health check path: `/api/v1/health`
- [ ] Add Worker Service (`auren-worker`):
  - Start command: `python -m app.services.memory.runner`
  - No public domain attached.

### Phase 3: Environment Variable & Secret Injection
- [ ] Set `ENVIRONMENT=production`.
- [ ] Set `CORS_ORIGINS=["https://frontend-alpha-steel-64.vercel.app","https://frontend-solian-wolves.vercel.app"]`.
- [ ] Set `SUPABASE_URL` and `SUPABASE_ANON_KEY`.
- [ ] Set `SUPABASE_JWT_SECRET`.
- [ ] Set `LLM_API_KEY` (Gemini API key).
- [ ] Set `JOURNAL_HMAC_SECRET` (generated via `openssl rand -hex 32`).
- [ ] Set `WORKER_DATABASE_URL` (Postgres DSN with `auren_worker_service`).

### Phase 4: Hosted Security & RLS Verification
- [ ] Populate `SUPABASE_USER_A_TOKEN` and `SUPABASE_USER_B_TOKEN` in temporary test environment.
- [ ] Run `pytest backend/tests/test_supabase_rls_integration.py -v`.
- [ ] Verify all 5 hosted RLS tests pass.

### Phase 5: Frontend Integration & Verification
- [ ] Update `VITE_API_BASE_URL` in Vercel project settings to `https://<railway-domain>/api/v1`.
- [ ] Trigger Vercel frontend redeploy.
- [ ] Run automated E2E browser tests against the live deployment to confirm chat streaming, task creation, memory exploration, and reflection.

---

## 14. Explicit Blockers & Unresolved Decisions

### Explicit Blockers
1. **Missing Dependencies in Package Config:** `asyncpg` and `google-genai` are absent from `pyproject.toml` / `requirements.txt`.
2. **Missing `user_id` Property in `AuthenticatedUser`:** Reflection and search API endpoints will crash with `AttributeError` when authenticated requests arrive.
3. **No PaaS Deployment Manifests:** No `Procfile` or `railway.toml` exists in the repository.
4. **Skipped Hosted RLS Tests:** Cannot certify multi-user database security until the 5 live Supabase RLS tests pass against the target hosted project.

### Unresolved Architectural Decisions
1. **Supabase Connection Topology for Worker:** Whether the worker should connect to Supabase port 5432 (direct session) or port 6543 (transaction pooler). If connecting via 6543, `statement_cache_size=0` must be added to `asyncpg.create_pool` in `runner.py`.
2. **Dedicated Worker Service vs Single Process:** Whether to run the background worker as a separate container service on Railway (recommended for process isolation) or launch it as an `asyncio` background task within the FastAPI lifespan. Running it as a separate service is more resilient, but consumes slightly more memory.

---

*Report generated: 2026-11-17 · Commit: `0b3dea6` · Conversation: `b7cea535-b917-4f28-9c42-2a03574d18ce`*
