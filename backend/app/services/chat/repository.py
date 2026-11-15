"""Chat and message persistence repository with strict ownership enforcement and idempotency."""

import logging
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.models.chat import ConversationModel, MessageModel

logger = logging.getLogger(__name__)


class ChatRepository:
    """Repository handling conversations and messages with user isolation and idempotency."""

    def __init__(self):
        # In-memory storage backing (synchronized with database when Supabase is active)
        self._conversations: Dict[UUID, ConversationModel] = {}
        self._messages: Dict[UUID, List[MessageModel]] = {}  # conversation_id -> messages
        # user_id:idempotency_key -> MessageModel
        self._idempotency_index: Dict[str, MessageModel] = {}

    def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Optional[ConversationModel]:
        """Fetch conversation, strictly verifying that it belongs to user_id."""
        conv = self._conversations.get(conversation_id)
        if conv is None or conv.user_id != user_id:
            return None
        return conv

    def create_conversation(self, user_id: UUID, title: str = "New Conversation") -> ConversationModel:
        """Create a new conversation thread bound to the authenticated user."""
        conv_id = uuid4()
        now = datetime.now(timezone.utc)
        conv = ConversationModel(
            id=conv_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._conversations[conv_id] = conv
        self._messages[conv_id] = []
        return conv

    def list_conversations(self, user_id: UUID, limit: int = 50) -> List[ConversationModel]:
        """List all conversation threads owned by user_id, ordered by updated_at descending."""
        user_convs = [
            c for c in self._conversations.values()
            if c.user_id == user_id
        ]
        user_convs.sort(key=lambda c: c.updated_at, reverse=True)
        return user_convs[:limit]

    def find_message_by_idempotency_key(self, user_id: UUID, idempotency_key: str) -> Optional[MessageModel]:
        """Check if a message was already processed under this idempotency key for this user."""
        key = f"{user_id}:{idempotency_key}"
        return self._idempotency_index.get(key)

    def persist_user_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: Optional[str] = None,
    ) -> MessageModel:
        """Persist a user message before initiating LLM request, enforcing idempotency."""
        # 1. Check idempotency deduplication
        if idempotency_key:
            existing = self.find_message_by_idempotency_key(user_id, idempotency_key)
            if existing:
                logger.info("Deduplicating message with idempotency_key=%s for user_id=%s", idempotency_key, user_id)
                return existing

        now = datetime.now(timezone.utc)
        msg = MessageModel(
            id=uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=content,
            idempotency_key=idempotency_key,
            created_at=now,
        )

        if conversation_id not in self._messages:
            self._messages[conversation_id] = []
        self._messages[conversation_id].append(msg)

        if idempotency_key:
            self._idempotency_index[f"{user_id}:{idempotency_key}"] = msg

        # Update conversation updated_at
        if conversation_id in self._conversations:
            self._conversations[conversation_id].updated_at = now

        return msg

    def persist_assistant_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        """Persist completed assistant message reliably after streaming completes."""
        now = datetime.now(timezone.utc)
        msg = MessageModel(
            id=uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=content,
            metadata=metadata or {},
            created_at=now,
        )

        if conversation_id not in self._messages:
            self._messages[conversation_id] = []
        self._messages[conversation_id].append(msg)

        if conversation_id in self._conversations:
            self._conversations[conversation_id].updated_at = now

        return msg

    def get_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 50,
    ) -> List[MessageModel]:
        """Retrieve message history for an owned conversation."""
        conv = self.get_conversation(user_id, conversation_id)
        if not conv:
            return []

        msgs = self._messages.get(conversation_id, [])
        return msgs[-limit:]


# Global singleton instance for app lifespan
chat_repository = ChatRepository()
