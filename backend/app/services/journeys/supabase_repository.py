"""Supabase / PostgreSQL PostgREST implementation of the Journey Repository."""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import httpx

from app.core.exceptions import DatabaseOperationError
from app.models.journeys import JourneyCreateRequest, JourneyModel
from app.services.journeys.base_repository import BaseJourneyRepository

logger = logging.getLogger(__name__)


class SupabaseJourneyRepository(BaseJourneyRepository):
    """PostgREST-backed journey repository using user JWT."""

    def __init__(self, supabase_url: str, supabase_anon_key: str, user_token: str):
        self.base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": supabase_anon_key,
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _row_to_model(self, r: Dict[str, Any]) -> JourneyModel:
        pts = r.get("points")
        if isinstance(pts, str):
            try:
                pts = json.loads(pts)
            except Exception:
                pts = []
        elif not isinstance(pts, list):
            pts = []

        return JourneyModel(
            id=UUID(r["id"]),
            user_id=UUID(r["user_id"]),
            title=r["title"],
            status=r["status"],
            distance_meters=float(r.get("distance_meters", 0.0)),
            duration_seconds=int(r.get("duration_seconds", 0)),
            avg_speed_kmh=float(r.get("avg_speed_kmh", 0.0)) if r.get("avg_speed_kmh") is not None else 0.0,
            is_offline_recorded=bool(r.get("is_offline_recorded", False)),
            is_team_assignment=bool(r.get("is_team_assignment", False)),
            assignment_site=r.get("assignment_site"),
            assignment_purpose=r.get("assignment_purpose"),
            assignment_notes=r.get("assignment_notes"),
            check_in_time=datetime.fromisoformat(r["check_in_time"]) if r.get("check_in_time") else None,
            check_in_coords=r.get("check_in_coords"),
            points=pts,
            idempotency_key=r.get("idempotency_key"),
            created_at=datetime.fromisoformat(r["created_at"]),
            completed_at=datetime.fromisoformat(r["completed_at"]) if r.get("completed_at") else None,
        )

    async def list_journeys(self, user_id: UUID, limit: int = 50, offset: int = 0) -> Tuple[List[JourneyModel], int]:
        headers = dict(self.headers)
        headers["Prefer"] = "count=exact"
        params = {
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
            "limit": str(limit),
            "offset": str(offset),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/journeys", headers=headers, params=params)
            if resp.status_code != 200:
                raise DatabaseOperationError(f"Failed to list journeys: {resp.text}")

            content_range = resp.headers.get("content-range", "")
            total = int(content_range.split("/")[-1]) if "/" in content_range and content_range.split("/")[-1].isdigit() else len(resp.json())
            items = [self._row_to_model(r) for r in resp.json()]
            return items, total

    async def get_journey_by_id(self, user_id: UUID, journey_id: UUID) -> Optional[JourneyModel]:
        params = {
            "id": f"eq.{journey_id}",
            "user_id": f"eq.{user_id}",
            "select": "*",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/journeys", headers=self.headers, params=params)
            if resp.status_code != 200:
                return None
            rows = resp.json()
            return self._row_to_model(rows[0]) if rows else None

    async def create_or_sync_journey(self, user_id: UUID, payload: JourneyCreateRequest) -> JourneyModel:
        # Check idempotency
        if payload.idempotency_key:
            params = {
                "user_id": f"eq.{user_id}",
                "idempotency_key": f"eq.{payload.idempotency_key}",
                "select": "*",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/journeys", headers=self.headers, params=params)
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows:
                        return self._row_to_model(rows[0])

        journey_id = payload.id or uuid4()
        now_iso = datetime.now(timezone.utc).isoformat()
        completed_iso = payload.completed_at.isoformat() if payload.completed_at else (now_iso if payload.status == "completed" else None)

        record = {
            "id": str(journey_id),
            "user_id": str(user_id),
            "title": payload.title,
            "status": payload.status,
            "distance_meters": payload.distance_meters,
            "duration_seconds": payload.duration_seconds,
            "avg_speed_kmh": payload.avg_speed_kmh or 0.0,
            "is_offline_recorded": payload.is_offline_recorded,
            "is_team_assignment": payload.is_team_assignment,
            "assignment_site": payload.assignment_site,
            "assignment_purpose": payload.assignment_purpose,
            "assignment_notes": payload.assignment_notes,
            "check_in_time": payload.check_in_time.isoformat() if payload.check_in_time else None,
            "check_in_coords": payload.check_in_coords,
            "points": payload.points,
            "idempotency_key": payload.idempotency_key,
            "created_at": now_iso,
            "completed_at": completed_iso,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{self.base_url}/journeys", headers=self.headers, json=record)
            if resp.status_code not in (200, 201):
                raise DatabaseOperationError(f"Failed to create journey: {resp.text}")
            rows = resp.json()
            return self._row_to_model(rows[0])

    async def delete_journey(self, user_id: UUID, journey_id: UUID) -> bool:
        params = {
            "id": f"eq.{journey_id}",
            "user_id": f"eq.{user_id}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{self.base_url}/journeys", headers=self.headers, params=params)
            return resp.status_code in (200, 204)

