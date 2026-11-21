"""SQLite implementation of the Connection Repository for tests and local fallback."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sqlite3
from typing import List, Optional, Union
from uuid import UUID, uuid4

from app.models.connections import ConnectionModel, LocationSharingToggleRequest, LocationUpdateRequest
from app.services.connections.base_repository import BaseConnectionRepository

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_DB_PATH = DB_DIR / "auren_connections.db"


class SQLiteConnectionRepository(BaseConnectionRepository):
    """File-backed SQLite connections store for local development and testing."""

    def __init__(self, db_path: Optional[Union[Path, str]] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    connected_user_id TEXT,
                    invite_code TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    avatar_initials TEXT NOT NULL DEFAULT 'TC',
                    status TEXT NOT NULL DEFAULT 'pending',
                    location_sharing_active INTEGER NOT NULL DEFAULT 0,
                    location_sharing_expires_at TEXT,
                    last_latitude REAL,
                    last_longitude REAL,
                    last_location_updated_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> ConnectionModel:
        return ConnectionModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            connected_user_id=UUID(row["connected_user_id"]) if row["connected_user_id"] else None,
            invite_code=row["invite_code"],
            display_name=row["display_name"],
            avatar_initials=row["avatar_initials"],
            status=row["status"],
            location_sharing_active=bool(row["location_sharing_active"]),
            location_sharing_expires_at=datetime.fromisoformat(row["location_sharing_expires_at"]) if row["location_sharing_expires_at"] else None,
            last_latitude=float(row["last_latitude"]) if row["last_latitude"] is not None else None,
            last_longitude=float(row["last_longitude"]) if row["last_longitude"] is not None else None,
            last_location_updated_at=datetime.fromisoformat(row["last_location_updated_at"]) if row["last_location_updated_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _sync_list_connections(self, user_id: UUID) -> List[ConnectionModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM connections
                WHERE (user_id = ? OR connected_user_id = ?)
                  AND status IN ('pending', 'accepted')
                ORDER BY created_at DESC
                """,
                (str(user_id), str(user_id)),
            )
            rows = cursor.fetchall()
            return [self._row_to_model(r) for r in rows]

    async def list_connections(self, user_id: UUID) -> List[ConnectionModel]:
        return await asyncio.to_thread(self._sync_list_connections, user_id)

    def _sync_create_invite(self, user_id: UUID, display_name: str) -> ConnectionModel:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conn_id = uuid4()
            invite_code = f"aur_{secrets.token_hex(4)}"
            initials = "".join([part[0].upper() for part in display_name.split()[:2]]) or "TC"
            now_iso = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                INSERT INTO connections (
                    id, user_id, connected_user_id, invite_code, display_name,
                    avatar_initials, status, location_sharing_active, location_sharing_expires_at,
                    last_latitude, last_longitude, last_location_updated_at, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, ?, ?, 'pending', 0, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (str(conn_id), str(user_id), invite_code, display_name, initials, now_iso, now_iso),
            )
            conn.commit()

            cursor.execute("SELECT * FROM connections WHERE id = ?", (str(conn_id),))
            return self._row_to_model(cursor.fetchone())

    async def create_invite(self, user_id: UUID, display_name: str) -> ConnectionModel:
        return await asyncio.to_thread(self._sync_create_invite, user_id, display_name)

    def _sync_accept_invite(self, user_id: UUID, invite_code: str) -> ConnectionModel:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM connections WHERE invite_code = ? AND status = 'pending'",
                (invite_code.strip(),),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Invalid or expired invitation code.")

            if str(user_id) == row["user_id"]:
                raise ValueError("You cannot accept your own invitation code.")

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                UPDATE connections
                SET connected_user_id = ?, status = 'accepted', updated_at = ?
                WHERE id = ?
                """,
                (str(user_id), now_iso, row["id"]),
            )
            conn.commit()

            cursor.execute("SELECT * FROM connections WHERE id = ?", (row["id"],))
            return self._row_to_model(cursor.fetchone())

    async def accept_invite(self, user_id: UUID, invite_code: str) -> ConnectionModel:
        return await asyncio.to_thread(self._sync_accept_invite, user_id, invite_code)

    def _sync_decline_invite(self, user_id: UUID, connection_id: UUID) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                UPDATE connections
                SET status = 'declined', updated_at = ?
                WHERE id = ? AND (user_id = ? OR connected_user_id = ?)
                """,
                (now_iso, str(connection_id), str(user_id), str(user_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def decline_invite(self, user_id: UUID, connection_id: UUID) -> bool:
        return await asyncio.to_thread(self._sync_decline_invite, user_id, connection_id)

    def _sync_revoke_connection(self, user_id: UUID, connection_id: UUID) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM connections
                WHERE id = ? AND (user_id = ? OR connected_user_id = ?)
                """,
                (str(connection_id), str(user_id), str(user_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def revoke_connection(self, user_id: UUID, connection_id: UUID) -> bool:
        return await asyncio.to_thread(self._sync_revoke_connection, user_id, connection_id)

    def _sync_toggle_location_sharing(self, user_id: UUID, payload: LocationSharingToggleRequest) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            expires_at = (now + timedelta(minutes=payload.duration_minutes or 60)).isoformat() if payload.enabled else None

            if payload.target_connection_ids:
                targets = [str(cid) for cid in payload.target_connection_ids]
                placeholders = ",".join("?" for _ in targets)
                cursor.execute(
                    f"""
                    UPDATE connections
                    SET location_sharing_active = ?, location_sharing_expires_at = ?, updated_at = ?
                    WHERE id IN ({placeholders}) AND user_id = ?
                    """,
                    [1 if payload.enabled else 0, expires_at, now_iso, *targets, str(user_id)],
                )
            else:
                cursor.execute(
                    """
                    UPDATE connections
                    SET location_sharing_active = ?, location_sharing_expires_at = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (1 if payload.enabled else 0, expires_at, now_iso, str(user_id)),
                )
            conn.commit()
            return True

    async def toggle_location_sharing(self, user_id: UUID, payload: LocationSharingToggleRequest) -> bool:
        return await asyncio.to_thread(self._sync_toggle_location_sharing, user_id, payload)

    def _sync_update_location(self, user_id: UUID, payload: LocationUpdateRequest) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                UPDATE connections
                SET last_latitude = ?, last_longitude = ?, last_location_updated_at = ?
                WHERE user_id = ? AND location_sharing_active = 1
                """,
                (payload.latitude, payload.longitude, now_iso, str(user_id)),
            )
            conn.commit()
            return True

    async def update_location(self, user_id: UUID, payload: LocationUpdateRequest) -> bool:
        return await asyncio.to_thread(self._sync_update_location, user_id, payload)
