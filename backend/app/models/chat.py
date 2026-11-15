"""Domain and API schemas for Chat, Conversations, and Messages."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class MessageModel(BaseModel):
    """Represents a persisted message entity."""

    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    user_id: UUID
    role: str = Field(..., description="'system', 'user', or 'assistant'")
    content: str
    idempotency_key: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationModel(BaseModel):
    """Represents a conversation thread."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    title: str = "New Conversation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatCompletionRequest(BaseModel):
    """Incoming request payload for streaming chat completions."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User text prompt for the assistant",
    )
    conversation_id: Optional[UUID] = Field(
        default=None,
        description="Target conversation ID. If omitted, a new thread is created automatically.",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Client-generated unique ID to prevent duplicates on network reconnection.",
    )


class ConversationCreateRequest(BaseModel):
    """Request payload to explicitly create a conversation thread."""

    title: Optional[str] = Field(default="New Conversation", max_length=200)


class ConversationResponse(BaseModel):
    """API view for conversation threads."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageResponse(BaseModel):
    """API view for individual messages."""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
