"""API Router for chat completions, conversations, and message history."""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.core.exceptions import (
    DatabaseAuthError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseOperationError,
    IdempotencyConflictError,
)
from app.core.security import get_current_user
from app.models.chat import (
    ChatCompletionRequest,
    ConversationCreateRequest,
    ConversationRenameRequest,
    ConversationResponse,
    MessageResponse,
)
from app.models.memory import MemoryContextItem, MessageContextResponse
from app.models.user import AuthenticatedUser
from app.services.chat.base_repository import BaseChatRepository
from app.services.chat.chat_service import chat_service
from app.services.chat.repository import get_chat_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat & Conversations"])


def get_user_chat_repository(current_user: AuthenticatedUser = Depends(get_current_user)) -> BaseChatRepository:
    """Dependency injecting repository configured for authenticated user."""
    return get_chat_repository(user_token=current_user.token)


@router.post(
    "/completions",
    summary="Stream Chat Completion",
    description="Stream real-time AI responses via Server-Sent Events (SSE). User message is persisted before streaming begins.",
)
async def stream_chat_completion(
    request: ChatCompletionRequest,
    raw_request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Initiate an SSE stream for chat interaction with heartbeat, timeout, and idempotency."""
    try:
        # 1. Validate request and resolve conversation with ownership enforcement BEFORE starting the stream
        conversation = await chat_service.validate_and_resolve_conversation(current_user, request)
    except IdempotencyConflictError as exc:
        logger.warning("Idempotency conflict in stream_chat_completion: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except DatabaseAuthError as exc:
        logger.error("Database auth failure in stream_chat_completion: %s", exc.technical_details)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable due to authentication configuration.",
        )
    except DatabaseConnectionError as exc:
        logger.error("Database connection failure in stream_chat_completion: %s", exc.technical_details)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unreachable. Please try again shortly.",
        )
    except DatabaseOperationError as exc:
        logger.error("Database operation failure in stream_chat_completion: %s", exc.technical_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error resolving conversation.",
        )

    # 2. Return SSE StreamingResponse
    stream_generator = chat_service.stream_chat_completion(
        user=current_user,
        conversation=conversation,
        request=request,
        raw_request=raw_request,
    )

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
    repo: BaseChatRepository = Depends(get_user_chat_repository),
) -> List[ConversationResponse]:
    """Return all conversations owned by the caller."""
    try:
        conversations = await repo.list_conversations(current_user.id)
        return [
            ConversationResponse(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=c.message_count,
            )
            for c in conversations
        ]
    except DatabaseAuthError as exc:
        logger.error("Database auth error: %s", exc.technical_details)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database authentication error.")
    except DatabaseConnectionError as exc:
        logger.error("Database connection error: %s", exc.technical_details)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unreachable.")
    except DatabaseOperationError as exc:
        logger.error("Database operation error: %s", exc.technical_details)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database operation error.")


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
    repo: BaseChatRepository = Depends(get_user_chat_repository),
) -> ConversationResponse:
    """Create a new conversation thread bound to the user."""
    try:
        conv = await repo.create_conversation(current_user.id, title=payload.title or "New Conversation")
        return ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=0,
        )
    except DatabaseError as exc:
        logger.error("Database error creating conversation: %s", getattr(exc, "technical_details", str(exc)))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create conversation.")


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Rename Conversation",
    description="Update the title of an owned conversation thread.",
)
async def rename_conversation(
    conversation_id: UUID,
    payload: ConversationRenameRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseChatRepository = Depends(get_user_chat_repository),
) -> ConversationResponse:
    """Rename an owned conversation thread."""
    try:
        conv = await repo.update_conversation_title(
            user_id=current_user.id,
            conversation_id=conversation_id,
            title=payload.title,
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )
        return ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=conv.message_count,
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error renaming conversation: %s", getattr(exc, "technical_details", str(exc)))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to rename conversation.")


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Conversation",
    description="Atomically delete an owned conversation thread and all its messages.",
)
async def delete_conversation(
    conversation_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseChatRepository = Depends(get_user_chat_repository),
):
    """Delete an owned conversation thread and cascade delete its messages."""
    try:
        deleted = await repo.delete_conversation(
            user_id=current_user.id,
            conversation_id=conversation_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error deleting conversation: %s", getattr(exc, "technical_details", str(exc)))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete conversation.")


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[MessageResponse],
    summary="Get Conversation Messages",
    description="Retrieve chronological messages for an owned conversation.",
)
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseChatRepository = Depends(get_user_chat_repository),
) -> List[MessageResponse]:
    """Retrieve message history, enforcing caller ownership."""
    try:
        conv = await repo.get_conversation(current_user.id, conversation_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )

        messages = await repo.get_messages(current_user.id, conversation_id)
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
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error fetching messages: %s", getattr(exc, "technical_details", str(exc)))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch messages.")


@router.get(
    "/conversations/{conversation_id}/messages/{message_id}/context",
    response_model=MessageContextResponse,
    summary="Get Message Context Provenance",
    description="Retrieve the exact memory items that were injected into context for an assistant message.",
)
async def get_message_context(
    conversation_id: UUID,
    message_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseChatRepository = Depends(get_user_chat_repository),
) -> MessageContextResponse:
    """Retrieve context provenance for a message, strictly verifying ownership and conversational hierarchy."""
    try:
        conv = await repo.get_conversation(current_user.id, conversation_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )

        msg = await repo.get_message_by_id(current_user.id, message_id)
        if not msg or msg.conversation_id != conversation_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found or access denied.",
            )

        raw_memories = (msg.metadata or {}).get("retrieved_memories", [])
        items: List[MemoryContextItem] = []
        for rm in raw_memories:
            try:
                items.append(
                    MemoryContextItem(
                        id=UUID(rm["id"]),
                        content=rm["content"],
                        memory_type=rm.get("memory_type", "fact"),
                        category=rm.get("category", "general"),
                        confirmation_status=rm.get("confirmation_status", "unconfirmed"),
                        importance=rm.get("importance", 3),
                        score=float(rm.get("score", 0.0)),
                    )
                )
            except Exception as parse_err:
                logger.warning("Error parsing retrieved memory context item: %s", parse_err)

        return MessageContextResponse(
            message_id=msg.id,
            conversation_id=conversation_id,
            model=(msg.metadata or {}).get("model"),
            retrieved_memories=items,
            memory_count=len(items),
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error fetching message context: %s", getattr(exc, "technical_details", str(exc)))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch message context.")
