"""Domain and API schemas for Chat, Conversations, Messages, and Idempotency Requests."""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator


def compute_request_fingerprint(
    user_id: UUID,
    content: str,
    conversation_id: Optional[UUID] = None,
) -> str:
    """Compute immutable SHA-256 fingerprint binding user, normalized content, and conversation."""
    normalized_content = "\n".join(line.rstrip() for line in content.strip().splitlines())
    conv_part = str(conversation_id) if conversation_id else "none"
    payload = f"user:{str(user_id)}|conv:{conv_part}|content:{normalized_content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    message_count: int = 0


class ChatRequestModel(BaseModel):
    """Lifecycle entity tracking in-flight and completed chat requests for strict idempotency."""

    user_id: UUID
    idempotency_key: str
    conversation_id: UUID
    status: str = Field(..., description="'processing', 'completed', 'failed', 'interrupted'")
    user_message_id: UUID
    assistant_message_id: Optional[UUID] = None
    request_fingerprint: Optional[str] = None
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


class ConversationRenameRequest(BaseModel):
    """Request payload to rename an existing conversation thread."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="New title for the conversation thread",
    )

    @field_validator("title")
    @classmethod
    def validate_title_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Conversation title cannot be empty or whitespace only.")
        return stripped


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
