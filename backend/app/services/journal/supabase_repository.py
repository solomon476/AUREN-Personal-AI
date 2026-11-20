"""Supabase PostgREST repository for AUREN Private Journal."""

from datetime import date, datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from app.core.exceptions import DatabaseAuthError, DatabaseConnectionError, DatabaseError
from app.models.journal import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryUpdate,
)
from app.services.journal.base_repository import BaseJournalRepository
from app.services.journal.integrity import compute_journal_signature, verify_journal_signature

logger = logging.getLogger(__name__)


class SupabaseJournalRepository(BaseJournalRepository):
    """Supabase PostgREST implementation of BaseJournalRepository enforcing user token RLS."""

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
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
        else:
            headers["Authorization"] = f"Bearer {self.supabase_anon_key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> httpx.Response:
        url = f"{self.rest_url}/{endpoint.lstrip('/')}"
        headers = self._get_headers(prefer)

        try:
            if self._client:
                return await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
        except httpx.TimeoutException as exc:
            raise DatabaseConnectionError(f"Supabase connection timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise DatabaseConnectionError(f"Supabase request network error: {exc}") from exc

    def _dict_to_entry(self, data: Dict[str, Any]) -> JournalEntryResponse:
        tags = data.get("tags") or []
        if isinstance(tags, str):
            import json
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []

        entry_date_raw = data.get("entry_date")
        if isinstance(entry_date_raw, str):
            parsed_date = date.fromisoformat(entry_date_raw[:10])
        elif isinstance(entry_date_raw, date):
            parsed_date = entry_date_raw
        else:
            parsed_date = date.today()

        sig = data.get("integrity_signature")
        integrity_verified = None
        if sig:
            integrity_verified = verify_journal_signature(
                entry_id=UUID(str(data["id"])),
                user_id=UUID(str(data["user_id"])),
                title=data.get("title"),
                content=data["content"],
                mood=data.get("mood"),
                tags=tags,
                entry_date=parsed_date,
                signature=sig,
                is_private=bool(data.get("is_private", True)),
            )

        return JournalEntryResponse(
            id=UUID(str(data["id"])),
            user_id=UUID(str(data["user_id"])),
            title=data.get("title"),
            content=data["content"],
            mood=data.get("mood"),
            tags=tags,
            is_private=bool(data.get("is_private", True)),
            entry_date=parsed_date,
            integrity_signature=sig,
            integrity_verified=integrity_verified,
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
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
        offset = (page - 1) * page_size
        params: Dict[str, Any] = {
            "user_id": f"eq.{user_id}",
            "order": "entry_date.desc,created_at.desc",
            "limit": str(page_size),
            "offset": str(offset),
        }

        if start_date:
            params["entry_date"] = f"gte.{start_date.isoformat()}"
        if end_date:
            params["entry_date"] = f"lte.{end_date.isoformat()}"
        if mood:
            params["mood"] = f"eq.{mood}"
        if query:
            params["or"] = f"(content.ilike.*{query}*,title.ilike.*{query}*)"

        resp = await self._request("GET", "journal_entries", params=params, prefer="count=exact")
        if resp.status_code in (401, 403):
            raise DatabaseAuthError("Unauthorized accessing journal records.")
        if resp.status_code != 200:
            raise DatabaseError(f"Failed to query journal entries: {resp.text}")

        content_range = resp.headers.get("content-range", "")
        total = 0
        if "/" in content_range:
            parts = content_range.split("/")
            if parts[1].isdigit():
                total = int(parts[1])

        records = resp.json()
        return [self._dict_to_entry(r) for r in records], total

    async def get_entry(self, user_id: UUID, entry_id: UUID) -> Optional[JournalEntryResponse]:
        params = {
            "id": f"eq.{entry_id}",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        }
        resp = await self._request("GET", "journal_entries", params=params)
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not items:
            return None
        return self._dict_to_entry(items[0])

    async def create_entry(self, user_id: UUID, payload: JournalEntryCreate) -> JournalEntryResponse:
        from uuid import uuid4
        new_id = uuid4()
        entry_date_val = payload.entry_date or date.today()
        entry_date_iso = entry_date_val.isoformat()
        is_priv = True if payload.is_private is None else bool(payload.is_private)
        clean_tags = payload.tags or []

        sig = compute_journal_signature(
            entry_id=new_id,
            user_id=user_id,
            title=payload.title,
            content=payload.content,
            mood=payload.mood,
            tags=clean_tags,
            entry_date=entry_date_val,
            is_private=is_priv,
        )

        body = {
            "id": str(new_id),
            "user_id": str(user_id),
            "title": payload.title,
            "content": payload.content,
            "mood": payload.mood,
            "tags": clean_tags,
            "is_private": is_priv,
            "entry_date": entry_date_iso,
            "integrity_signature": sig,
        }
        resp = await self._request("POST", "journal_entries", json_body=body, prefer="return=representation")
        if resp.status_code == 400 and "integrity_signature" in resp.text:
            body.pop("integrity_signature", None)
            resp = await self._request("POST", "journal_entries", json_body=body, prefer="return=representation")

        if resp.status_code in (401, 403):
            raise DatabaseAuthError("Unauthorized creating journal entry.")
        if resp.status_code not in (200, 201):
            raise DatabaseError(f"Failed to create journal entry: {resp.text}")

        items = resp.json()
        return self._dict_to_entry(items[0])

    async def update_entry(
        self,
        user_id: UUID,
        entry_id: UUID,
        payload: JournalEntryUpdate,
    ) -> Optional[JournalEntryResponse]:
        current = await self.get_entry(user_id, entry_id)
        if not current:
            return None

        body: Dict[str, Any] = {}
        new_title = payload.title if payload.title is not None else current.title
        new_content = payload.content if payload.content is not None else current.content
        new_mood = payload.mood if payload.mood is not None else current.mood
        new_tags = payload.tags if payload.tags is not None else current.tags
        new_is_priv = payload.is_private if payload.is_private is not None else current.is_private
        new_entry_date = payload.entry_date if payload.entry_date is not None else current.entry_date

        if payload.title is not None:
            body["title"] = payload.title
        if payload.content is not None:
            body["content"] = payload.content
        if payload.mood is not None:
            body["mood"] = payload.mood
        if payload.tags is not None:
            body["tags"] = payload.tags
        if payload.is_private is not None:
            body["is_private"] = payload.is_private
        if payload.entry_date is not None:
            body["entry_date"] = payload.entry_date.isoformat()

        if not body:
            return current

        new_sig = compute_journal_signature(
            entry_id=entry_id,
            user_id=user_id,
            title=new_title,
            content=new_content,
            mood=new_mood,
            tags=new_tags,
            entry_date=new_entry_date,
            is_private=new_is_priv,
        )
        body["integrity_signature"] = new_sig

        params = {
            "id": f"eq.{entry_id}",
            "user_id": f"eq.{user_id}",
        }
        resp = await self._request(
            "PATCH",
            "journal_entries",
            params=params,
            json_body=body,
            prefer="return=representation",
        )
        if resp.status_code == 400 and "integrity_signature" in resp.text:
            body.pop("integrity_signature", None)
            resp = await self._request(
                "PATCH",
                "journal_entries",
                params=params,
                json_body=body,
                prefer="return=representation",
            )
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not items:
            return None
        return self._dict_to_entry(items[0])

    async def delete_entry(self, user_id: UUID, entry_id: UUID) -> bool:
        params = {
            "id": f"eq.{entry_id}",
            "user_id": f"eq.{user_id}",
        }
        resp = await self._request("DELETE", "journal_entries", params=params)
        return resp.status_code in (200, 204)
