# AUREN — Persistent Chat, Idempotency, and Streaming Reliability Architecture

This document details the architecture, persistence layers, idempotency guarantees, error distinction, and resilient streaming mechanisms implemented in Phase 3A.1 and Phase 3A.2.

---

## 1. Asynchronous Repository Architecture (`BaseChatRepository`)

AUREN separates repository interface contracts from backend persistence implementations. All chat, conversation, and lifecycle operations adhere to the asynchronous `BaseChatRepository` contract, preventing event-loop blocking.

```
                      ┌──────────────────────┐
                      │  BaseChatRepository  │
                      │   (Asynchronous)     │
                      └──────────┬───────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│  SupabasePostgresChatRepository │   │      SQLiteChatRepository       │
│  (Cloud Supabase PostgreSQL)    │   │  (Explicit Local-Dev / Offline) │
├─────────────────────────────────┤   ├─────────────────────────────────┤
│ • httpx.AsyncClient non-block   │   │ • Disk-backed SQLite (WAL mode) │
│ • Caller JWT Token (auth.uid)   │   │ • Enforces foreign keys         │
│ • Public anon key only          │   │ • Atomic SQLite transactions    │
│ • Enforces PostgreSQL RLS       │   │ • Survives process restarts     │
│ • NO service-role key used      │   │ • Async contract conformance    │
│ • Strict error categorization   │   │ • Zero cloud dependencies       │
└─────────────────────────────────┘   └─────────────────────────────────┘
```

### Selection Rules (`get_chat_repository`)

- **Production / Supabase Mode**: Selected when `CHAT_REPOSITORY_TYPE="supabase"` or when `CHAT_REPOSITORY_TYPE="auto"` with `SUPABASE_URL` and `SUPABASE_ANON_KEY` configured and caller JWT token provided.
- **Local Development / Offline Mode**: Explicitly designated fallback using `SQLiteChatRepository`. Guarantees local developers and test suites can run offline without hosted infrastructure.

---

## 2. Row Level Security & Cloud PostgREST Enforcement

`SupabasePostgresChatRepository` communicates directly with Supabase PostgREST (`/rest/v1`) using asynchronous non-blocking HTTP requests:

- **Caller Identity**: PostgREST requests include `Authorization: Bearer <user_jwt_token>` and `apikey: <anon_key>`.
- **Row Level Security**: PostgreSQL evaluates policies (`auth.uid() = user_id`) on all reads and writes across `conversations`, `messages`, and `chat_requests`.
- **Zero Service-Role Usage**: The privileged `service-role` key is strictly excluded from ordinary user operations.
- **Cross-Tenant Isolation**: Attempting to read or mutate another user's conversation returns an empty set or error as enforced by the database engine.

---

## 3. Strict Database Error Categorization

Supabase PostgREST responses are strictly categorized to avoid converting errors into false missing records:

| Scenario / Code | PostgREST Response | Repository Behavior | Client Safe Detail |
|---|---|---|---|
| Query with no matches | `200 OK` with `[]` | Returns `None` or `[]` | Normal 404 if item required |
| Invalid/expired JWT | `401 / 403` | Raises `DatabaseAuthError` | HTTP 503 "Database authentication error" |
| Network drop / timeout | `httpx.RequestError` | Raises `DatabaseConnectionError` | HTTP 503 "Database service temporarily unreachable" |
| Database 5xx error | `500 / 502 / 503` | Raises `DatabaseOperationError` | HTTP 500 "Database operation error" |

Full technical details (status code, endpoint, response payload) are recorded in server-side logs and never masked internally.

---

## 4. Atomic Idempotency Lifecycle & New-Conversation Race Resolution

### New-Conversation Race Resolution

When two identical requests arrive simultaneously without a supplied `conversation_id`:
1. `validate_and_resolve_conversation()` deterministically derives a conversation UUID bound to the user and idempotency key:
   $$\text{conversation\_id} = \text{uuid5}(\text{NAMESPACE\_OID}, \text{"auren:conv:"} + \text{user\_id} + \text{":"} + \text{idempotency\_key})$$
2. Calls `repo.get_or_create_conversation(user_id, deterministic_conv_id, title)`.
3. Both requests resolve to the **exact same** conversation ID.
4. Exactly **one** conversation is created; no orphan conversations are created.
5. `persist_user_message` uses the unique index `(user_id, idempotency_key)`, storing exactly **one** user message.
6. `claim_chat_request` is atomic, allowing only **one** request to claim `processing`.
7. The second request halts with `idempotency_in_flight` (or replays completed response).
8. The chat request, user message, and assistant response all belong to the same conversation.

