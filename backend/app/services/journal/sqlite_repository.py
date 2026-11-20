"""SQLite repository for AUREN Private Journal."""

import asyncio
from datetime import date, datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.models.journal import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryUpdate,
)
from app.services.journal.base_repository import BaseJournalRepository

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_DB_PATH = DB_DIR / "auren_journal.db"


class SQLiteJournalRepository(BaseJournalRepository):
    """SQLite implementation of BaseJournalRepository for local development and testing."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_database(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT,
                    content TEXT NOT NULL,
                    mood TEXT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    is_private INTEGER NOT NULL DEFAULT 1,
                    entry_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_journal_user_entry_date 
                ON journal_entries(user_id, entry_date DESC);
            """)
            conn.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> JournalEntryResponse:
        tags_raw = row["tags"]
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except Exception:
            tags = []

        entry_date_str = row["entry_date"]
        parsed_date = date.fromisoformat(entry_date_str[:10])

        return JournalEntryResponse(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            title=row["title"],
            content=row["content"],
            mood=row["mood"],
            tags=tags,
            is_private=bool(row["is_private"]),
            entry_date=parsed_date,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def list_entries(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        mood: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Tuple[List[JournalEntryResponse], int]:
        def _execute() -> Tuple[List[JournalEntryResponse], int]:
            conditions = ["user_id = ?"]
            params: List[Any] = [str(user_id)]

            if start_date:
                conditions.append("entry_date >= ?")
                params.append(start_date.isoformat())
            if end_date:
                conditions.append("entry_date <= ?")
                params.append(end_date.isoformat())
            if mood:
                conditions.append("mood = ?")
                params.append(mood)
            if query:
                conditions.append("(content LIKE ? OR title LIKE ?)")
                q = f"%{query}%"
                params.extend([q, q])

            where_clause = " WHERE " + " AND ".join(conditions)

            with self._get_connection() as conn:
                count_cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM journal_entries {where_clause}", params)
                total = count_cursor.fetchone()["cnt"]

                offset = (page - 1) * page_size
                data_query = f"""
                    SELECT * FROM journal_entries 
                    {where_clause}
                    ORDER BY entry_date DESC, created_at DESC
                    LIMIT ? OFFSET ?
                """
                data_params = params + [page_size, offset]
                rows = conn.execute(data_query, data_params).fetchall()
                items = [self._row_to_entry(r) for r in rows]
                return items, total

        return await asyncio.to_thread(_execute)

    async def get_entry(self, user_id: UUID, entry_id: UUID) -> Optional[JournalEntryResponse]:
        def _execute() -> Optional[JournalEntryResponse]:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM journal_entries WHERE id = ? AND user_id = ?",
                    (str(entry_id), str(user_id)),
                ).fetchone()
                return self._row_to_entry(row) if row else None

        return await asyncio.to_thread(_execute)

    async def create_entry(self, user_id: UUID, payload: JournalEntryCreate) -> JournalEntryResponse:
        def _execute() -> JournalEntryResponse:
            entry_id = str(uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()
            entry_date_iso = (payload.entry_date or date.today()).isoformat()
            tags_json = json.dumps(payload.tags or [])

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO journal_entries (
                        id, user_id, title, content, mood, tags, is_private, entry_date, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        str(user_id),
                        payload.title,
                        payload.content,
                        payload.mood,
                        tags_json,
                        1 if payload.is_private else 0,
                        entry_date_iso,
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()

                row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
                return self._row_to_entry(row)

        return await asyncio.to_thread(_execute)

    async def update_entry(
        self,
        user_id: UUID,
        entry_id: UUID,
        payload: JournalEntryUpdate,
    ) -> Optional[JournalEntryResponse]:
        def _execute() -> Optional[JournalEntryResponse]:
            updates = []
            params: List[Any] = []

            if payload.title is not None:
                updates.append("title = ?")
                params.append(payload.title)
            if payload.content is not None:
                updates.append("content = ?")
                params.append(payload.content)
            if payload.mood is not None:
                updates.append("mood = ?")
                params.append(payload.mood)
            if payload.tags is not None:
                updates.append("tags = ?")
                params.append(json.dumps(payload.tags))
            if payload.is_private is not None:
                updates.append("is_private = ?")
                params.append(1 if payload.is_private else 0)
            if payload.entry_date is not None:
                updates.append("entry_date = ?")
                params.append(payload.entry_date.isoformat())

            if not updates:
                # Return current entry without modifications
                return self._row_to_entry(
                    self._get_connection().execute(
                        "SELECT * FROM journal_entries WHERE id = ? AND user_id = ?",
                        (str(entry_id), str(user_id)),
                    ).fetchone()
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            updates.append("updated_at = ?")
            params.append(now_iso)

            params.extend([str(entry_id), str(user_id)])

            with self._get_connection() as conn:
                res = conn.execute(
                    f"UPDATE journal_entries SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
                    params,
                )
                conn.commit()
                if res.rowcount == 0:
                    return None

                row = conn.execute(
                    "SELECT * FROM journal_entries WHERE id = ? AND user_id = ?",
                    (str(entry_id), str(user_id)),
                ).fetchone()
                return self._row_to_entry(row) if row else None

        return await asyncio.to_thread(_execute)

    async def delete_entry(self, user_id: UUID, entry_id: UUID) -> bool:
        def _execute() -> bool:
            with self._get_connection() as conn:
                res = conn.execute(
                    "DELETE FROM journal_entries WHERE id = ? AND user_id = ?",
                    (str(entry_id), str(user_id)),
                )
                conn.commit()
                return res.rowcount > 0

        return await asyncio.to_thread(_execute)
