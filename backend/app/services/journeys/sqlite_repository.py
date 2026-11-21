"""SQLite implementation of the Journey Repository for tests and local fallback."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import List, Optional, Tuple, Union
from uuid import UUID, uuid4

from app.models.journeys import JourneyCreateRequest, JourneyModel
from app.services.journeys.base_repository import BaseJourneyRepository

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_DB_PATH = DB_DIR / "auren_journeys.db"


class SQLiteJourneyRepository(BaseJourneyRepository):
    """File-backed SQLite journey store for local development and testing."""

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
                CREATE TABLE IF NOT EXISTS journeys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    distance_meters REAL NOT NULL DEFAULT 0.0,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    avg_speed_kmh REAL DEFAULT 0.0,
                    is_offline_recorded INTEGER NOT NULL DEFAULT 0,
                    is_team_assignment INTEGER NOT NULL DEFAULT 0,
                    assignment_site TEXT,
                    assignment_purpose TEXT,
                    assignment_notes TEXT,
                    check_in_time TEXT,
                    check_in_coords TEXT,
                    points TEXT NOT NULL DEFAULT '[]',
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> JourneyModel:
        return JourneyModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            title=row["title"],
            status=row["status"],
            distance_meters=float(row["distance_meters"]),
            duration_seconds=int(row["duration_seconds"]),
            avg_speed_kmh=float(row["avg_speed_kmh"]) if row["avg_speed_kmh"] is not None else 0.0,
            is_offline_recorded=bool(row["is_offline_recorded"]),
            is_team_assignment=bool(row["is_team_assignment"]),
            assignment_site=row["assignment_site"],
            assignment_purpose=row["assignment_purpose"],
            assignment_notes=row["assignment_notes"],
            check_in_time=datetime.fromisoformat(row["check_in_time"]) if row["check_in_time"] else None,
            check_in_coords=row["check_in_coords"],
            points=json.loads(row["points"] or "[]"),
            idempotency_key=row["idempotency_key"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    def _sync_list_journeys(self, user_id: UUID, limit: int, offset: int) -> Tuple[List[JourneyModel], int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM journeys WHERE user_id = ?",
                (str(user_id),),
            )
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT * FROM journeys WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (str(user_id), limit, offset),
            )
            rows = cursor.fetchall()
            return [self._row_to_model(r) for r in rows], total

    async def list_journeys(self, user_id: UUID, limit: int = 50, offset: int = 0) -> Tuple[List[JourneyModel], int]:
        return await asyncio.to_thread(self._sync_list_journeys, user_id, limit, offset)

    def _sync_get_journey_by_id(self, user_id: UUID, journey_id: UUID) -> Optional[JourneyModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM journeys WHERE id = ? AND user_id = ?",
                (str(journey_id), str(user_id)),
            )
            row = cursor.fetchone()
            return self._row_to_model(row) if row else None

    async def get_journey_by_id(self, user_id: UUID, journey_id: UUID) -> Optional[JourneyModel]:
        return await asyncio.to_thread(self._sync_get_journey_by_id, user_id, journey_id)

    def _sync_create_or_sync_journey(self, user_id: UUID, payload: JourneyCreateRequest) -> JourneyModel:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Idempotency deduplication
            if payload.idempotency_key:
                cursor.execute(
                    "SELECT * FROM journeys WHERE user_id = ? AND idempotency_key = ?",
                    (str(user_id), payload.idempotency_key),
                )
                existing = cursor.fetchone()
                if existing:
                    return self._row_to_model(existing)

            journey_id = payload.id or uuid4()
            now_iso = datetime.now(timezone.utc).isoformat()
            completed_iso = payload.completed_at.isoformat() if payload.completed_at else (now_iso if payload.status == "completed" else None)
            check_in_iso = payload.check_in_time.isoformat() if payload.check_in_time else None

            cursor.execute(
                """
                INSERT INTO journeys (
                    id, user_id, title, status, distance_meters, duration_seconds, avg_speed_kmh,
                    is_offline_recorded, is_team_assignment, assignment_site, assignment_purpose,
                    assignment_notes, check_in_time, check_in_coords, points, idempotency_key, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(journey_id),
                    str(user_id),
                    payload.title,
                    payload.status,
                    payload.distance_meters,
                    payload.duration_seconds,
                    payload.avg_speed_kmh or 0.0,
                    1 if payload.is_offline_recorded else 0,
                    1 if payload.is_team_assignment else 0,
                    payload.assignment_site,
                    payload.assignment_purpose,
                    payload.assignment_notes,
                    check_in_iso,
                    payload.check_in_coords,
                    json.dumps(payload.points),
                    payload.idempotency_key,
                    now_iso,
                    completed_iso,
                ),
            )
            conn.commit()

            cursor.execute("SELECT * FROM journeys WHERE id = ?", (str(journey_id),))
            return self._row_to_model(cursor.fetchone())

    async def create_or_sync_journey(self, user_id: UUID, payload: JourneyCreateRequest) -> JourneyModel:
        return await asyncio.to_thread(self._sync_create_or_sync_journey, user_id, payload)

    def _sync_delete_journey(self, user_id: UUID, journey_id: UUID) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM journeys WHERE id = ? AND user_id = ?",
                (str(journey_id), str(user_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def delete_journey(self, user_id: UUID, journey_id: UUID) -> bool:
        return await asyncio.to_thread(self._sync_delete_journey, user_id, journey_id)
