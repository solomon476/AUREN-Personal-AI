"""Abstract Base Class for Chat and Message Repositories.

Defines the asynchronous contract for conversation, message, and idempotency persistence
across PostgreSQL (Supabase) and local SQLite backends.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from uuid import UUID

from app.models.chat import ChatRequestModel, ConversationModel, MessageModel


class BaseChatRepository(ABC):
    """Abstract interface for chat persistence and lifecycle tracking.

    Guarantees:
    - Thread/conversation ownership enforcement on all reads and writes.
    - Idempotency lifecycle tracking to prevent duplicate message storage and duplicate AI invocations.
    - Message history retrieval ordered chronologically.
    - Data persistence across process restarts.
    - Asynchronous non-blocking contract.
    """

    @abstractmethod
    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Optional[ConversationModel]:
        """Fetch conversation, strictly verifying that it belongs to user_id."""
        pass

    @abstractmethod
    async def create_conversation(
        self,
        user_id: UUID,
        title: str = "New Conversation",
        conversation_id: Optional[UUID] = None,
    ) -> ConversationModel:
        """Create a new conversation thread bound to the authenticated user."""
        pass

    @abstractmethod
    async def get_or_create_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID,
        title: str = "New Conversation",
    ) -> ConversationModel:
        """Atomically get or create a conversation thread with a specific ID."""
        pass

    @abstractmethod
    async def list_conversations(self, user_id: UUID, limit: int = 50) -> List[ConversationModel]:
        """List conversation threads owned by user_id, ordered by updated_at descending."""
        pass

    @abstractmethod
    async def get_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 50,
    ) -> List[MessageModel]:
        """Retrieve message history for an owned conversation."""
        pass

    @abstractmethod
    async def get_message_by_id(self, user_id: UUID, message_id: UUID) -> Optional[MessageModel]:
        """Fetch a single message by ID, verifying caller ownership."""
        pass

    @abstractmethod
    async def persist_user_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        idempotency_key: Optional[str] = None,
    ) -> MessageModel:
        """Persist user message, reusing existing message if idempotency_key already exists."""
        pass

    @abstractmethod
    async def persist_assistant_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        """Persist completed assistant message reliably."""
        pass

    @abstractmethod
    async def update_assistant_message(
        self,
        user_id: UUID,
        message_id: UUID,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        """Update an existing assistant message's content and metadata (for retry recovery)."""
        pass

    @abstractmethod
    async def get_chat_request(self, user_id: UUID, idempotency_key: str) -> Optional[ChatRequestModel]:
        """Fetch request lifecycle record by user_id and idempotency_key."""
        pass

    @abstractmethod
    async def claim_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        conversation_id: UUID,
        user_message_id: UUID,
        request_fingerprint: Optional[str] = None,
    ) -> Tuple[bool, ChatRequestModel]:
        """Atomically claim a chat request.

        Returns:
            (True, ChatRequestModel) if successfully claimed with status='processing'.
            (False, ChatRequestModel) if already claimed / existing record found.
        """
        pass

    @abstractmethod
    async def find_assistant_message_for_request(
        self,
        user_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
    ) -> Optional[MessageModel]:
        """Find an assistant message in a conversation produced for a specific user message."""
        pass

    @abstractmethod
    async def transition_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        from_statuses: List[str],
        to_status: str,
    ) -> bool:
        """Atomically transition request status conditional on its current state (for retry recovery).

        Returns:
            True if row was atomically updated, False if current status was not in from_statuses.
        """
        pass

    @abstractmethod
    async def update_chat_request_status(
        self,
        user_id: UUID,
        idempotency_key: str,
        status: str,
        assistant_message_id: Optional[UUID] = None,
    ) -> None:
        """Update request status (completed, failed, interrupted) and associate assistant message."""
        pass

    @abstractmethod
    async def reconcile_chat_request(
        self,
        user_id: UUID,
        idempotency_key: str,
        assistant_message_id: UUID,
    ) -> ChatRequestModel:
        """Reconcile an incomplete request to completed status with an existing assistant message."""
        pass