### Lifecycle Table: `chat_requests`

```sql
CREATE TABLE IF NOT EXISTS public.chat_requests (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed', 'interrupted')),
    user_message_id UUID NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
    assistant_message_id UUID REFERENCES public.messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, idempotency_key)
);
```

---

## 5. Resilient Streaming & Non-Overwriting Lifecycle States

### Decoupled Producer-Consumer Architecture

```
┌─────────────────────────────────┐
│     AI Model stream_response    │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   Background Producer Task      │
│   (Puts tokens into Queue)      │
└────────────────┬────────────────┘
                 │
                 ▼
      ┌─────────────────────┐
      │    asyncio.Queue    │
      └──────────┬──────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│      Consumer Stream Loop       │
│  • Awaits queue.get() (15s)     │
│  • On timeout: emits heartbeat  │
│  • Producer is NEVER cancelled  │
│  • Enforces overall deadline    │
└─────────────────────────────────┘
```

1. **Undisturbed Model Generation**: Waiting for a heartbeat waits on `queue.get()`. A timeout cancels only the queue waiter, leaving `producer_task` running without interruption.
2. **Verified >15s Latency**: An automated test simulating a model taking 16 seconds to produce its first chunk verifies that the 15-second heartbeat is emitted and the stream proceeds to completion without interruption.

### Non-Overwriting Terminal Lifecycle States

The streaming runner explicitly tracks `terminal_state`:
- **Provider failure or timeout**: Sets `terminal_state = "failed"`. In `finally:`, even if partial tokens were generated, the request lifecycle record **remains `failed`** (never overwritten as `interrupted`).
- **Client disconnect**: Sets `terminal_state = "interrupted"`. Persists partial tokens with `metadata={"interrupted": True}` and sets status to `"interrupted"`.
- **Successful generation**: Sets `terminal_state = "completed"`. Persists full tokens and updates status to `"completed"`.

---

## 6. Frontend Stable Idempotency & Reconciliation

1. **Client-Side Generation**: When a user submits a prompt, `ChatView` assigns a stable `idempotencyKey = \`req-\${crypto.randomUUID()}\``.
2. **Optimistic Persistence**: The message is placed in local state with its stable idempotency key.
3. **Reconciliation & Retries**:
   - If an error occurs or the stream is interrupted, the UI displays a "Retry" button.
   - Retrying sends the **exact same** `idempotencyKey`.
   - If the backend already finished generation in the background before the disconnect, it instantly replays the completed response from cache with zero additional AI tokens consumed.
   - If the request was interrupted or failed, the backend cleanly retries.

---

## 7. Phase 3A.3 Retry Lifecycle & Concurrency Guarantees

### Explicit Handling for All Four States

| State | Backend Action | Assistant Message Handling | Provider Invocation |
|---|---|---|---|
| `completed` | Replays cached assistant message directly | Emits cached message; no duplicate records | 0 (cached) |
| `processing` | Returns `idempotency_in_flight` SSE error event | Untouched; prevents race with active worker | 0 (rejected) |
| `failed` | Atomic state transition `failed -> processing` | New assistant message created upon success | 1 (retried) |
| `interrupted` | Atomic state transition `interrupted -> processing` | Existing assistant message updated in-place (`update_assistant_message`) | 1 (recovered) |

### Key Invariants
1. **Atomic Conditional Transition**:
   - `transition_chat_request_status(user_id, idempotency_key, from_statuses=['failed', 'interrupted'], to_status='processing')`
   - In SQLite: `UPDATE chat_requests SET status = ? WHERE user_id = ? AND idempotency_key = ? AND status IN (?, ?)`
   - In Supabase PostgreSQL: PostgREST `PATCH /chat_requests?user_id=eq.{user_id}&idempotency_key=eq.{idempotency_key}&status=in.({from_statuses})`
   - Exactly one concurrent retry can succeed (row count = 1). Any other concurrent retry sees row count = 0 and is cleanly rejected as `idempotency_in_flight`.
2. **Assistant Message De-duplication on Interrupted Recovery**:
   - When recovering an `interrupted` request, `existing_req.assistant_message_id` is preserved.
   - Upon completion, `repo.update_assistant_message(user_id, message_id, content, metadata)` updates the existing message in-place rather than inserting a duplicate record.
   - As a result, the conversation history contains exactly one user message and one assistant message.
