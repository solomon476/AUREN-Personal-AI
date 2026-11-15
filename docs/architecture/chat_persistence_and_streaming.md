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
