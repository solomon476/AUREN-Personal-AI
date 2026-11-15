"""API Router for chat completions, conversations, and message history."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.models.chat import (
    ChatCompletionRequest,
    ConversationCreateRequest,
    ConversationResponse,
    MessageResponse,
)
from app.models.user import AuthenticatedUser
from app.services.chat.chat_service import chat_service
from app.services.chat.repository import chat_repository

router = APIRouter(prefix="/chat", tags=["Chat & Conversations"])


@router.post(
    "/completions",
    summary="Stream Chat Completion",
    description="Stream real-time AI responses via Server-Sent Events (SSE). User message is persisted before streaming begins.",
)
async def stream_chat_completion(
    request: ChatCompletionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Initiate an SSE stream for chat interaction."""
    # 1. Validate request and resolve conversation with ownership enforcement BEFORE starting the stream
    conversation = chat_service.validate_and_resolve_conversation(current_user, request)

    # 2. Return SSE StreamingResponse
    stream_generator = chat_service.stream_chat_completion(current_user, conversation, request)

    return StreamingResponse(
        stream_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable proxy buffering in Nginx
        },
    )


@router.get(
    "/conversations",
    response_model=List[ConversationResponse],
    summary="List Conversations",
    description="List all active conversation threads owned by the authenticated caller.",
)
async def list_conversations(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[ConversationResponse]:
    """Return all conversations owned by the caller."""
    conversations = chat_repository.list_conversations(current_user.id)
    return [
        ConversationResponse(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=len(chat_repository.get_messages(current_user.id, c.id)),
        )
        for c in conversations
    ]


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Conversation",
    description="Explicitly initialize a new conversation thread.",
)
async def create_conversation(
    payload: ConversationCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ConversationResponse:
    """Create a new conversation thread bound to the user."""
    conv = chat_repository.create_conversation(current_user.id, title=payload.title or "New Conversation")
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[MessageResponse],
    summary="Get Conversation Messages",
    description="Retrieve chronological messages for an owned conversation.",
)
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[MessageResponse]:
    """Retrieve message history, enforcing caller ownership."""
    conv = chat_repository.get_conversation(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    messages = chat_repository.get_messages(current_user.id, conversation_id)
    return [
        MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            metadata=m.metadata,
        )
        for m in messages
    ]