3. **SQLite Worker Thread Isolation**:
   - SQLite is maintained strictly as an isolated local-development adapter (`storage/dev_chat.db`).
   - All synchronous SQLite calls are offloaded via `asyncio.to_thread` to prevent blocking the asynchronous event loop.

---

## 8. Phase 3A.4 Request Fingerprint & Content Binding

To guarantee that an idempotency key strictly identifies one logical request and cannot be hijacked or reused with conflicting input:

### Fingerprint Formulation
```python
def compute_request_fingerprint(
    user_id: UUID,
    content: str,
    conversation_id: Optional[UUID] = None,
) -> str:
    normalized_content = "\n".join(line.rstrip() for line in content.strip().splitlines())
    conv_part = str(conversation_id) if conversation_id else "none"
    payload = f"user:{str(user_id)}|conv:{conv_part}|content:{normalized_content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

### Invariants:
1. **Binding**: The immutable fingerprint is stored in `chat_requests.request_fingerprint` upon claiming.
2. **Conflicting Reuse Rejection**: If an existing idempotency key is submitted with differing normalized content or conversation target:
   - Request is immediately rejected with HTTP 409 Conflict (or SSE `idempotency_conflict`).
   - The LLM is **never** invoked.
   - The original user message is **not** modified.
   - The original request lifecycle record is **not** altered.
3. **Identical Retries**: Requests with identical parameters yield the exact same fingerprint and proceed through standard replay or recovery.

---

## 9. Phase 3A.4 Persistence Failure Recovery & Reconciliation

### Scenario
1. The LLM finishes generating a response.
2. The assistant message is persisted to the database.
3. Updating the corresponding `chat_requests` record to `status = 'completed'` fails (e.g. database network error or constraint failure).
4. The client retries using the same idempotency key.

### Recovery Mechanism
- On retry, `chat_service` inspects `chat_requests`. If `status != 'completed'`:
  - It queries the database via `find_assistant_message_for_request(user_id, conversation_id, user_message_id)`.
  - If a completed assistant message already exists in that conversation matching that user request (identified via `user_message_id` and not marked `interrupted`):
    1. **Reconciles Lifecycle**: Updates `chat_requests` to `status = 'completed'` and sets `assistant_message_id`.
    2. **Replays Response**: Immediately streams the cached assistant response.
    3. **Zero Duplication**: Does not persist duplicate assistant or user messages.
    4. **Zero AI Cost**: Does not call `provider.stream_response` again.
    5. **No Deadlocks**: Prevents requests from becoming permanently stuck in `processing`.

---

## 10. Phase 3A.5 Database-Level Integrity & Least-Privilege RLS

### 1. Database-Level Trigger Protection
Application-level checks are reinforced with PostgreSQL and SQLite triggers executing on `BEFORE UPDATE`:
- **Fingerprint Immutability**: If `OLD.request_fingerprint IS NOT NULL`, any mutation or replacement raises an exception (`request_fingerprint is immutable and cannot be modified once set`).
- **Legacy Backfill Policy**: If `OLD.request_fingerprint IS NULL`, an initial assignment is permitted once to allow seamless migration of legacy records.
- **Ownership Protection**: `user_id` is immutable (`user_id is immutable and cannot be transferred`).
- **Status Machine Protection**: Requests with `status = 'completed'` cannot be transitioned out of completed status.
- **Structural Immutability**: `idempotency_key`, `conversation_id`, `user_message_id`, and `created_at` cannot be mutated.

### 2. Least-Privilege RLS Policies
The broad `FOR ALL` policy on `chat_requests` is replaced with operation-specific policies:
- `SELECT`: `auth.uid() = user_id`
- `INSERT`: `auth.uid() = user_id AND status = 'processing'`
- `UPDATE`: `auth.uid() = user_id AND status IN ('processing', 'completed', 'failed', 'interrupted')`
- `DELETE`: Direct `DELETE` privilege is revoked from `authenticated` and `anon`. Deletions can only occur via `ON DELETE CASCADE` from parent conversation threads.

---

## 11. Phase 3A.6 Security Definer RPCs & Direct Mutation Revocation

To address the security vulnerability where authenticated clients could invoke PostgREST directly (`PATCH /chat_requests`) to manipulate their own lifecycle status or inject arbitrary `assistant_message_id`s, Phase 3A.6 eliminates all direct UPDATE privileges on `chat_requests` and introduces strictly validated PostgreSQL Security Definer RPC functions.

### 1. Privilege Revocation
```sql
REVOKE UPDATE, DELETE ON public.chat_requests FROM authenticated, anon;
DROP POLICY IF EXISTS chat_requests_update_own ON public.chat_requests;
DROP POLICY IF EXISTS chat_requests_delete_own ON public.chat_requests;
```
Direct `PATCH` or `DELETE` requests to `/rest/v1/chat_requests` by authenticated or anonymous users are rejected at the database level (`42501 permission denied`).

### 2. Strict Validated INSERT Policy
Direct `INSERT` into `chat_requests` is tightly restricted:
```sql
CREATE POLICY chat_requests_insert_own ON public.chat_requests
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id
        AND status = 'processing'
        AND request_fingerprint IS NOT NULL
        AND length(request_fingerprint) = 64
        AND EXISTS (SELECT 1 FROM public.conversations WHERE id = conversation_id AND user_id = auth.uid())
        AND EXISTS (SELECT 1 FROM public.messages WHERE id = user_message_id AND user_id = auth.uid() AND conversation_id = chat_requests.conversation_id)
    );
