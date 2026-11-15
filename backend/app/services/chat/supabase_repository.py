"""Supabase PostgreSQL chat repository adapter enforcing Row Level Security (RLS).

Guarantees:
- Enforces user isolation via Supabase PostgREST and PostgreSQL Row Level Security.
- Uses the caller's authenticated JWT token (auth.uid()) and public anon key.
- Never uses or exposes the Supabase service-role key for ordinary user operations.
- Atomic idempotency lifecycle claiming using database constraints.
- Full parity with BaseChatRepository interface.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import httpx

from app.models.chat import ChatRequestModel, ConversationModel, MessageModel
from app.services.chat.base_repository import BaseChatRepository

logger = logging.getLogger(__name__)


class SupabasePostgresChatRepository(BaseChatRepository):
    """Supabase PostgreSQL chat repository adapter interacting through PostgREST."""

    def __init__(
        self,
        supabase_url: str,
        supabase_anon_key: str,
        user_token: Optional[str] = None,
        timeout: float = 10.0,
        http_client: Optional[httpx.Client] = None,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.rest_url = f"{self.supabase_url}/rest/v1"
        self.supabase_anon_key = supabase_anon_key
        self.user_token = user_token
        self.timeout = timeout
        self._client = http_client

    def _get_headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        """Construct PostgREST headers with authenticated user bearer token and anon key."""
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

    def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        prefer: Optional[str] = None,
    ) -> httpx.Response:
        """Execute synchronous HTTP request to Supabase PostgREST."""
        url = f"{self.rest_url}{path}"
        headers = self._get_headers(prefer=prefer)

        if self._client:
            return self._client.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )

        with httpx.Client(timeout=self.timeout) as client:
            return client.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                headers=headers,
            )

    def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Optional[ConversationModel]:
        """Fetch conversation, strictly protected by Supabase RLS."""
        res = self._request(
            method="GET",
            path="/conversations",
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "select": "*",
            },
        )
        if res.status_code != 200:
            logger.warning("Supabase get_conversation error: %s - %s", res.status_code, res.text)
            return None

        rows = res.json()
        if not rows:
            return None

        r = rows[0]
        return ConversationModel(
            id=UUID(r["id"]),
            user_id=UUID(r["user_id"]),
            title=r["title"],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    def create_conversation(self, user_id: UUID, title: str = "New Conversation") -> ConversationModel:
        """Create a new conversation thread bound to the user in PostgreSQL."""
        payload = {
            "id": str(uuid4()),
            "user_id": str(user_id),
            "title": title,
        }
        res = self._request(
            method="POST",
            path="/conversations",
            json_data=payload,
            prefer="return=representation",
        )
        if res.status_code not in (200, 201):
            logger.error("Failed to create conversation in Supabase: %s - %s", res.status_code, res.text)
            raise RuntimeError(f"Database error creating conversation: {res.text}")

        rows = res.json()
        r = rows[0]
        return ConversationModel(
            id=UUID(r["id"]),
            user_id=UUID(r["user_id"]),
            title=r["title"],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    def list_conversations(self, user_id: UUID, limit: int = 50) -> List[ConversationModel]:
        """List conversation threads owned by user_id, ordered by updated_at descending."""
        res = self._request(
            method="GET",
            path="/conversations",
            params={
                "user_id": f"eq.{user_id}",
                "order": "updated_at.desc",
                "limit": str(limit),
                "select": "*",
            },
        )
        if res.status_code != 200:
            logger.warning("Supabase list_conversations error: %s - %s", res.status_code, res.text)
            return []

        rows = res.json()
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

    def get_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 50,
    ) -> List[MessageModel]:
        """Retrieve chronological message history for an owned conversation."""
        # Ensure conversation exists and belongs to user
        conv = self.get_conversation(user_id, conversation_id)
        if not conv:
            return []

        res = self._request(
            method="GET",
            path="/messages",
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "order": "created_at.asc",
                "limit": str(limit),
                "select": "*",
            },
        )
        if res.status_code != 200:
            logger.warning("Supabase get_messages error: %s - %s", res.status_code, res.text)
            return []

        rows = res.json()
        return [
            MessageModel(
                id=UUID(r["id"]),
                conversation_id=UUID(r["conversation_id"]),
                user_id=UUID(r["user_id"]),
                role=r["role"],
                content=r["content"],
                idempotency_key=r.get("idempotency_key"),
                metadata=r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else json.loads(r.get("metadata") or "{}"),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def get_message_by_id(self, user_id: UUID, message_id: UUID) -> Optional[MessageModel]:
        """Fetch a single message by ID, verifying user ownership via RLS."""
        res = self._request(
            method="GET",
            path="/messages",
            params={
                "id": f"eq.{message_id}",
                "user_id": f"eq.{user_id}",
                "select": "*",
            },
        )
        if res.status_code != 200:
            return None

        rows = res.json()
        if not rows:
            return None

        r = rows[0]
        return MessageModel(
            id=UUID(r["id"]),
            conversation_id=UUID(r["conversation_id"]),
            user_id=UUID(r["user_id"]),
            role=r["role"],
            content=r["content"],
            idempotency_key=r.get("idempotency_key"),
            metadata=r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else json.loads(r.get("metadata") or "{}"),
            created_at=datetime.fromisoformat(r["created_at"]),
        )

    def persist_user_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: Optional[str] = None,
    ) -> MessageModel:
        """Persist user message in PostgreSQL, reusing existing message on idempotency match."""
        if idempotency_key:
            res_existing = self._request(
                method="GET",
                path="/messages",
                params={
                    "user_id": f"eq.{user_id}",
                    "idempotency_key": f"eq.{idempotency_key}",
                    "select": "*",
                },
            )
            if res_existing.status_code == 200:
                rows = res_existing.json()
                if rows:
                    r = rows[0]
                    return MessageModel(
                        id=UUID(r["id"]),
                        conversation_id=UUID(r["conversation_id"]),
                        user_id=UUID(r["user_id"]),
                        role=r["role"],
                        content=r["content"],
                        idempotency_key=r.get("idempotency_key"),
                        metadata=r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else json.loads(r.get("metadata") or "{}"),
                        created_at=datetime.fromisoformat(r["created_at"]),
                    )

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": str(uuid4()),
            "conversation_id": str(conversation_id),
            "user_id": str(user_id),
            "role": "user",
            "content": content,
            "idempotency_key": idempotency_key,
            "metadata": {},
        }
        res = self._request(
            method="POST",
            path="/messages",
            json_data=payload,
            prefer="return=representation",
        )
        if res.status_code not in (200, 201):
            # If 409 Conflict due to race condition on idempotency_key
            if idempotency_key and res.status_code in (409, 400):
                existing = self._request(
                    method="GET",
                    path="/messages",
                    params={"user_id": f"eq.{user_id}", "idempotency_key": f"eq.{idempotency_key}", "select": "*"},
                )
                if existing.status_code == 200 and existing.json():
                    r = existing.json()[0]
                    return MessageModel(
                        id=UUID(r["id"]),
                        conversation_id=UUID(r["conversation_id"]),
                        user_id=UUID(r["user_id"]),
                        role=r["role"],
                        content=r["content"],
                        idempotency_key=r.get("idempotency_key"),
                        metadata=r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {},
                        created_at=datetime.fromisoformat(r["created_at"]),
                    )
            logger.error("Failed to insert message into Supabase: %s - %s", res.status_code, res.text)
            raise RuntimeError(f"Database error inserting message: {res.text}")

        # Update conversation updated_at
        self._request(
            method="PATCH",
            path="/conversations",
            params={"id": f"eq.{conversation_id}", "user_id": f"eq.{user_id}"},
            json_data={"updated_at": now_iso},
        )

        rows = res.json()
        r = rows[0]
        return MessageModel(
            id=UUID(r["id"]),
            conversation_id=UUID(r["conversation_id"]),
            user_id=UUID(r["user_id"]),
            role=r["role"],
            content=r["content"],
            idempotency_key=r.get("idempotency_key"),
            metadata=r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {},
            created_at=datetime.fromisoformat(r["created_at"]),
        )

    def persist_assistant_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        """Persist completed assistant message reliably into Supabase PostgreSQL."""
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": str(uuid4()),
            "conversation_id": str(conversation_id),
            "user_id": str(user_id),
            "role": "assistant",
            "content": content,
            "metadata": metadata or {},
        }
        res = self._request(
            method="POST",
            path="/messages",
            json_data=payload,
            prefer="return=representation",
        )
        if res.status_code not in (200, 201):
            logger.error("Failed to insert assistant message: %s - %s", res.status_code, res.text)
            raise RuntimeError(f"Database error inserting assistant message: {res.text}")

        # Update conversation timestamp
        self._request(
            method="PATCH",
            path="/conversations",
            params={"id": f"eq.{conversation_id}", "user_id": f"eq.{user_id}"},
            json_data={"updated_at": now_iso},
        )

        rows = res.json()
        r = rows[0]
        return MessageModel(
            id=UUID(r["id"]),
            conversation_id=UUID(r["conversation_id"]),
            user_id=UUID(r["user_id"]),
            role=r["role"],
            content=r["content"],
            metadata=r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {},
            created_at=datetime.fromisoformat(r["created_at"]),
        )

    def get_chat_request(self, user_id: UUID, idempotency_key: str) -> Optional[ChatRequestModel]:
        """Fetch request lifecycle record by user_id and idempotency_key from Supabase."""
        res = self._request(
            method="GET",
            path="/chat_requests",
            params={
                "user_id": f"eq.{user_id}",
                "idempotency_key": f"eq.{idempotency_key}",
                "select": "*",
            },
        )
        if res.status_code != 200:
            return None

        rows = res.json()
        if not rows:
            return None

        r = rows[0]
        return ChatRequestModel(
            user_id=UUID(r["user_id"]),
            idempotency_key=r["idempotency_key"],
            conversation_id=UUID(r["conversation_id"]),
            status=r["status"],
            user_message_id=UUID(r["user_message_id"]),
            assistant_message_id=UUID(r["assistant_message_id"]) if r.get("assistant_message_id") else None,
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    def claim_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> Tuple[bool, ChatRequestModel]:
        """Atomically claim a chat request in Supabase PostgreSQL.

        Uses PostgreSQL primary key constraint (user_id, idempotency_key).
        Returns (True, ChatRequestModel) if successfully claimed with status='processing'.
        Returns (False, ChatRequestModel) if already claimed / duplicate key conflict.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": str(user_id),
            "idempotency_key": idempotency_key,
            "conversation_id": str(conversation_id),
            "status": "processing",
            "user_message_id": str(user_message_id),
        }

        res = self._request(
            method="POST",
            path="/chat_requests",
            json_data=payload,
            prefer="return=representation",
        )

        if res.status_code in (200, 201):
            rows = res.json()
            r = rows[0]
            return True, ChatRequestModel(
                user_id=UUID(r["user_id"]),
                idempotency_key=r["idempotency_key"],
                conversation_id=UUID(r["conversation_id"]),
                status=r["status"],
                user_message_id=UUID(r["user_message_id"]),
                assistant_message_id=UUID(r["assistant_message_id"]) if r.get("assistant_message_id") else None,
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
            )

        # Conflict (409) or constraint error (400) indicates already claimed
        if res.status_code in (409, 400):
            existing = self.get_chat_request(user_id, idempotency_key)
            if existing:
                return False, existing

        logger.error("Unexpected error claiming chat request in Supabase: %s - %s", res.status_code, res.text)
        raise RuntimeError(f"Database error claiming chat request: {res.text}")

    def update_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        status: str,
        assistant_message_id: Optional[UUID] = None,
    ) -> None:
        """Update request status and associate assistant message in Supabase."""
        now_iso = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "status": status,
            "updated_at": now_iso,
        }
        if assistant_message_id:
            payload["assistant_message_id"] = str(assistant_message_id)

        res = self._request(
            method="PATCH",
            path="/chat_requests",
            params={
                "user_id": f"eq.{user_id}",
                "idempotency_key": f"eq.{idempotency_key}",
            },
            json_data=payload,
        )
        if res.status_code not in (200, 204):
            logger.warning("Failed to update chat request status in Supabase: %s - %s", res.status_code, res.text)
