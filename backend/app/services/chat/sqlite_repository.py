"""SQLite-backed chat repository for local development and offline testing.

Explicitly identified local-development option providing:
- Disk-backed SQLite storage surviving process restarts.
- Strict ownership verification on all operations.
- Atomic idempotency claiming via SQLite UNIQUE constraints.
- Foreign keys and WAL mode enabled.
- Asynchronous contract conformance without unnecessary rewrite.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

from app.models.chat import ChatRequestModel, ConversationModel, MessageModel
from app.services.chat.base_repository import BaseChatRepository

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_SQLITE_PATH = DB_DIR / "auren_chat.db"


class SQLiteChatRepository(BaseChatRepository):
    """SQLite implementation of BaseChatRepository for local development and offline testing."""

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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, idempotency_key)
                );

                CREATE INDEX IF NOT EXISTS idx_chat_requests_user_status
                ON chat_requests(user_id, status);
            """)

    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Optional[ConversationModel]:
        """Fetch conversation, strictly verifying that it belongs to user_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
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
            )

    async def create_conversation(
        self,
        user_id: UUID,
        title: str = "New Conversation",
        conversation_id: Optional[UUID] = None,
    ) -> ConversationModel:
        """Create a new conversation thread bound to the authenticated user."""
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

    async def get_or_create_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID,
        title: str = "New Conversation",
    ) -> ConversationModel:
        """Atomically get or create a conversation thread with a specific deterministic ID."""
        existing = await self.get_conversation(user_id, conversation_id)
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

        conv = await self.get_conversation(user_id, conversation_id)
        if conv:
            return conv
        return ConversationModel(
            id=conversation_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )

    async def list_conversations(self, user_id: UUID, limit: int = 50) -> List[ConversationModel]:
        """List all conversation threads owned by user_id, ordered by updated_at descending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
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
            )
            for r in rows
        ]

    async def get_chat_request(self, user_id: UUID, idempotency_key: str) -> Optional[ChatRequestModel]:
        """Fetch request lifecycle record by user_id and idempotency_key."""
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
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    async def persist_user_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: Optional[str] = None,
    ) -> MessageModel:
        """Persist user message into the database, reusing existing message on idempotency match."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        msg_id = uuid4()

        with self._get_connection() as conn:
            if idempotency_key:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM messages WHERE user_id = ? AND idempotency_key = ?",
                    (str(user_id), idempotency_key),
                )
                row = cursor.fetchone()
                if row:
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
                    (str(msg_id), str(conversation_id), str(user_id), "user", content, idempotency_key, "{}", now_iso),
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (now_iso, str(conversation_id), str(user_id)),
                )
            except sqlite3.IntegrityError:
                # Concurrent insert race with identical idempotency key
                if idempotency_key:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM messages WHERE user_id = ? AND idempotency_key = ?",
                        (str(user_id), idempotency_key),
                    )
                    row = cursor.fetchone()
                    if row:
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

    async def claim_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> Tuple[bool, ChatRequestModel]:
        """Atomically claim a chat request.

        Attempts atomic INSERT with status='processing'.
        If row with (user_id, idempotency_key) already exists, sqlite3.IntegrityError
        is raised and caught, returning (False, existing_request).
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO chat_requests (user_id, idempotency_key, conversation_id, status, user_message_id, created_at, updated_at)
                    VALUES (?, ?, ?, 'processing', ?, ?, ?)
                    """,
                    (str(user_id), idempotency_key, str(conversation_id), str(user_message_id), now_iso, now_iso),
                )
            return True, ChatRequestModel(
                user_id=user_id,
                idempotency_key=idempotency_key,
                conversation_id=conversation_id,
                status="processing",
                user_message_id=user_message_id,
                created_at=now,
                updated_at=now,
            )
        except sqlite3.IntegrityError:
            # Key was already claimed! Retrieve and return existing request record
            existing = await self.get_chat_request(user_id, idempotency_key)
            if existing:
                return False, existing
            raise

    async def update_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        status: str,
        assistant_message_id: Optional[UUID] = None,
    ) -> None:
        """Update request status (completed, failed, interrupted) and associate assistant message."""
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

    async def persist_assistant_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        """Persist completed assistant message reliably into the database."""
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

    async def get_message_by_id(self, user_id: UUID, message_id: UUID) -> Optional[MessageModel]:
        """Fetch a single message by ID, verifying caller ownership."""
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

    async def get_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 50,
    ) -> List[MessageModel]:
        """Retrieve message history for an owned conversation from the database."""
        conv = await self.get_conversation(user_id, conversation_id)
        if not conv:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (str(conversation_id), str(user_id), limit),
            )
            rows = cursor.fetchall()

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