```

### 3. Narrowly Scoped Security Definer RPC Functions
All lifecycle mutations must pass through dedicated RPC functions executed with `SECURITY DEFINER` and `SET search_path = public, pg_temp`:

1. `claim_chat_request(p_idempotency_key, p_conversation_id, p_user_message_id, p_request_fingerprint)`:
   - Validates caller via `auth.uid()`.
   - Rejects non-NULL fingerprints if length != 64.
   - Verifies user ownership of conversation and user message.
   - Atomically inserts or returns existing request record with conflict handling.
2. `complete_chat_request(p_idempotency_key, p_assistant_message_id)`:
   - Validates caller via `auth.uid()`.
   - Verifies `status = 'processing'`. Completed requests cannot be re-completed or mutated.
   - Validates that `p_assistant_message_id` exists in `public.messages`, belongs to `auth.uid()`, matches the request's `conversation_id`, and has `role = 'assistant'`.
   - Transitions status to `'completed'` and binds `assistant_message_id`.
3. `fail_chat_request(p_idempotency_key)`:
   - Validates caller via `auth.uid()`.
   - Cannot mutate already `'completed'` requests.
   - Sets `status = 'failed'`.
4. `interrupt_chat_request(p_idempotency_key, p_assistant_message_id)`:
   - Validates caller via `auth.uid()`.
   - Cannot mutate already `'completed'` requests.
   - Verifies assistant message if provided.
   - Sets `status = 'interrupted'`.
5. `retry_chat_request(p_idempotency_key)`:
   - Validates caller via `auth.uid()`.
   - Atomically updates status from `('failed', 'interrupted')` to `'processing'`.
   - Fails if the request is already in `processing` or `completed`.

### 4. Zero Service-Role Key Usage
RPC functions are granted directly to the `authenticated` role (`GRANT EXECUTE ON FUNCTION ... TO authenticated`). All operations run under the end-user's authenticated JWT bearer token and anon key, ensuring complete tenant isolation with zero exposure of administrative database keys.

---

## 12. Phase 3A.7 Strict Lifecycle Matrix, Exclusive RPC Claiming, and Dedicated Reconciliation

Phase 3A.7 closes all remaining bypasses and enforces strict lifecycle invariants at the PostgreSQL engine level.

### 1. Strict Lifecycle Transition Matrix
The PostgreSQL trigger `handle_chat_requests_immutability()` and RPC functions strictly enforce the following transition matrix:

```
               ┌───────────────────────┐
               │      (Created)        │
               │      processing       │
               └───┬───────┬───────┬───┘
                   │       │       │
       ┌───────────┘       │       └───────────┐
       ▼                   ▼                   ▼
┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│  completed   │   │    failed     │   │ interrupted  │
│  (TERMINAL)  │   └───┬───────────┘   └───┬──────────┘
└──────────────┘       │                   │
       ▲               │ (retry_chat_req)  │ (retry_chat_req)
       │               ▼                   ▼
       │               ┌───────────────────┐
       │               │    processing     │
       │               └───────────────────┘
       │
       └───── [reconcile_chat_request ONLY] ───┘
