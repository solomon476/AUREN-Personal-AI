"""Supabase / PostgreSQL PostgREST implementation of the Connections Repository."""

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import httpx

from app.core.exceptions import DatabaseOperationError
from app.models.connections import ConnectionModel, LocationSharingToggleRequest, LocationUpdateRequest
from app.services.connections.base_repository import BaseConnectionRepository

logger = logging.getLogger(__name__)


class SupabaseConnectionRepository(BaseConnectionRepository):
    """PostgREST-backed connections repository using user JWT."""

    def __init__(self, supabase_url: str, supabase_anon_key: str, user_token: str):
        self.base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": supabase_anon_key,
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _row_to_model(self, r: Dict[str, Any]) -> ConnectionModel:
        return ConnectionModel(
            id=UUID(r["id"]),
            user_id=UUID(r["user_id"]),
            connected_user_id=UUID(r["connected_user_id"]) if r.get("connected_user_id") else None,
            invite_code=r["invite_code"],
            display_name=r["display_name"],
            avatar_initials=r.get("avatar_initials", "TC"),
            status=r["status"],
            location_sharing_active=bool(r.get("location_sharing_active", False)),
            location_sharing_expires_at=datetime.fromisoformat(r["location_sharing_expires_at"]) if r.get("location_sharing_expires_at") else None,
            last_latitude=float(r["last_latitude"]) if r.get("last_latitude") is not None else None,
            last_longitude=float(r["last_longitude"]) if r.get("last_longitude") is not None else None,
            last_location_updated_at=datetime.fromisoformat(r["last_location_updated_at"]) if r.get("last_location_updated_at") else None,
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    async def list_connections(self, user_id: UUID) -> List[ConnectionModel]:
        params = {
            "or": f"(user_id.eq.{user_id},connected_user_id.eq.{user_id})",
            "status": "in.(pending,accepted)",
            "order": "created_at.desc",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/connections", headers=self.headers, params=params)
            if resp.status_code != 200:
                raise DatabaseOperationError(f"Failed to list connections: {resp.text}")
            return [self._row_to_model(r) for r in resp.json()]

    async def create_invite(self, user_id: UUID, display_name: str) -> ConnectionModel:
        conn_id = uuid4()
        invite_code = f"aur_{secrets.token_hex(4)}"
        initials = "".join([part[0].upper() for part in display_name.split()[:2]]) or "TC"
        now_iso = datetime.now(timezone.utc).isoformat()

        record = {
            "id": str(conn_id),
            "user_id": str(user_id),
            "invite_code": invite_code,
            "display_name": display_name,
            "avatar_initials": initials,
            "status": "pending",
            "location_sharing_active": False,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{self.base_url}/connections", headers=self.headers, json=record)
            if resp.status_code not in (200, 201):
                raise DatabaseOperationError(f"Failed to create connection invite: {resp.text}")
            rows = resp.json()
            return self._row_to_model(rows[0])

    async def accept_invite(self, user_id: UUID, invite_code: str) -> ConnectionModel:
        params = {
            "invite_code": f"eq.{invite_code.strip()}",
            "status": "eq.pending",
            "select": "*",
        }
        now_iso = datetime.now(timezone.utc).isoformat()

        async with httpx.AsyncClient(timeout=10.0) as client:
            find_resp = await client.get(f"{self.base_url}/connections", headers=self.headers, params=params)
            if find_resp.status_code != 200 or not find_resp.json():
                raise ValueError("Invalid or expired invitation code.")

            existing = find_resp.json()[0]
            if existing["user_id"] == str(user_id):
                raise ValueError("You cannot accept your own invitation code.")

            update_patch = {
                "connected_user_id": str(user_id),
                "status": "accepted",
                "updated_at": now_iso,
            }
            patch_resp = await client.patch(
                f"{self.base_url}/connections?id=eq.{existing['id']}",
                headers=self.headers,
                json=update_patch,
            )
            if patch_resp.status_code not in (200, 204):
                raise DatabaseOperationError(f"Failed to accept connection invite: {patch_resp.text}")
            rows = patch_resp.json()
            return self._row_to_model(rows[0])

    async def decline_invite(self, user_id: UUID, connection_id: UUID) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        params = f"id=eq.{connection_id}"
        update_patch = {"status": "declined", "updated_at": now_iso}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(f"{self.base_url}/connections?{params}", headers=self.headers, json=update_patch)
            return resp.status_code in (200, 204)

    async def revoke_connection(self, user_id: UUID, connection_id: UUID) -> bool:
        params = f"id=eq.{connection_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{self.base_url}/connections?{params}", headers=self.headers)
            return resp.status_code in (200, 204)

    async def toggle_location_sharing(self, user_id: UUID, payload: LocationSharingToggleRequest) -> bool:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_at = (now + timedelta(minutes=payload.duration_minutes or 60)).isoformat() if payload.enabled else None

        update_patch = {
            "location_sharing_active": payload.enabled,
            "location_sharing_expires_at": expires_at,
            "updated_at": now_iso,
        }

        params = f"user_id=eq.{user_id}"
        if payload.target_connection_ids:
            ids_str = ",".join(str(cid) for cid in payload.target_connection_ids)
            params += f"&id=in.({ids_str})"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(f"{self.base_url}/connections?{params}", headers=self.headers, json=update_patch)
            return resp.status_code in (200, 204)

    async def update_location(self, user_id: UUID, payload: LocationUpdateRequest) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        update_patch = {
            "last_latitude": payload.latitude,
            "last_longitude": payload.longitude,
            "last_location_updated_at": now_iso,
        }
        params = f"user_id=eq.{user_id}&location_sharing_active=eq.true"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(f"{self.base_url}/connections?{params}", headers=self.headers, json=update_patch)
            return resp.status_code in (200, 204)

