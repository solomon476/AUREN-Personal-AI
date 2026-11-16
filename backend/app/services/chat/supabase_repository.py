"""Supabase PostgreSQL chat repository adapter enforcing Row Level Security (RLS).

Guarantees:
- Fully asynchronous non-blocking PostgREST communication via httpx.AsyncClient.
- Enforces user isolation via Supabase PostgREST and PostgreSQL Row Level Security.
- Uses the caller's authenticated JWT token (auth.uid()) and public anon key.
- Never uses or exposes the Supabase service-role key for ordinary user operations.
- Explicit database error handling distinguishing auth, network, server, and missing records.
- Atomic idempotency lifecycle claiming using database constraints.
- Full parity with BaseChatRepository asynchronous interface.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import httpx

from app.core.exceptions import (
    DatabaseAuthError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseOperationError,
    IdempotencyConflictError,
)
from app.models.chat import ChatRequestModel, ConversationModel, MessageModel
from app.services.chat.base_repository import BaseChatRepository

logger = logging.getLogger(__name__)


class SupabasePostgresChatRepository(BaseChatRepository):
    """Asynchronous Supabase PostgreSQL chat repository adapter interacting through PostgREST."""

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

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        prefer: Optional[str] = None,
        allowed_error_codes: Optional[Tuple[int, ...]] = None,
    ) -> httpx.Response:
        """Execute non-blocking asynchronous HTTP request to Supabase PostgREST with strict error categorization."""
        url = f"{self.rest_url}{path}"
        headers = self._get_headers(prefer=prefer)

        try:
            if self._client:
                res = await self._client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    res = await client.request(
                        method=method,
                        url=url,
                        json=json_data,
                        params=params,
                        headers=headers,
                    )
        except httpx.RequestError as exc:
            logger.error("Supabase network connection failure (%s %s): %s", method, url, exc)
            raise DatabaseConnectionError(
                "Unable to connect to database service. Please check your network connection.",
                technical_details=str(exc),
            ) from exc

        # Handle specific error status codes
        if allowed_error_codes and res.status_code in allowed_error_codes:
            return res

        if res.status_code in (401, 403):
            logger.error("Supabase PostgREST auth/RLS error (%s %s) [%d]: %s", method, url, res.status_code, res.text)
            raise DatabaseAuthError(
                "Database authentication or authorization failure.",
                technical_details=f"Status {res.status_code}: {res.text}",
            )

        if res.status_code >= 500:
            logger.error("Supabase server failure (%s %s) [%d]: %s", method, url, res.status_code, res.text)
            raise DatabaseOperationError(
                "A database service error occurred. Please try again later.",
                technical_details=f"Status {res.status_code}: {res.text}",
            )

        if res.status_code not in (200, 201, 204):
            logger.error("Supabase unexpected response (%s %s) [%d]: %s", method, url, res.status_code, res.text)
            raise DatabaseOperationError(
                "Unexpected database response code.",
                technical_details=f"Status {res.status_code}: {res.text}",
            )

        return res

    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Optional[ConversationModel]:
        """Fetch conversation, strictly protected by Supabase RLS."""
        res = await self._request(
            method="GET",
            path="/conversations",
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "select": "*",
            },
        )
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

    async def create_conversation(
        self,
        user_id: UUID,
        title: str = "New Conversation",
        conversation_id: Optional[UUID] = None,
    ) -> ConversationModel:
        """Create a new conversation thread bound to the user in PostgreSQL."""
        conv_id = conversation_id or uuid4()
        payload = {
            "id": str(conv_id),
            "user_id": str(user_id),
            "title": title,
        }
        res = await self._request(
            method="POST",
            path="/conversations",
            json_data=payload,
            prefer="return=representation",
        )
        rows = res.json()
        r = rows[0]
        return ConversationModel(
            id=UUID(r["id"]),
            user_id=UUID(r["user_id"]),
            title=r["title"],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
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

        payload = {
            "id": str(conversation_id),
            "user_id": str(user_id),
            "title": title,
        }
        res = await self._request(
            method="POST",
            path="/conversations",
            json_data=payload,
            prefer="return=representation",
            allowed_error_codes=(409, 400),
        )
        if res.status_code in (200, 201) and res.json():
            r = res.json()[0]
            return ConversationModel(
                id=UUID(r["id"]),
                user_id=UUID(r["user_id"]),
                title=r["title"],
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
            )

        # In case of duplicate/conflict, fetch existing
        conv = await self.get_conversation(user_id, conversation_id)
        if conv:
            return conv
        raise DatabaseOperationError("Failed to resolve or create conversation.")

    async def list_conversations(self, user_id: UUID, limit: int = 50) -> List[ConversationModel]:
        """List conversation threads owned by user_id, ordered by updated_at descending."""
        res = await self._request(
            method="GET",
            path="/conversations",
            params={
                "user_id": f"eq.{user_id}",
                "order": "updated_at.desc",
                "limit": str(limit),
                "select": "*",
            },
        )
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

    async def get_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 50,
    ) -> List[MessageModel]:
        """Retrieve chronological message history for an owned conversation."""
        conv = await self.get_conversation(user_id, conversation_id)
        if not conv:
            return []

        res = await self._request(
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

    async def get_message_by_id(self, user_id: UUID, message_id: UUID) -> Optional[MessageModel]:
        """Fetch a single message by ID, verifying user ownership via RLS."""
        res = await self._request(
            method="GET",
            path="/messages",
            params={
                "id": f"eq.{message_id}",
                "user_id": f"eq.{user_id}",
                "select": "*",
            },
        )
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

    async def persist_user_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: Optional[str] = None,
    ) -> MessageModel:
        """Persist user message in PostgreSQL, reusing existing message on idempotency match."""
        if idempotency_key:
            res_existing = await self._request(
                method="GET",
                path="/messages",
                params={
                    "user_id": f"eq.{user_id}",
                    "idempotency_key": f"eq.{idempotency_key}",
                    "select": "*",
                },
            )
            rows = res_existing.json()
            if rows:
                r = rows[0]
                existing_normalized = "\n".join(line.rstrip() for line in r["content"].strip().splitlines())
                incoming_normalized = "\n".join(line.rstrip() for line in content.strip().splitlines())
                if existing_normalized != incoming_normalized:
                    raise IdempotencyConflictError(
                        f"Idempotency key '{idempotency_key}' was already used with different message content."
                    )
                if UUID(r["conversation_id"]) != conversation_id:
                    raise IdempotencyConflictError(
                        f"Idempotency key '{idempotency_key}' was already used with a different conversation."
                    )
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
        res = await self._request(
            method="POST",
            path="/messages",
            json_data=payload,
            prefer="return=representation",
            allowed_error_codes=(409, 400),
        )

        if res.status_code in (409, 400) and idempotency_key:
            # Race condition: duplicate key already inserted
            existing = await self._request(
                method="GET",
                path="/messages",
                params={"user_id": f"eq.{user_id}", "idempotency_key": f"eq.{idempotency_key}", "select": "*"},
            )
            if existing.json():
                r = existing.json()[0]
                existing_normalized = "\n".join(line.rstrip() for line in r["content"].strip().splitlines())
                incoming_normalized = "\n".join(line.rstrip() for line in content.strip().splitlines())
                if existing_normalized != incoming_normalized or UUID(r["conversation_id"]) != conversation_id:
                    raise IdempotencyConflictError(
                        f"Idempotency key '{idempotency_key}' was already used with conflicting parameters."
                    )
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

        # Update conversation updated_at
        await self._request(
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

    async def persist_assistant_message(
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
        res = await self._request(
            method="POST",
            path="/messages",
            json_data=payload,
            prefer="return=representation",
        )
        # Update conversation timestamp
        await self._request(
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

    def _row_to_chat_request(self, r: dict) -> ChatRequestModel:
        return ChatRequestModel(
            user_id=UUID(r["user_id"]),
            idempotency_key=r["idempotency_key"],
            conversation_id=UUID(r["conversation_id"]),
            status=r["status"],
            user_message_id=UUID(r["user_message_id"]),
            assistant_message_id=UUID(r["assistant_message_id"]) if r.get("assistant_message_id") else None,
            request_fingerprint=r.get("request_fingerprint"),
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    async def get_chat_request(self, user_id: UUID, idempotency_key: str) -> Optional[ChatRequestModel]:
        """Fetch request lifecycle record by user_id and idempotency_key from Supabase."""
        res = await self._request(
            method="GET",
            path="/chat_requests",
            params={
                "user_id": f"eq.{user_id}",
                "idempotency_key": f"eq.{idempotency_key}",
                "select": "*",
            },
        )
        rows = res.json()
        if not rows:
            return None

        return self._row_to_chat_request(rows[0])

    async def claim_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        conversation_id: UUID,
        user_message_id: UUID,
        request_fingerprint: Optional[str] = None,
    ) -> Tuple[bool, ChatRequestModel]:
        """Atomically claim a chat request in Supabase PostgreSQL via RPC claim_chat_request.

        Enforces caller identity (auth.uid()), strict 64-character hexadecimal fingerprint
        validation, and conversation/message ownership at the database level.
        Exclusive RPC creation path: direct table INSERT is revoked.
        """
        rpc_payload = {
            "p_idempotency_key": idempotency_key,
            "p_conversation_id": str(conversation_id),
            "p_user_message_id": str(user_message_id),
            "p_request_fingerprint": request_fingerprint,
        }
        res_rpc = await self._request(
            method="POST",
            path="/rpc/claim_chat_request",
            json_data=rpc_payload,
            allowed_error_codes=(404, 400, 409),
        )
        if res_rpc.status_code == 404:
            raise DatabaseOperationError("Required database RPC 'claim_chat_request' not found. Please apply database migrations.")

        if res_rpc.status_code == 409 or (res_rpc.status_code == 400 and "conflicting" in res_rpc.text.lower()):
            raise IdempotencyConflictError(
                f"Idempotency key '{idempotency_key}' was already used with conflicting request content."
            )

        if res_rpc.status_code in (200, 201) and res_rpc.json():
            data = res_rpc.json()
            if isinstance(data, dict) and "claimed" in data and "request" in data:
                return data["claimed"], self._row_to_chat_request(data["request"])

        raise DatabaseOperationError(f"Unexpected response claiming chat request: {res_rpc.status_code}")

    async def find_assistant_message_for_request(
        self,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> Optional[MessageModel]:
        """Find an assistant message in a conversation produced for a specific user message."""
        res = await self._request(
            method="GET",
            path="/messages",
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "role": "eq.assistant",
                "order": "created_at.desc",
                "select": "*",
            },
        )
        rows = res.json()
        for r in rows:
            meta = r.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if meta.get("user_message_id") == str(user_message_id):
                return MessageModel(
                    id=UUID(r["id"]),
                    conversation_id=UUID(r["conversation_id"]),
                    user_id=UUID(r["user_id"]),
                    role=r["role"],
                    content=r["content"],
                    idempotency_key=r.get("idempotency_key"),
                    metadata=meta,
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
        return None

    async def update_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        status: str,
        assistant_message_id: Optional[UUID] = None,
    ) -> None:
        """Update request status and associate assistant message in Supabase via dedicated RPCs.

        Direct UPDATE table access is revoked; operations execute exclusively through
        validated SECURITY DEFINER stored procedures enforcing the lifecycle transition matrix.
        """
        if status == "completed":
            if not assistant_message_id:
                raise ValueError("assistant_message_id is required to complete chat request")
            res_rpc = await self._request(
                method="POST",
                path="/rpc/complete_chat_request",
                json_data={
                    "p_idempotency_key": idempotency_key,
                    "p_assistant_message_id": str(assistant_message_id),
                },
                allowed_error_codes=(404, 400),
            )
            if res_rpc.status_code == 404:
                raise DatabaseOperationError("Required database RPC 'complete_chat_request' not found. Please apply migrations.")
            if res_rpc.status_code == 400:
                raise DatabaseOperationError(f"Database rejected completion transition: {res_rpc.text}")
            if res_rpc.status_code in (200, 201):
                return
        elif status == "failed":
            res_rpc = await self._request(
                method="POST",
                path="/rpc/fail_chat_request",
                json_data={"p_idempotency_key": idempotency_key},
                allowed_error_codes=(404, 400),
            )
            if res_rpc.status_code == 404:
                raise DatabaseOperationError("Required database RPC 'fail_chat_request' not found. Please apply migrations.")
            if res_rpc.status_code == 400:
                raise DatabaseOperationError(f"Database rejected fail transition: {res_rpc.text}")
            if res_rpc.status_code in (200, 201):
                return
        elif status == "interrupted":
            res_rpc = await self._request(
                method="POST",
                path="/rpc/interrupt_chat_request",
                json_data={
                    "p_idempotency_key": idempotency_key,
                    "p_assistant_message_id": str(assistant_message_id) if assistant_message_id else None,
                },
                allowed_error_codes=(404, 400),
            )
            if res_rpc.status_code == 404:
                raise DatabaseOperationError("Required database RPC 'interrupt_chat_request' not found. Please apply migrations.")
            if res_rpc.status_code == 400:
                raise DatabaseOperationError(f"Database rejected interrupt transition: {res_rpc.text}")
            if res_rpc.status_code in (200, 201):
                return
        else:
            raise ValueError(f"Unsupported status transition target: '{status}'")

        raise DatabaseOperationError(f"Unexpected response updating chat request status: {res_rpc.status_code}")

    async def reconcile_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        assistant_message_id: UUID,
    ) -> ChatRequestModel:
        """Reconcile an incomplete request to completed status via dedicated RPC reconcile_chat_request."""
        res_rpc = await self._request(
            method="POST",
            path="/rpc/reconcile_chat_request",
            json_data={
                "p_idempotency_key": idempotency_key,
                "p_assistant_message_id": str(assistant_message_id),
            },
            allowed_error_codes=(404, 400),
        )
        if res_rpc.status_code == 404:
            raise DatabaseOperationError("Required database RPC 'reconcile_chat_request' not found. Please apply migrations.")
        if res_rpc.status_code == 400:
            raise DatabaseOperationError(f"Reconciliation rejected by database: {res_rpc.text}")
        if res_rpc.status_code in (200, 201):
            return self._row_to_chat_request(res_rpc.json())
        raise DatabaseOperationError(f"Unexpected response reconciling chat request: {res_rpc.status_code}")

    async def update_assistant_message(
        self,
        user_id: UUID,
        message_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        """Update an existing assistant message's content and metadata (for retry recovery)."""
        payload = {
            "content": content,
            "metadata": metadata or {},
        }
        res = await self._request(
            method="PATCH",
            path="/messages",
            params={"id": f"eq.{message_id}", "user_id": f"eq.{user_id}"},
            json_data=payload,
            prefer="return=representation",
        )
        rows = res.json()
        if not rows:
            raise DatabaseOperationError(f"Assistant message {message_id} not found to update")
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

    async def transition_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        from_statuses: List[str],
        to_status: str,
    ) -> bool:
        """Atomically transition request status conditional on its current state (for retry recovery).

        Exclusively uses RPC retry_chat_request; direct PATCH table access is revoked.
        """
        if to_status == "processing" and any(s in from_statuses for s in ("failed", "interrupted")):
            res_rpc = await self._request(
                method="POST",
                path="/rpc/retry_chat_request",
                json_data={"p_idempotency_key": idempotency_key},
                allowed_error_codes=(404, 400),
            )
            if res_rpc.status_code == 404:
                raise DatabaseOperationError("Required database RPC 'retry_chat_request' not found. Please apply migrations.")
            if res_rpc.status_code == 400:
                raise DatabaseOperationError(f"Database rejected retry transition: {res_rpc.text}")
            if res_rpc.status_code in (200, 201):
                data = res_rpc.json()
                if isinstance(data, dict) and "transitioned" in data:
                    return bool(data["transitioned"])

        raise DatabaseOperationError(f"Unsupported conditional transition from {from_statuses} to '{to_status}'")

    async def search_memories_hybrid(
        self,
        user_id: UUID,
        query_text: str,
        query_embedding: Optional[List[float]] = None,
        limit: int = 5,
        min_similarity: float = 0.0,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        dimension: Optional[int] = None,
    ) -> List[Any]:
        """Invoke search_memories_hybrid_rpc via PostgREST."""
        from app.services.memory.models import MemorySearchResult

        payload: dict = {
            "p_query_text": query_text,
            "p_limit": limit,
            "p_min_similarity": min_similarity,
        }
        if query_embedding is not None:
            payload["p_query_embedding"] = f"[{','.join(str(x) for x in query_embedding)}]"
        if model is not None:
            payload["p_model"] = model
        if provider is not None:
            payload["p_provider"] = provider
        if version is not None:
            payload["p_version"] = version
        if dimension is not None:
            payload["p_dimension"] = dimension

        res = await self._request(
            method="POST",
            path="/rpc/search_memories_hybrid_rpc",
            json_data=payload,
            allowed_error_codes=(404, 400),
        )
        if res.status_code in (404, 400):
            logger.warning("search_memories_hybrid_rpc failed: %s", res.text)
            return []

        rows = res.json()
        return [
            MemorySearchResult(
                id=UUID(r["id"]),
                content=r["content"],
                memory_type=r["memory_type"],
                category=r["category"],
                importance=r["importance"],
                confidence=r.get("confidence"),
                confirmation_status=r["confirmation_status"],
                score=float(r["score"]),
            )
            for r in rows
        ]