```

- **Permitted Transitions**:
  - `processing → completed`
  - `processing → failed`
  - `processing → interrupted`
  - `failed → processing` (via `retry_chat_request`)
  - `interrupted → processing` (via `retry_chat_request`)
  - `completed` is strictly terminal and immutable.
- **Strictly Rejected Transitions**:
  - `failed → interrupted` (rejected)
  - `interrupted → failed` (rejected)
  - `failed → completed` (rejected in ordinary `complete_chat_request`)
  - `interrupted → completed` (rejected in ordinary `complete_chat_request`)
  - `completed → any other status` (rejected)

### 2. Exclusive RPC Creation Path & Direct INSERT Revocation
Direct table privileges on `public.chat_requests`:
- `SELECT`: Granted to `authenticated` (filtered by `auth.uid() = user_id`).
- `INSERT`: **REVOKED** from `authenticated` and `anon`. Direct INSERT policy dropped.
- `UPDATE`: **REVOKED** from `authenticated` and `anon`.
- `DELETE`: **REVOKED** from `authenticated` and `anon`.

Clients cannot insert or mutate `chat_requests` rows directly. All creation and mutations occur exclusively through `SECURITY DEFINER` RPC functions validating caller identity via `auth.uid()`.

### 3. Hexadecimal Fingerprint Format & Conflict Detection
- `request_fingerprint` is non-null and validated against `^[0-9a-fA-F]{64}$`.
- Legacy NULL fingerprints are migrated via SHA-256 digest backfill.
- When `claim_chat_request` encounters an existing key:
  - If stored fingerprint matches incoming: returns `{"claimed": false, "request": ...}`.
  - If stored fingerprint differs: raises `23505` resulting in HTTP 409 Conflict. Never silently returns an unrelated request.

### 4. Dedicated Narrowly Scoped Reconciliation RPC
Persistence recovery is isolated in `reconcile_chat_request(p_idempotency_key, p_assistant_message_id)`:
1. Validates caller via `auth.uid()`.
2. Locks the request row `FOR UPDATE`.
3. Verifies `p_assistant_message_id` belongs to `auth.uid()`, belongs to `conversation_id`, and has `role = 'assistant'`.
4. Verifies metadata binding: `metadata->>'user_message_id' = user_message_id`.
5. Verifies message is not interrupted (`metadata->>'interrupted' != 'true'`).
6. Atomically updates status to `'completed'` and binds `assistant_message_id`.

### 5. Repository RPC-Only Enforcement
`SupabasePostgresChatRepository` removed all legacy direct POST/PATCH fallbacks. Any missing RPC immediately raises `DatabaseOperationError` and never falls back to insecure direct operations.

---

## 13. Phase 3A.8 Legacy Fingerprint Compatibility and Verification Hardening

Phase 3A.8 corrects the legacy fingerprint backfill algorithm, formalizes the compatibility policy for unreconstructable records, resolves `pgcrypto` schema dependencies, and hardens hosted database verification.

### 1. Exact Application Normalization Parity
To guarantee deterministic idempotency fingerprints matching Python's application logic (`app.models.chat.compute_request_fingerprint`), PostgreSQL migration `20261115000010_correct_legacy_fingerprints_and_pgcrypto.sql` defines:

- `public.normalize_chat_content(p_content TEXT)`:
  1. Trims leading and trailing whitespace from the full text.
  2. Splits into lines across `\r\n`, `\n`, or `\r`.
  3. Strips trailing whitespace from each line (`rtrim`).
  4. Joins lines with `\n`.
- `public.compute_request_fingerprint_sql(p_user_id UUID, p_conversation_id UUID, p_content TEXT)`:
  Constructs payload `user:<user_id>|conv:<conv_id_or_none>|content:<normalized_content>` and outputs a 64-character lowercase SHA-256 hexadecimal string.

### 2. Safe Legacy Fingerprint Reconstruction
Historical records with NULL or legacy synthetic fingerprints are updated from their source user messages:
```sql
UPDATE public.chat_requests cr
SET request_fingerprint = public.compute_request_fingerprint_sql(cr.user_id, cr.conversation_id, m.content)
FROM public.messages m
WHERE cr.user_message_id = m.id
  AND (
      cr.request_fingerprint IS NULL
      OR cr.request_fingerprint !~ '^[0-9a-fA-F]{64}$'
  );
