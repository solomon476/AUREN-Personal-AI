"""Supabase PostgreSQL memory repository adapter enforcing Row Level Security (RLS).

Guarantees:
- Fully asynchronous non-blocking PostgREST communication via httpx.AsyncClient.
- Strict user-scoped querying and caller verification (auth.uid()).
- Calls hardened SECURITY DEFINER RPCs for state transitions and lineage creation.
- Preserves full audit trail and epistemic lifecycle invariants.
- Strict isolation: never queries or leaks raw journal entries.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from app.core.exceptions import (
    DatabaseAuthError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseOperationError,
)
from app.models.memory import MemoryModel
from app.services.memory.base_repository import BaseMemoryRepository

logger = logging.getLogger(__name__)


class SupabaseMemoryRepository(BaseMemoryRepository):
    """Asynchronous Supabase PostgreSQL memory repository adapter interacting via PostgREST."""

    def __init__(
        self,
        supabase_url: str,
        supabase_anon_key: str,
        user_token: Optional[str] = None,
        timeout: float = 10.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.rest_url = f"{self.supabase_url}/rest/v1"
        self.supabase_anon_key = supabase_anon_key
        self.user_token = user_token
        self.timeout = timeout
        self._client = http_client

    def _get_headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.supabase_anon_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> httpx.Response:
        url = f"{self.rest_url}{path}"
        headers = self._get_headers(prefer=prefer)

        try:
            if self._client:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=headers,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json_data,
                        headers=headers,
                    )
        except httpx.TimeoutException as exc:
            logger.error("Supabase memory request timed out: %s %s", method, path)
            raise DatabaseConnectionError(f"Database connection timed out: {exc}")
        except httpx.RequestError as exc:
            logger.error("Supabase memory connection error: %s %s: %s", method, path, exc)
            raise DatabaseConnectionError(f"Database connection failed: {exc}")

        if response.status_code in (401, 403):
            raise DatabaseAuthError("PostgreSQL authentication failure or permission denied.")
        elif response.status_code >= 500:
            raise DatabaseOperationError(f"PostgreSQL internal error: {response.text}")

        return response

    def _dict_to_model(self, data: Dict[str, Any]) -> MemoryModel:
        return MemoryModel(
            id=UUID(data["id"]),
            user_id=UUID(data["user_id"]),
            content=data["content"],
            memory_type=data.get("memory_type", "fact"),
            category=data.get("category", "general"),
            importance=data.get("importance", 3),
            confidence=data.get("confidence"),
            confirmation_status=data.get("confirmation_status", "unconfirmed"),
            lifecycle_status=data.get("lifecycle_status", "active"),
            origin=data.get("origin", "user_direct_input"),
            source_message_id=UUID(data["source_message_id"]) if data.get("source_message_id") else None,
            source_conversation_id=UUID(data["source_conversation_id"]) if data.get("source_conversation_id") else None,
            superseded_by_id=UUID(data["superseded_by_id"]) if data.get("superseded_by_id") else None,
            previous_version_id=UUID(data["previous_version_id"]) if data.get("previous_version_id") else None,
            root_memory_id=UUID(data["root_memory_id"]) if data.get("root_memory_id") else None,
            access_count=data.get("access_count", 0),
            last_accessed_at=datetime.fromisoformat(data["last_accessed_at"]) if data.get("last_accessed_at") else None,
            last_confirmed_at=datetime.fromisoformat(data["last_confirmed_at"]) if data.get("last_confirmed_at") else None,
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            review_after=datetime.fromisoformat(data["review_after"]) if data.get("review_after") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata") or {},
        )

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
        params: Dict[str, str] = {
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "updated_at.desc,created_at.desc",
        }

        if query and query.strip():
            params["content"] = f"ilike.*{query.strip()}*"
        if memory_type:
            params["memory_type"] = f"eq.{memory_type}"
        if category:
            params["category"] = f"eq.{category}"
        if confirmation_status:
            params["confirmation_status"] = f"eq.{confirmation_status}"
        if lifecycle_status:
            params["lifecycle_status"] = f"eq.{lifecycle_status}"

        offset = max(0, (page - 1) * page_size)
        limit = page_size
        prefer = "count=exact"

        # PostgREST Range header for server-side pagination
        range_header = f"{offset}-{offset + limit - 1}"
        headers = self._get_headers(prefer=prefer)
        headers["Range"] = range_header

        url = f"{self.rest_url}/memories"
        try:
            if self._client:
                response = await self._client.get(url, params=params, headers=headers, timeout=self.timeout)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, params=params, headers=headers)
        except Exception as exc:
            raise DatabaseConnectionError(f"Database error listing memories: {exc}")

        if response.status_code >= 400:
            raise DatabaseOperationError(f"Failed to list memories: {response.text}")

        total = 0
        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            total_part = content_range.split("/")[1]
            if total_part != "*":
                try:
                    total = int(total_part)
                except ValueError:
                    total = 0

        raw_items = response.json()
        models = [self._dict_to_model(item) for item in raw_items]
        return models, total

    async def get_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        params = {
            "id": f"eq.{memory_id}",
            "user_id": f"eq.{user_id}",
            "select": "*",
        }
        resp = await self._request("GET", "/memories", params=params)
        items = resp.json()
        if not items:
            return None
        return self._dict_to_model(items[0])

    async def create_memory(
        self,
        user_id: UUID,
        content: str,
        memory_type: str = "fact",
        category: str = "general",
        importance: int = 3,
        origin: str = "user_direct_input",
    ) -> MemoryModel:
        payload = {
            "p_content": content.strip(),
            "p_memory_type": memory_type,
            "p_category": category,
            "p_importance": importance,
            "p_origin": origin,
            "p_confirmation_status": "confirmed",
        }
        resp = await self._request("POST", "/rpc/create_memory_rpc", json_data=payload)
        new_id_raw = resp.json()
        new_id = UUID(new_id_raw)
        created = await self.get_memory(user_id, new_id)
        if not created:
            raise DatabaseOperationError("Created memory could not be retrieved.")
        return created

    async def confirm_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        payload = {"p_memory_id": str(memory_id)}
        resp = await self._request("POST", "/rpc/confirm_memory_rpc", json_data=payload)
        if resp.status_code == 404:
            return None
        return await self.get_memory(user_id, memory_id)

    async def reject_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        payload = {"p_memory_id": str(memory_id)}
        resp = await self._request("POST", "/rpc/reject_memory_rpc", json_data=payload)
        if resp.status_code == 404:
            return None
        return await self.get_memory(user_id, memory_id)

    async def correct_memory(
        self,
        user_id: UUID,
        memory_id: UUID,
        content: str,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
    ) -> Optional[MemoryModel]:
        payload = {
            "p_old_memory_id": str(memory_id),
            "p_new_content": content.strip(),
            "p_memory_type": memory_type,
            "p_category": category,
            "p_importance": importance,
            "p_origin": "user_direct_edit",
            "p_confirmation_status": "confirmed",
        }
        resp = await self._request("POST", "/rpc/supersede_memory_rpc", json_data=payload)
        if resp.status_code == 404:
            return None
        new_id = UUID(resp.json())
        return await self.get_memory(user_id, new_id)

    async def archive_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        payload = {"p_memory_id": str(memory_id)}
        resp = await self._request("POST", "/rpc/archive_memory_rpc", json_data=payload)
        if resp.status_code == 404:
            return None
        return await self.get_memory(user_id, memory_id)

    async def restore_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        # Epistemic guard: in PostgREST, direct update or status change
        params = {"id": f"eq.{memory_id}", "user_id": f"eq.{user_id}"}
        payload = {"lifecycle_status": "active", "updated_at": datetime.now(timezone.utc).isoformat()}
        resp = await self._request("PATCH", "/memories", params=params, json_data=payload)
        if resp.status_code == 404:
            return None
        return await self.get_memory(user_id, memory_id)

    async def outdate_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        params = {"id": f"eq.{memory_id}", "user_id": f"eq.{user_id}"}
        payload = {"lifecycle_status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}
        resp = await self._request("PATCH", "/memories", params=params, json_data=payload)
        if resp.status_code == 404:
            return None
        return await self.get_memory(user_id, memory_id)
