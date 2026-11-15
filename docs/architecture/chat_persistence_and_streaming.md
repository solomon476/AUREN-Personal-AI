# AUREN — Persistent Chat, Idempotency, and Streaming Reliability Architecture

This document details the architecture, persistence layers, idempotency guarantees, and resilient streaming mechanisms implemented in Phase 3A.1.

---

## 1. Dual Repository Architecture (`BaseChatRepository`)

AUREN separates repository interface contracts from backend persistence implementations. All chat, conversation, and lifecycle operations adhere to `BaseChatRepository`.

```
                      ┌──────────────────────┐
                      │  BaseChatRepository  │
                      └──────────┬───────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│  SupabasePostgresChatRepository │   │      SQLiteChatRepository       │
│  (Cloud Supabase PostgreSQL)    │   │  (Explicit Local-Dev / Offline) │
├─────────────────────────────────┤   ├─────────────────────────────────┤
│ • Supabase PostgREST API        │   │ • Disk-backed SQLite (WAL mode) │
│ • Caller JWT Token (auth.uid)   │   │ • Enforces foreign keys         │
│ • Public anon key only          │   │ • Atomic SQLite transactions    │
│ • Enforces PostgreSQL RLS       │   │ • Survives process restarts     │
│ • NO service-role key used      │   │ • Zero cloud dependencies       │
└─────────────────────────────────┘   └─────────────────────────────────┘
```

### Selection Rules (`get_chat_repository`)

- **Production / Supabase Mode**: Selected when `CHAT_REPOSITORY_TYPE="supabase"` or when `CHAT_REPOSITORY_TYPE="auto"` with `SUPABASE_URL` and `SUPABASE_ANON_KEY` configured and caller JWT token provided.
- **Local Development / Offline Mode**: Explicitly designated fallback using `SQLiteChatRepository`. Guarantees local developers and test suites can run offline without hosted infrastructure.

---

## 2. Row Level Security & Cloud PostgREST Enforcement

`SupabasePostgresChatRepository` communicates directly with Supabase PostgREST (`/rest/v1`):

- **Caller Identity**: PostgREST requests include `Authorization: Bearer <user_jwt_token>` and `apikey: <anon_key>`.
- **Row Level Security**: PostgreSQL evaluates policies (`auth.uid() = user_id`) on all reads and writes across `conversations`, `messages`, and `chat_requests`.
- **Zero Service-Role Usage**: The privileged `service-role` key is strictly excluded from ordinary user operations.
- **Cross-Tenant Isolation**: Attempting to read or mutate another user's conversation returns an empty set or error as enforced by the database engine.

---

## 3. Atomic Idempotency Lifecycle

To prevent duplicate user messages, concurrent race conditions, and accidental duplicate AI invocations during network reconnects, AUREN uses database-level atomic claiming.

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

### Atomic Claim Protocol (`claim_chat_request`)

1. When a request arrives with an `idempotency_key`:
   - Checks if a `completed` record exists. If found, replays the cached assistant response without invoking the LLM provider.
   - If a `processing` record already exists, rejects the duplicate with `idempotency_in_flight`.
2. Persists the user message (reusing existing on duplicate).
3. Executes an atomic insert into `chat_requests` with `status='processing'`.
   - **SQLite**: Enforced by `PRIMARY KEY (user_id, idempotency_key)`. Concurrent inserts raise `sqlite3.IntegrityError`, caught and returned as `(claimed=False, existing_req)`.
   - **PostgreSQL / PostgREST**: Enforced by primary key constraint. Concurrent inserts return `409 Conflict`, caught and returned as `(claimed=False, existing_req)`.
4. If `claimed == False`: The runner halts and does NOT invoke the AI provider.

---

## 4. Resilient Streaming & Heartbeat Decoupling

In prior implementations, running `asyncio.wait_for(stream_gen.__anext__(), timeout=15.0)` cancelled the generator coroutine when the 15-second heartbeat timer expired, corrupting or aborting the model stream.

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

---

## 5. Client Disconnection & Interruption Handling

If a client disconnects mid-stream (e.g. mobile connectivity drop or browser tab close):

1. `raw_request.is_disconnected()` detects client disconnection.
2. The loop exits immediately, setting `was_interrupted = True`.
3. The completion block is skipped.
4. If chunks were received:
   - Persists partial tokens with `metadata={"interrupted": True}`.
   - Updates `chat_requests` status to `"interrupted"`.
5. Under no circumstances is an interrupted response marked `"completed"`.

---

## 6. Frontend Stable Idempotency & Reconciliation

1. **Client-Side Generation**: When a user submits a prompt, `ChatView` assigns a stable `idempotencyKey = \`req-\${crypto.randomUUID()}\``.
2. **Optimistic Persistence**: The message is placed in local state with its stable idempotency key.
3. **Reconciliation & Retries**:
   - If an error occurs or the stream is interrupted, the UI displays a "Retry" button.
   - Retrying sends the **exact same** `idempotencyKey`.
   - If the backend already finished generation before the disconnect, it instantly replays the completed response from cache with zero additional AI tokens consumed.
   - If the request was interrupted or failed, the backend cleanly retries.
