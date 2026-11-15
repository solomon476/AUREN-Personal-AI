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


