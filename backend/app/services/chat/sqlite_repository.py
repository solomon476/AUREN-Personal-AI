"""SQLite-backed chat repository for local development and offline testing.

Explicitly identified local-development option providing:
- Disk-backed SQLite storage surviving process restarts.
- Strict ownership verification on all operations.
- Atomic idempotency claiming and conditional state transitions.
- Synchronous sqlite3 operations isolated in worker threads (asyncio.to_thread)
  to avoid blocking the asyncio event loop.
- Foreign keys and WAL mode enabled.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple
from uuid import UUID, uuid4

from app.core.exceptions import DatabaseOperationError, IdempotencyConflictError
from app.models.chat import (
    ChatRequestModel,
    ConversationModel,
    MessageModel,
    compute_request_fingerprint,
)
from app.services.chat.base_repository import BaseChatRepository

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_SQLITE_PATH = DB_DIR / "auren_chat.db"


class SQLiteChatRepository(BaseChatRepository):
    """SQLite implementation of BaseChatRepository for local development and offline testing.

    Note: This is an explicitly identified local-development option. All database operations
    are executed via asyncio.to_thread to maintain an asynchronous non-blocking contract.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_SQLITE_PATH
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a connection with foreign keys and WAL mode enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_database(self):
        """Ensure parent directories and database tables exist on disk."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                ON conversations(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    idempotency_key TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conv_created
                ON messages(conversation_id, created_at ASC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_user_idempotency
                ON messages(user_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;

                CREATE TABLE IF NOT EXISTS chat_requests (
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed', 'interrupted')),
                    user_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    assistant_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
                    request_fingerprint TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, idempotency_key)
                );

                CREATE INDEX IF NOT EXISTS idx_chat_requests_user_status
                ON chat_requests(user_id, status);
            """)

            # Run incremental migration if request_fingerprint is missing in existing sqlite table
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(chat_requests)")
            columns = [col[1] for col in cursor.fetchall()]
            if "request_fingerprint" not in columns:
                conn.execute("ALTER TABLE chat_requests ADD COLUMN request_fingerprint TEXT")

            # Temporarily drop delete trigger during migration/backfill if present
            conn.execute("DROP TRIGGER IF EXISTS trg_chat_requests_prevent_direct_delete")

            # Safe legacy fingerprint reconstruction and compatibility policy
            # 1. Reconstruct exact fingerprint for records whose source message satisfies ALL provenance checks:
            #    - messages.id = chat_requests.user_message_id
            #    - messages.user_id = chat_requests.user_id
            #    - messages.conversation_id = chat_requests.conversation_id
            #    - messages.role = 'user'
            #    - provenance metadata is intact (not edited, not content_changed, no original_content)
            cursor.execute(
                """
                SELECT cr.user_id, cr.idempotency_key, cr.conversation_id, cr.user_message_id,
                       m.content, m.metadata, m.user_id, m.conversation_id, m.role
                FROM chat_requests cr
                LEFT JOIN messages m ON m.id = cr.user_message_id
                WHERE cr.request_fingerprint IS NULL
                """
            )
            for r_uid, r_key, r_cid, r_umsg_id, m_content, m_metadata, m_uid, m_cid, m_role in cursor.fetchall():
                # Provenance checks: source message must exist, belong to same user, same conversation, and role == 'user'
                if not r_umsg_id or not m_uid or m_uid != r_uid or m_cid != r_cid or m_role != "user":
                    conn.execute("DELETE FROM chat_requests WHERE user_id = ? AND idempotency_key = ?", (r_uid, r_key))
                    continue

                meta = json.loads(m_metadata) if isinstance(m_metadata, str) else (m_metadata or {})
                if meta.get("edited") is True or meta.get("content_changed") is True or "original_content" in meta:
                    # Message content was altered: provenance broken -> unreconstructable, purge
                    conn.execute("DELETE FROM chat_requests WHERE user_id = ? AND idempotency_key = ?", (r_uid, r_key))
                    continue

                # Determine original conversation input:
                # Was it an initial request without conversation_id?
                user_uuid = UUID(r_uid)
                det_conv_id = uuid.uuid5(uuid.NAMESPACE_OID, f"auren:conv:{user_uuid}:{r_key}")
                if UUID(r_cid) == det_conv_id:
                    # Request was originally submitted without conversation_id -> conv:none
                    orig_conv_id = None
                else:
                    # Request was originally submitted with an explicit conversation_id -> conv:<uuid>
                    orig_conv_id = UUID(r_cid)

                fp = compute_request_fingerprint(
                    user_uuid,
                    m_content,
                    orig_conv_id,
                )
                conn.execute(
                    "UPDATE chat_requests SET request_fingerprint = ? WHERE user_id = ? AND idempotency_key = ?",
                    (fp, r_uid, r_key),
                )

            # 2. Compatibility policy: purge unreconstructable records (orphans whose source message was deleted, missing, or invalid)
            cursor.execute(
                """
                DELETE FROM chat_requests
                WHERE request_fingerprint IS NULL OR length(request_fingerprint) != 64
                """
            )

            # Database-level integrity triggers enforcing immutability & valid transitions
            conn.executescript("""
                CREATE TRIGGER IF NOT EXISTS trg_chat_requests_immutable_fingerprint
                BEFORE UPDATE ON chat_requests
                FOR EACH ROW
                WHEN OLD.request_fingerprint IS NOT NULL AND NEW.request_fingerprint IS NOT OLD.request_fingerprint
                BEGIN
                    SELECT RAISE(ABORT, 'request_fingerprint is immutable and cannot be modified once set');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_chat_requests_immutable_owner
                BEFORE UPDATE ON chat_requests
                FOR EACH ROW
                WHEN NEW.user_id IS NOT OLD.user_id
                BEGIN
                    SELECT RAISE(ABORT, 'user_id is immutable and cannot be transferred');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_chat_requests_immutable_completed
                BEFORE UPDATE ON chat_requests
                FOR EACH ROW
                WHEN OLD.status = 'completed' AND NEW.status != 'completed'
                BEGIN
                    SELECT RAISE(ABORT, 'Completed chat requests cannot be transitioned out of completed status');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_chat_requests_lifecycle_transitions
                BEFORE UPDATE OF status ON chat_requests
                FOR EACH ROW
                WHEN OLD.status IS NOT NEW.status
                BEGIN
                    SELECT CASE
                        WHEN OLD.status = 'completed' THEN
                            RAISE(ABORT, 'Completed chat requests cannot be transitioned out of completed status')
                        WHEN OLD.status = 'processing' AND NEW.status NOT IN ('completed', 'failed', 'interrupted') THEN
                            RAISE(ABORT, 'Invalid status transition: processing can only transition to completed, failed, or interrupted')
                        WHEN OLD.status = 'failed' AND NEW.status NOT IN ('processing', 'completed') THEN
                            RAISE(ABORT, 'Invalid status transition: failed can only transition to processing or completed via reconcile')
                        WHEN OLD.status = 'interrupted' AND NEW.status NOT IN ('processing', 'completed') THEN
                            RAISE(ABORT, 'Invalid status transition: interrupted can only transition to processing or completed via reconcile')
                    END;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_chat_requests_immutable_key
                BEFORE UPDATE ON chat_requests
                FOR EACH ROW
                WHEN NEW.idempotency_key IS NOT OLD.idempotency_key
                BEGIN
                    SELECT RAISE(ABORT, 'idempotency_key is immutable and cannot be modified');
                END;

                DROP TRIGGER IF EXISTS trg_chat_requests_prevent_direct_delete;
                CREATE TRIGGER trg_chat_requests_prevent_direct_delete
                BEFORE DELETE ON chat_requests
                FOR EACH ROW
                WHEN (SELECT 1 FROM conversations WHERE id = OLD.conversation_id) IS NOT NULL
                  AND (SELECT 1 FROM messages WHERE id = OLD.user_message_id) IS NOT NULL
                BEGIN
                    SELECT RAISE(ABORT, 'Direct DELETE on chat_requests is forbidden; deletion must cascade from conversation');
                END;

                DROP TRIGGER IF EXISTS trg_messages_user_content_immutability;
                CREATE TRIGGER trg_messages_user_content_immutability
                BEFORE UPDATE OF content ON messages
                FOR EACH ROW
                WHEN OLD.role = 'user' AND NEW.content IS NOT OLD.content
                BEGIN
                    SELECT RAISE(ABORT, 'User message content is immutable and cannot be modified');
                END;
            """)

    # -----------------------------------------------------------------------
    # Synchronous Core Operations (run via asyncio.to_thread)
    # -----------------------------------------------------------------------
    def _sync_get_conversation(self, user_id: UUID, conversation_id: UUID) -> Optional[ConversationModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.id, c.user_id, c.title, c.created_at, c.updated_at,
                       COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id AND m.user_id = c.user_id
                WHERE c.id = ? AND c.user_id = ?
                GROUP BY c.id, c.user_id, c.title, c.created_at, c.updated_at
                """,
                (str(conversation_id), str(user_id)),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ConversationModel(
                id=UUID(row["id"]),
                user_id=UUID(row["user_id"]),
                title=row["title"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                message_count=int(row["message_count"]) if "message_count" in row.keys() else 0,
            )

    def _sync_create_conversation(
        self,
        user_id: UUID,
        title: str,
        conversation_id: Optional[UUID] = None,
    ) -> ConversationModel:
        conv_id = conversation_id or uuid4()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (str(conv_id), str(user_id), title, now_iso, now_iso),
            )

        return ConversationModel(
            id=conv_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )

    def _sync_get_or_create_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID,
        title: str,
    ) -> ConversationModel:
        existing = self._sync_get_conversation(user_id, conversation_id)
        if existing:
            return existing

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (str(conversation_id), str(user_id), title, now_iso, now_iso),
            )

        conv = self._sync_get_conversation(user_id, conversation_id)
        if conv:
            return conv
        return ConversationModel(
            id=conversation_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )

    def _sync_list_conversations(self, user_id: UUID, limit: int) -> List[ConversationModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.id, c.user_id, c.title, c.created_at, c.updated_at,
                       COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id AND m.user_id = c.user_id
                WHERE c.user_id = ?
                GROUP BY c.id, c.user_id, c.title, c.created_at, c.updated_at
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (str(user_id), limit),
            )
            rows = cursor.fetchall()

        return [
            ConversationModel(
                id=UUID(r["id"]),
                user_id=UUID(r["user_id"]),
                title=r["title"],
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
                message_count=int(r["message_count"]) if "message_count" in r.keys() else 0,
            )
            for r in rows
        ]

    def _sync_update_conversation_title(
        self,
        user_id: UUID,
        conversation_id: UUID,
        title: str,
    ) -> Optional[ConversationModel]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (title, now_iso, str(conversation_id), str(user_id)),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self._sync_get_conversation(user_id, conversation_id)

    async def update_conversation_title(
        self,
        user_id: UUID,
        conversation_id: UUID,
        title: str,
    ) -> Optional[ConversationModel]:
        """Update conversation title, strictly enforcing ownership."""
        return await asyncio.to_thread(
            self._sync_update_conversation_title,
            user_id,
            conversation_id,
            title,
        )

    def _sync_delete_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID,
    ) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
                (str(conversation_id), str(user_id)),
            )
            if not cursor.fetchone():
                return False

            cursor.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (str(conversation_id), str(user_id)),
            )
            conn.commit()
            return True

    async def delete_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID,
    ) -> bool:
        """Atomically delete conversation and associated messages, enforcing ownership."""
        return await asyncio.to_thread(
            self._sync_delete_conversation,
            user_id,
            conversation_id,
        )

    def _sync_get_chat_request(self, user_id: UUID, idempotency_key: str) -> Optional[ChatRequestModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM chat_requests WHERE user_id = ? AND idempotency_key = ?",
                (str(user_id), idempotency_key),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ChatRequestModel(
                user_id=UUID(row["user_id"]),
                idempotency_key=row["idempotency_key"],
                conversation_id=UUID(row["conversation_id"]),
                status=row["status"],
                user_message_id=UUID(row["user_message_id"]),
                assistant_message_id=UUID(row["assistant_message_id"]) if row["assistant_message_id"] else None,
                request_fingerprint=row["request_fingerprint"] if "request_fingerprint" in row.keys() else None,
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def _sync_persist_user_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MessageModel:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        msg_id = uuid4()
        msg_metadata = metadata or {}

        with self._get_connection() as conn:
            if idempotency_key:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM messages WHERE user_id = ? AND idempotency_key = ?",
                    (str(user_id), idempotency_key),
                )
                row = cursor.fetchone()
                if row:
                    existing_normalized = "\n".join(line.rstrip() for line in row["content"].strip().splitlines())
                    incoming_normalized = "\n".join(line.rstrip() for line in content.strip().splitlines())
                    if existing_normalized != incoming_normalized:
                        raise IdempotencyConflictError(
                            f"Idempotency key '{idempotency_key}' was already used with different message content."
                        )
                    if UUID(row["conversation_id"]) != conversation_id:
                        raise IdempotencyConflictError(
                            f"Idempotency key '{idempotency_key}' was already used with a different conversation."
                        )
                    return MessageModel(
                        id=UUID(row["id"]),
                        conversation_id=UUID(row["conversation_id"]),
                        user_id=UUID(row["user_id"]),
                        role=row["role"],
                        content=row["content"],
                        idempotency_key=row["idempotency_key"],
                        metadata=json.loads(row["metadata"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )

            try:
                conn.execute(
                    """
                    INSERT INTO messages (id, conversation_id, user_id, role, content, idempotency_key, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(msg_id), str(conversation_id), str(user_id), "user", content, idempotency_key, json.dumps(msg_metadata), now_iso),
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (now_iso, str(conversation_id), str(user_id)),
                )
            except sqlite3.IntegrityError:
                if idempotency_key:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM messages WHERE user_id = ? AND idempotency_key = ?",
                        (str(user_id), idempotency_key),
                    )
                    row = cursor.fetchone()
                    if row:
                        existing_normalized = "\n".join(line.rstrip() for line in row["content"].strip().splitlines())
                        incoming_normalized = "\n".join(line.rstrip() for line in content.strip().splitlines())
                        if existing_normalized != incoming_normalized:
                            raise IdempotencyConflictError(
                                f"Idempotency key '{idempotency_key}' was already used with different message content."
                            )
                        if UUID(row["conversation_id"]) != conversation_id:
                            raise IdempotencyConflictError(
                                f"Idempotency key '{idempotency_key}' was already used with a different conversation."
                            )
                        return MessageModel(
                            id=UUID(row["id"]),
                            conversation_id=UUID(row["conversation_id"]),
                            user_id=UUID(row["user_id"]),
                            role=row["role"],
                            content=row["content"],
                            idempotency_key=row["idempotency_key"],
                            metadata=json.loads(row["metadata"]),
                            created_at=datetime.fromisoformat(row["created_at"]),
                        )
                raise

        return MessageModel(
            id=msg_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=content,
            idempotency_key=idempotency_key,
            created_at=now,
        )

    def _sync_claim_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        conversation_id: UUID,
        user_message_id: UUID,
        request_fingerprint: Optional[str] = None,
    ) -> Tuple[bool, ChatRequestModel]:
        # Enforce strictly non-null, 64-character hexadecimal format
        if not request_fingerprint or len(request_fingerprint) != 64 or not all(c in "0123456789abcdefABCDEF" for c in request_fingerprint):
            raise ValueError("Valid 64-character hexadecimal request fingerprint is required")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, request_fingerprint, created_at, updated_at)
                    VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)
                    """,
                    (str(user_id), idempotency_key, str(conversation_id), str(user_message_id), request_fingerprint, now_iso, now_iso),
                )
            return True, ChatRequestModel(
                user_id=user_id,
                idempotency_key=idempotency_key,
                conversation_id=conversation_id,
                status="processing",
                user_message_id=user_message_id,
                request_fingerprint=request_fingerprint,
                created_at=now,
                updated_at=now,
            )
        except sqlite3.IntegrityError:
            existing = self._sync_get_chat_request(user_id, idempotency_key)
            if existing:
                if existing.request_fingerprint != request_fingerprint:
                    raise IdempotencyConflictError(
                        f"Idempotency key '{idempotency_key}' was already used with conflicting request content."
                    )
                return False, existing
            raise

    def _sync_transition_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        from_statuses: List[str],
        to_status: str,
    ) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in from_statuses)
        sql = f"""
            UPDATE chat_requests
            SET status = ?, updated_at = ?
            WHERE user_id = ? AND idempotency_key = ? AND status IN ({placeholders})
        """
        params = [to_status, now_iso, str(user_id), idempotency_key] + from_statuses
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.rowcount > 0

    def _sync_update_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        status: str,
        assistant_message_id: Optional[UUID] = None,
    ) -> None:
        req = self._sync_get_chat_request(user_id, idempotency_key)
        if not req:
            raise DatabaseOperationError(f"Chat request '{idempotency_key}' not found")

        if req.status == status:
            if assistant_message_id and not req.assistant_message_id:
                now_iso = datetime.now(timezone.utc).isoformat()
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE chat_requests
                        SET assistant_message_id = ?, updated_at = ?
                        WHERE user_id = ? AND idempotency_key = ?
                        """,
                        (str(assistant_message_id), now_iso, str(user_id), idempotency_key),
                    )
            return

        if req.status == "completed":
            raise sqlite3.IntegrityError("Completed chat requests cannot be transitioned out of completed status")

        if req.status != "processing":
            raise sqlite3.IntegrityError(f"Invalid status transition: cannot transition from {req.status} to {status}")

        if status not in ("completed", "failed", "interrupted"):
            raise sqlite3.IntegrityError(f"Invalid status transition: cannot transition to {status}")

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE chat_requests
                SET status = ?, assistant_message_id = COALESCE(?, assistant_message_id), updated_at = ?
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (status, str(assistant_message_id) if assistant_message_id else None, now_iso, str(user_id), idempotency_key),
            )

    def _sync_reconcile_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        assistant_message_id: UUID,
    ) -> ChatRequestModel:
        req = self._sync_get_chat_request(user_id, idempotency_key)
        if not req:
            raise DatabaseOperationError(f"Chat request '{idempotency_key}' not found")

        if req.status == "completed":
            if req.assistant_message_id == assistant_message_id:
                return req
            raise sqlite3.IntegrityError("Completed request already associated with different assistant message")

        msg = self._sync_get_message_by_id(user_id, assistant_message_id)
        if not msg or msg.role != "assistant" or msg.conversation_id != req.conversation_id:
            raise DatabaseOperationError("Invalid assistant_message_id: message not found in thread or not an assistant response")

        if msg.metadata.get("user_message_id") != str(req.user_message_id):
            raise DatabaseOperationError("Assistant message was not generated for this user message")

        if msg.metadata.get("interrupted"):
            raise DatabaseOperationError("Cannot reconcile request with an interrupted assistant message")

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE chat_requests
                SET status = 'completed', assistant_message_id = ?, updated_at = ?
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (str(assistant_message_id), now_iso, str(user_id), idempotency_key),
            )
        return self._sync_get_chat_request(user_id, idempotency_key)

    def _sync_persist_assistant_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        msg_id = uuid4()
        meta_json = json.dumps(metadata or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, user_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(msg_id), str(conversation_id), str(user_id), "assistant", content, meta_json, now_iso),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                (now_iso, str(conversation_id), str(user_id)),
            )

        return MessageModel(
            id=msg_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=content,
            metadata=metadata or {},
            created_at=now,
        )

    def _sync_update_assistant_message(
        self,
        user_id: UUID,
        message_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        meta_json = json.dumps(metadata or {})
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE messages
                SET content = ?, metadata = ?
                WHERE id = ? AND user_id = ?
                """,
                (content, meta_json, str(message_id), str(user_id)),
            )
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM messages WHERE id = ? AND user_id = ?",
                (str(message_id), str(user_id)),
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError(f"Message {message_id} not found for user {user_id}")
            return MessageModel(
                id=UUID(row["id"]),
                conversation_id=UUID(row["conversation_id"]),
                user_id=UUID(row["user_id"]),
                role=row["role"],
                content=row["content"],
                idempotency_key=row["idempotency_key"],
                metadata=json.loads(row["metadata"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def _sync_get_message_by_id(self, user_id: UUID, message_id: UUID) -> Optional[MessageModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM messages WHERE id = ? AND user_id = ?",
                (str(message_id), str(user_id)),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return MessageModel(
                id=UUID(row["id"]),
                conversation_id=UUID(row["conversation_id"]),
                user_id=UUID(row["user_id"]),
                role=row["role"],
                content=row["content"],
                idempotency_key=row["idempotency_key"],
                metadata=json.loads(row["metadata"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def _sync_find_assistant_message_for_request(
        self,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> Optional[MessageModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM messages
                WHERE user_id = ? AND conversation_id = ? AND role = 'assistant'
                ORDER BY created_at DESC
                """,
                (str(user_id), str(conversation_id)),
            )
            rows = cursor.fetchall()
            for row in rows:
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                if meta.get("user_message_id") == str(user_message_id):
                    return MessageModel(
                        id=UUID(row["id"]),
                        conversation_id=UUID(row["conversation_id"]),
                        user_id=UUID(row["user_id"]),
                        role=row["role"],
                        content=row["content"],
                        idempotency_key=row["idempotency_key"],
                        metadata=meta,
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )
            return None

    def _sync_get_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> List[MessageModel]:
        conv = self._sync_get_conversation(user_id, conversation_id)
        if not conv:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (str(conversation_id), str(user_id), limit),
            )
            rows = cursor.fetchall()

        # Reverse to restore chronological order (oldest to newest) of the most recent slice
        rows.reverse()

        return [
            MessageModel(
                id=UUID(r["id"]),
                conversation_id=UUID(r["conversation_id"]),
                user_id=UUID(r["user_id"]),
                role=r["role"],
                content=r["content"],
                idempotency_key=r["idempotency_key"],
                metadata=json.loads(r["metadata"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # -----------------------------------------------------------------------
    # Asynchronous Interface Implementation (isolated via asyncio.to_thread)
    # -----------------------------------------------------------------------
    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Optional[ConversationModel]:
        return await asyncio.to_thread(self._sync_get_conversation, user_id, conversation_id)

    async def create_conversation(
        self,
        user_id: UUID,
        title: str = "New Conversation",
        conversation_id: Optional[UUID] = None,
    ) -> ConversationModel:
        return await asyncio.to_thread(self._sync_create_conversation, user_id, title, conversation_id)

    async def get_or_create_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID,
        title: str = "New Conversation",
    ) -> ConversationModel:
        return await asyncio.to_thread(self._sync_get_or_create_conversation, user_id, conversation_id, title)

    async def list_conversations(self, user_id: UUID, limit: int = 50) -> List[ConversationModel]:
        return await asyncio.to_thread(self._sync_list_conversations, user_id, limit)

    async def get_chat_request(self, user_id: UUID, idempotency_key: str) -> Optional[ChatRequestModel]:
        return await asyncio.to_thread(self._sync_get_chat_request, user_id, idempotency_key)

    async def persist_user_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MessageModel:
        return await asyncio.to_thread(self._sync_persist_user_message, user_id, conversation_id, content, idempotency_key, metadata)

    async def claim_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        conversation_id: UUID,
        user_message_id: UUID,
        request_fingerprint: Optional[str] = None,
    ) -> Tuple[bool, ChatRequestModel]:
        return await asyncio.to_thread(
            self._sync_claim_chat_request,
            user_id,
            idempotency_key,
            conversation_id,
            user_message_id,
            request_fingerprint,
        )

    async def find_assistant_message_for_request(
        self,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> Optional[MessageModel]:
        return await asyncio.to_thread(
            self._sync_find_assistant_message_for_request,
            user_id,
            conversation_id,
            user_message_id,
        )

    async def transition_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        from_statuses: List[str],
        to_status: str,
    ) -> bool:
        return await asyncio.to_thread(self._sync_transition_chat_request_status, user_id, idempotency_key, from_statuses, to_status)

    async def update_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        status: str,
        assistant_message_id: Optional[UUID] = None,
    ) -> None:
        await asyncio.to_thread(self._sync_update_chat_request_status, user_id, idempotency_key, status, assistant_message_id)

    async def reconcile_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        assistant_message_id: UUID,
    ) -> ChatRequestModel:
        return await asyncio.to_thread(self._sync_reconcile_chat_request, user_id, idempotency_key, assistant_message_id)

    async def persist_assistant_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        return await asyncio.to_thread(self._sync_persist_assistant_message, user_id, conversation_id, content, metadata)

    async def update_assistant_message(
        self,
        user_id: UUID,
        message_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        return await asyncio.to_thread(self._sync_update_assistant_message, user_id, message_id, content, metadata)

    async def get_message_by_id(self, user_id: UUID, message_id: UUID) -> Optional[MessageModel]:
        return await asyncio.to_thread(self._sync_get_message_by_id, user_id, message_id)

    async def get_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 50,
    ) -> List[MessageModel]:
        return await asyncio.to_thread(self._sync_get_messages, user_id, conversation_id, limit)

    async def search_memories_hybrid(
        self,
        user_id: UUID,
        query_text: str,
        query_embedding: Optional[List[float]] = None,
        limit: int = 5,
        min_similarity: float = 0.0,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        dimension: Optional[int] = None,
    ) -> List[Any]:
        """Local SQLite mock returns empty memory candidates."""
        return []