```

### 3. Compatibility Policy for Unreconstructable Records
If a historical `chat_requests` record references a `user_message_id` that no longer exists in `messages` (e.g., deleted message or incomplete legacy test artifact):
- The original content cannot be cryptographically proven or recovered.
- Assigning a synthetic or fake fingerprint would permanently poison the idempotency key and cause false conflict rejections.
- In accordance with the `ON DELETE CASCADE` contract, orphaned legacy records without an existing source message are purged:
  ```sql
  DELETE FROM public.chat_requests cr
  WHERE NOT EXISTS (
      SELECT 1 FROM public.messages m WHERE m.id = cr.user_message_id
  );
  ```
- This restores clean idempotency claiming for new legitimate requests.

### 4. `pgcrypto` Dependency & Multi-Schema Resolution
- Supabase hosts cryptographic routines in the `extensions` schema, whereas vanilla PostgreSQL installs them in `public`.
- `compute_request_fingerprint_sql` dynamically resolves `extensions.digest` or `public.digest`.
- All SECURITY DEFINER RPCs (`claim_chat_request`, `complete_chat_request`, `fail_chat_request`, `interrupt_chat_request`, `retry_chat_request`, `reconcile_chat_request`) explicitly configure:
  ```sql
  SET search_path = public, extensions, pg_temp;
  ```
  preventing search path hijacking and resolving `digest()` reliably.

### 5. Strict Permission-Denied Assertion
Direct mutations on `chat_requests` by authenticated or anonymous clients are strictly revoked. Hosted RLS integration tests assert:
- `401 Unauthorized` or `403 Forbidden` with PostgreSQL error code `42501` (`permission denied for table chat_requests`).
- No direct INSERT, UPDATE, or DELETE succeeds. All lifecycle mutations occur solely through authorized SECURITY DEFINER RPCs.

---

## 14. Phase 3A.9 Original Request Semantics, Migration Portability & Provenance Integrity

Phase 3A.9 resolves original request parameter reconstruction, guarantees genuine byte-for-byte Python/SQL normalization parity across Unicode whitespace and line breaks, avoids static schema qualifications for `pgcrypto`, and secures user message provenance.

### 1. Preservation of Original Request Conversation Semantics (`conv:none` vs `conv:<uuid>`)
When an initial request arrives without a supplied conversation ID, the backend derives a deterministic UUIDv5 conversation ID:
$$\text{deterministic\_conv\_id} = \text{uuid5}(\text{NAMESPACE\_OID}, \text{"auren:conv:"} + \text{user\_id} + \text{":"} + \text{idempotency\_key})$$
The application generates the fingerprint using `conversation_id=None`, producing `conv:none`.
During migration backfill, the original request input cannot be inferred simply from `chat_requests.conversation_id` because the database stores the deterministic UUID.

Migration 010 implements `public.compute_deterministic_conversation_id_sql`:
- If `chat_requests.conversation_id = deterministic_conv_id`, the original request did NOT supply a conversation ID $\rightarrow$ reconstructs using `NULL` (`conv:none`).
- If `chat_requests.conversation_id != deterministic_conv_id`, the request explicitly supplied an existing conversation ID $\rightarrow$ reconstructs using `cr.conversation_id` (`conv:<uuid>`).
- Guarantees that legitimate API replays without a conversation ID match the reconstructed fingerprint with zero false HTTP 409 collisions.

### 2. Comprehensive Python/SQL Normalization Parity
`public.normalize_chat_content(p_content text)` achieves byte-for-byte parity with Python's:
```python
"\n".join(line.rstrip() for line in content.strip().splitlines())
```
- **29 Unicode Whitespace Characters**: Strips all code points where `unicodedata.category` is separator (`Zs`, `Zl`, `Zp`) or ASCII control whitespace (`\t`, `\n`, `\v`, `\f`, `\r`, `\x1c`–`\x1f`, `\x85`, `\xa0`, `\u1680`, `\u2000`–`\u200a`, `\u2028`, `\u2029`, `\u202f`, `\u205f`, `\u3000`).
- **11 Line Boundary Representations**: Correctly splits across `\r\n` (CRLF), `\n` (LF), `\r` (CR), `\x0b` (VT), `\x0c` (FF), `\x1c` (FS), `\x1d` (GS), `\x1e` (RS), `\x85` (NEL), `\u2028` (LS), and `\u2029` (PS).
- Evaluated against 10 comprehensive regression test vectors verifying matching UTF-8 byte sequences and identical SHA-256 digests.

### 3. Safe `pgcrypto` Schema Resolution Without Static Qualifications
To ensure migration portability across environments where `pgcrypto` is installed in `public` (vanilla PostgreSQL) or `extensions` (Supabase):
- Removed all static schema-qualified references (e.g. `extensions.digest` or `public.digest`).
- All `SECURITY DEFINER` RPC functions and migration functions set:
  ```sql
  SET search_path = public, extensions, pg_temp;
  ```
- Unqualified calls to `digest(..., 'sha256')` resolve dynamically through `search_path`, eliminating `schema "extensions" does not exist` compile-time failures.

### 4. User Message Provenance & Immutability Trigger
To prevent historical or concurrent mutation of user prompts from poisoning request fingerprints:
- Added database triggers (`trg_messages_user_content_immutability`) in PostgreSQL and SQLite forbidding direct `UPDATE` on `messages.content` where `role = 'user'`.
- **Compatibility Policy for Unreconstructable Records**:
  If a legacy request row points to a missing user message, or if a user message's metadata indicates content was modified (`metadata->>'edited' = 'true'`), the record cannot be cryptographically proven.
  Unreconstructable records are purged from `chat_requests`. This preserves message history while clearing unprovable lifecycle locks, allowing clients to re-issue clean requests without false conflict rejections.

---

## 15. Phase 3A.10 Migration Trigger Compatibility and Real PostgreSQL Verification

Phase 3A.10 resolves the Migration 009/010 trigger conflict, conducts real PostgreSQL function and migration execution verification, validates UUIDv5 mathematical parity, verifies dual-schema `pgcrypto` portability, and hardens provenance handling.

### 1. Resolution of Migration 009/010 Trigger Conflict
Migration 009 created `trg_chat_requests_immutability` to block modifying `request_fingerprint`, and backfilled legacy rows with synthetic digests. When Migration 010 attempted to reconstruct fingerprints, `handle_chat_requests_immutability()` aborted the update with `request_fingerprint is immutable and cannot be modified`.

**Transactional Migration-Only Procedure:**
1. Migration 010 temporarily updates `handle_chat_requests_immutability()` to check `current_setting('auren.allow_legacy_fingerprint_reconstruction', true) = 'on'` AND strictly require that `OLD.request_fingerprint` matches the known synthetic digest `encode(digest('legacy:' || ...))`.
2. Within the transaction block, the session setting is enabled (`PERFORM set_config('auren.allow_legacy_fingerprint_reconstruction', 'on', true)`).
3. The backfill update executes, replacing exclusively the known synthetic digests.
4. Immediately following the backfill, `handle_chat_requests_immutability()` is restored to its permanent strict definition forbidding all modifications to `request_fingerprint`.
5. Because PostgreSQL migrations execute within transaction boundaries, any migration failure rolls back the entire state, guaranteeing the database is never left without its integrity protections.

### 2. Real PostgreSQL Function Parity Verification
Verified on actual PostgreSQL 17 execution (`test_postgresql_migrations_and_parity.py`):
- `public.normalize_chat_content()` matches Python's `"\n".join(line.rstrip() for line in content.strip().splitlines())` across all 10 Unicode whitespace, line separator, and trailing whitespace vectors.
- Exact UTF-8 byte equality and SHA-256 fingerprint equality confirmed for all test cases.
- `public.compute_deterministic_conversation_id_sql()` compared directly against Python's `uuid.uuid5(uuid.NAMESPACE_OID, ...)` across diverse test vectors (standard IDs, special characters, all-0, all-F, 128-char keys, Unicode strings). 100% byte-for-byte equality confirmed.

### 3. Pgcrypto Dual-Schema Portability
Verified by executing migrations 001..010 on clean PostgreSQL databases with:
1. `pgcrypto` installed in schema `public` (standard PostgreSQL installation).
2. `pgcrypto` installed in schema `extensions` (standard Supabase installation).
In both configurations, `digest(...)` resolves dynamically without static schema prefixes or missing function errors.

### 4. Robust Provenance Handling
- JSONB metadata checks use safe text equality (`COALESCE(m.metadata->>'edited' = 'true', FALSE)`) rather than direct boolean type casting, preventing non-boolean or invalid metadata values from aborting the migration.
- User message content immutability trigger (`trg_messages_user_content_immutability`) verified to block direct `UPDATE` on user messages in PostgreSQL.








