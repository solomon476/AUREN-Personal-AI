"""SQLite-backed memory repository for local development and offline testing.

Provides:
- Disk-backed SQLite storage for memories surviving process restarts.
- Strict user ownership verification on all operations.
- Full epistemic lifecycle state machine enforcement matching PostgreSQL constraints.
- Atomic lineage tracking for memory corrections (superseded_by_id / previous_version_id).
- Thread-isolated non-blocking asynchronous execution via asyncio.to_thread.
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.core.exceptions import DatabaseOperationError
from app.models.memory import MemoryModel
from app.services.memory.base_repository import BaseMemoryRepository

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_SQLITE_PATH = DB_DIR / "auren_chat.db"


class SQLiteMemoryRepository(BaseMemoryRepository):
    """SQLite implementation of BaseMemoryRepository for local development and offline testing."""

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
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'fact',
                    category TEXT NOT NULL DEFAULT 'general',
                    importance INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
                    confidence REAL,
                    confirmation_status TEXT NOT NULL DEFAULT 'unconfirmed'
                        CHECK (confirmation_status IN ('confirmed', 'unconfirmed', 'rejected', 'system_asserted')),
                    lifecycle_status TEXT NOT NULL DEFAULT 'active'
                        CHECK (lifecycle_status IN ('active', 'superseded', 'expired', 'archived', 'rejected', 'forgotten')),
                    origin TEXT NOT NULL DEFAULT 'user_direct_input',
                    source_message_id TEXT,
                    source_conversation_id TEXT,
                    superseded_by_id TEXT,
                    previous_version_id TEXT,
                    root_memory_id TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    last_accessed_at TEXT,
                    last_confirmed_at TEXT,
                    expires_at TEXT,
                    review_after TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_memories_user_lifecycle ON memories(user_id, lifecycle_status);
                CREATE INDEX IF NOT EXISTS idx_memories_user_category ON memories(user_id, category);
                CREATE INDEX IF NOT EXISTS idx_memories_user_type ON memories(user_id, memory_type);
                CREATE INDEX IF NOT EXISTS idx_memories_root_lineage ON memories(root_memory_id, previous_version_id);
            """)

    def _row_to_model(self, row: sqlite3.Row) -> MemoryModel:
        """Convert a SQLite row to a MemoryModel."""
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except Exception:
                metadata = {}

        return MemoryModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            content=row["content"],
            memory_type=row["memory_type"],
            category=row["category"],
            importance=row["importance"],
            confidence=row["confidence"],
            confirmation_status=row["confirmation_status"],
            lifecycle_status=row["lifecycle_status"],
            origin=row["origin"],
            source_message_id=UUID(row["source_message_id"]) if row["source_message_id"] else None,
            source_conversation_id=UUID(row["source_conversation_id"]) if row["source_conversation_id"] else None,
            superseded_by_id=UUID(row["superseded_by_id"]) if row["superseded_by_id"] else None,
            previous_version_id=UUID(row["previous_version_id"]) if row["previous_version_id"] else None,
            root_memory_id=UUID(row["root_memory_id"]) if row["root_memory_id"] else None,
            access_count=row["access_count"] or 0,
            last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]) if row["last_accessed_at"] else None,
            last_confirmed_at=datetime.fromisoformat(row["last_confirmed_at"]) if row["last_confirmed_at"] else None,
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            review_after=datetime.fromisoformat(row["review_after"]) if row["review_after"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=metadata,
        )

    # -----------------------------------------------------------------------
    # Synchronous Worker Methods
    # -----------------------------------------------------------------------

    def _sync_list_memories(
        self,
        user_id: UUID,
        query: Optional[str] = None,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        confirmation_status: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MemoryModel], int]:
        clauses = ["user_id = ?"]
        params: List[Any] = [str(user_id)]

        if query and query.strip():
            clauses.append("content LIKE ?")
            params.append(f"%{query.strip()}%")

        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)

        if category:
            clauses.append("category = ?")
            params.append(category)

        if confirmation_status:
            clauses.append("confirmation_status = ?")
            params.append(confirmation_status)

        if lifecycle_status:
            clauses.append("lifecycle_status = ?")
            params.append(lifecycle_status)

        where_sql = " AND ".join(clauses)
        offset = max(0, (page - 1) * page_size)

        with self._get_connection() as conn:
            # Count total matching records
            count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM memories WHERE {where_sql};", params)
            total = count_cursor.fetchone()["total"]

            # Select paginated results
            select_sql = f"""
                SELECT * FROM memories
                WHERE {where_sql}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ? OFFSET ?;
            """
            select_params = params + [page_size, offset]
            rows = conn.execute(select_sql, select_params).fetchall()
            return [self._row_to_model(r) for r in rows], total

    def _sync_get_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ? AND user_id = ?;",
                (str(memory_id), str(user_id)),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def _sync_create_memory(
        self,
        user_id: UUID,
        content: str,
        memory_type: str = "fact",
        category: str = "general",
        importance: int = 3,
        origin: str = "user_direct_input",
    ) -> MemoryModel:
        now_iso = datetime.now(timezone.utc).isoformat()
        memory_id = str(uuid4())

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, user_id, content, memory_type, category, importance,
                    confidence, confirmation_status, lifecycle_status, origin,
                    root_memory_id, created_at, updated_at, last_confirmed_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, 1.0, 'confirmed', 'active', ?, ?, ?, ?, ?, '{}');
                """,
                (
                    memory_id,
                    str(user_id),
                    content.strip(),
                    memory_type,
                    category,
                    importance,
                    origin,
                    memory_id,
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()

        return self._sync_get_memory(user_id, UUID(memory_id))

    def _sync_confirm_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ? AND user_id = ?;",
                (str(memory_id), str(user_id)),
            ).fetchone()
            if not row:
                return None

            mem = self._row_to_model(row)
            if mem.confirmation_status == "rejected":
                raise ValueError("Cannot confirm previously rejected memory")
            if mem.lifecycle_status != "active":
                raise ValueError(f"Cannot confirm memory with lifecycle status: {mem.lifecycle_status}")
            if mem.confirmation_status == "confirmed":
                return mem

            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE memories
                SET confirmation_status = 'confirmed',
                    confidence = 1.0,
                    last_confirmed_at = ?,
                    updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (now_iso, now_iso, str(memory_id), str(user_id)),
            )
            conn.commit()

        return self._sync_get_memory(user_id, memory_id)

    def _sync_reject_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ? AND user_id = ?;",
                (str(memory_id), str(user_id)),
            ).fetchone()
            if not row:
                return None

            mem = self._row_to_model(row)
            if mem.lifecycle_status in ("superseded", "forgotten"):
                raise ValueError(f"Cannot reject memory with lifecycle status: {mem.lifecycle_status}")

            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE memories
                SET confirmation_status = 'rejected',
                    lifecycle_status = 'rejected',
                    updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (now_iso, str(memory_id), str(user_id)),
            )
            conn.commit()

        return self._sync_get_memory(user_id, memory_id)

    def _sync_correct_memory(
        self,
        user_id: UUID,
        memory_id: UUID,
        content: str,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
    ) -> Optional[MemoryModel]:
        with self._get_connection() as conn:
            # Immediate write lock: eliminates TOCTOU race by holding lock across read & write
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ? AND user_id = ?;",
                    (str(memory_id), str(user_id)),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return None

                old_mem = self._row_to_model(row)
                if old_mem.lifecycle_status != "active":
                    raise ValueError(f"Cannot correct memory with lifecycle status: {old_mem.lifecycle_status}")
                if old_mem.confirmation_status == "rejected":
                    raise ValueError("Cannot correct rejected memory")

                new_id = str(uuid4())
                root_id = str(old_mem.root_memory_id or old_mem.id)
                now_iso = datetime.now(timezone.utc).isoformat()

                new_type = memory_type or old_mem.memory_type
                new_cat = category or old_mem.category
                new_imp = importance if importance is not None else old_mem.importance

                conn.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, content, memory_type, category, importance,
                        confidence, confirmation_status, lifecycle_status, origin,
                        previous_version_id, root_memory_id, created_at, updated_at,
                        last_confirmed_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, 1.0, 'confirmed', 'active', 'user_direct_edit', ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        new_id,
                        str(user_id),
                        content.strip(),
                        new_type,
                        new_cat,
                        new_imp,
                        str(old_mem.id),
                        root_id,
                        now_iso,
                        now_iso,
                        now_iso,
                        json.dumps(old_mem.metadata),
                    ),
                )
                conn.execute(
                    """
                    UPDATE memories
                    SET lifecycle_status = 'superseded',
                        superseded_by_id = ?,
                        updated_at = ?
                    WHERE id = ? AND user_id = ?;
                    """,
                    (new_id, now_iso, str(old_mem.id), str(user_id)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return self._sync_get_memory(user_id, UUID(new_id))

    def _sync_archive_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ? AND user_id = ?;",
                    (str(memory_id), str(user_id)),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return None

                mem = self._row_to_model(row)
                if mem.lifecycle_status != "active":
                    raise ValueError(f"Cannot archive memory with lifecycle status: {mem.lifecycle_status}")
                if mem.confirmation_status == "rejected":
                    raise ValueError("Cannot archive rejected memory")

                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    UPDATE memories
                    SET lifecycle_status = 'archived',
                        updated_at = ?
                    WHERE id = ? AND user_id = ?;
                    """,
                    (now_iso, str(memory_id), str(user_id)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return self._sync_get_memory(user_id, memory_id)

    def _sync_restore_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ? AND user_id = ?;",
                    (str(memory_id), str(user_id)),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return None

                mem = self._row_to_model(row)
                if mem.lifecycle_status not in ("archived", "expired"):
                    raise ValueError(f"Cannot restore memory with lifecycle status: {mem.lifecycle_status}")
                if mem.confirmation_status == "rejected":
                    raise ValueError("Cannot restore rejected memory")

                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    UPDATE memories
                    SET lifecycle_status = 'active',
                        updated_at = ?
                    WHERE id = ? AND user_id = ?;
                    """,
                    (now_iso, str(memory_id), str(user_id)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return self._sync_get_memory(user_id, memory_id)

    def _sync_outdate_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ? AND user_id = ?;",
                    (str(memory_id), str(user_id)),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return None

                mem = self._row_to_model(row)
                if mem.lifecycle_status != "active":
                    raise ValueError(f"Cannot outdate memory with lifecycle status: {mem.lifecycle_status}")
                if mem.confirmation_status == "rejected":
                    raise ValueError("Cannot outdate rejected memory")

                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    UPDATE memories
                    SET lifecycle_status = 'expired',
                        updated_at = ?
                    WHERE id = ? AND user_id = ?;
                    """,
                    (now_iso, str(memory_id), str(user_id)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return self._sync_get_memory(user_id, memory_id)

    # -----------------------------------------------------------------------
    # Asynchronous Interface Implementation
    # -----------------------------------------------------------------------

    async def list_memories(
        self,
        user_id: UUID,
        query: Optional[str] = None,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        confirmation_status: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MemoryModel], int]:
        return await asyncio.to_thread(
            self._sync_list_memories,
            user_id,
            query,
            memory_type,
            category,
            confirmation_status,
            lifecycle_status,
            page,
            page_size,
        )

    async def get_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        return await asyncio.to_thread(self._sync_get_memory, user_id, memory_id)

    async def create_memory(
        self,
        user_id: UUID,
        content: str,
        memory_type: str = "fact",
        category: str = "general",
        importance: int = 3,
        origin: str = "user_direct_input",
    ) -> MemoryModel:
        return await asyncio.to_thread(
            self._sync_create_memory,
            user_id,
            content,
            memory_type,
            category,
            importance,
            origin,
        )

    async def confirm_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        return await asyncio.to_thread(self._sync_confirm_memory, user_id, memory_id)

    async def reject_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        return await asyncio.to_thread(self._sync_reject_memory, user_id, memory_id)

    async def correct_memory(
        self,
        user_id: UUID,
        memory_id: UUID,
        content: str,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
    ) -> Optional[MemoryModel]:
        return await asyncio.to_thread(
            self._sync_correct_memory,
            user_id,
            memory_id,
            content,
            memory_type,
            category,
            importance,
        )

    async def archive_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        return await asyncio.to_thread(self._sync_archive_memory, user_id, memory_id)

    async def restore_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        return await asyncio.to_thread(self._sync_restore_memory, user_id, memory_id)

    async def outdate_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        return await asyncio.to_thread(self._sync_outdate_memory, user_id, memory_id)

