"""Chat service managing context assembly, message persistence, and SSE streaming."""

import json
import logging
from typing import AsyncIterator, Optional
from uuid import UUID

from fastapi import HTTPException, status

from app.core.config import settings
from app.models.chat import (
    ChatCompletionRequest,
    ConversationModel,
    MessageModel,
)
from app.models.user import AuthenticatedUser
from app.services.chat.repository import ChatRepository, chat_repository
from app.services.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    LLMAuthenticationError,
    LLMException,
    LLMQuotaExceededError,
    LLMTimeoutError,
)
from app.services.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are AUREN, an intelligent, private, and premium personal AI assistant.
Your goal is to provide concise, structured, thoughtful, and deeply helpful assistance to the user.
Communicate clearly, avoid unnecessary filler, and maintain a calm, highly capable demeanor."""


class ChatService:
    """Orchestrates persistent chat flows, context management, and SSE streaming."""

    def __init__(self, repository: ChatRepository = chat_repository):
        self.repository = repository

    def _get_provider(self) -> BaseLLMProvider:
        return get_llm_provider(settings)

    def validate_and_resolve_conversation(
        self,
        user: AuthenticatedUser,
        request: ChatCompletionRequest,
    ) -> ConversationModel:
        """Fetch existing conversation enforcing ownership, or create a new one.

        Executed synchronously in route handler before initiating StreamingResponse to ensure
        HTTP 404/413 errors are delivered with correct HTTP status codes.
        """
        # Validate message length limit
        if len(request.message) > settings.CHAT_MAX_MESSAGE_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Message length exceeds maximum permitted limit ({settings.CHAT_MAX_MESSAGE_LENGTH} characters).",
            )

        # Check if an existing message was already submitted with this idempotency key
        if request.idempotency_key:
            existing_msg = self.repository.find_message_by_idempotency_key(user.id, request.idempotency_key)
            if existing_msg:
                existing_conv = self.repository.get_conversation(user.id, existing_msg.conversation_id)
                if existing_conv:
                    return existing_conv

        if request.conversation_id:
            conv = self.repository.get_conversation(user.id, request.conversation_id)
            if conv is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found or access denied.",
                )
            return conv

        # Generate concise title from the user's first prompt
        title = request.message.strip().split("\n")[0][:40] or "New Conversation"
        return self.repository.create_conversation(user.id, title=title)

    async def stream_chat_completion(
        self,
        user: AuthenticatedUser,
        conversation: ConversationModel,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[str]:
        """Stream SSE events for a pre-validated chat request."""
        # 1. Persist user message first (with idempotency handling)
        user_message = self.repository.persist_user_message(
            user_id=user.id,
            conversation_id=conversation.id,
            content=request.message,
            idempotency_key=request.idempotency_key,
        )

        # Send initial metadata event with thread and message IDs
        init_event = {
            "conversation_id": str(conversation.id),
            "user_message_id": str(user_message.id),
            "title": conversation.title,
        }
        yield f"event: metadata\ndata: {json.dumps(init_event)}\n\n"

        # 2. Assemble sliding window conversation context
        history = self.repository.get_messages(
            user_id=user.id,
            conversation_id=conversation.id,
            limit=settings.CHAT_HISTORY_LIMIT,
        )

        llm_messages: list[ChatMessage] = [
            ChatMessage(role="system", content=SYSTEM_PROMPT)
        ]

        for msg in history:
            llm_messages.append(ChatMessage(role=msg.role, content=msg.content))

        # 3. Stream response from LLM provider
        provider = self._get_provider()
        accumulated_chunks = []
        is_completed = False

        try:
            stream_gen = provider.stream_response(llm_messages)

            async for chunk in stream_gen:
                if chunk:
                    accumulated_chunks.append(chunk)
                    payload = json.dumps({"text": chunk})
                    yield f"event: token\ndata: {payload}\n\n"

            # 4. Persist assistant message upon successful completion
            full_response = "".join(accumulated_chunks)
            assistant_msg = self.repository.persist_assistant_message(
                user_id=user.id,
                conversation_id=conversation.id,
                content=full_response,
                metadata={"model": provider.get_model_id()},
            )
            is_completed = True

            done_event = {
                "message_id": str(assistant_msg.id),
                "finish_reason": "stop",
                "model": provider.get_model_id(),
            }
            yield f"event: done\ndata: {json.dumps(done_event)}\n\n"

        except LLMAuthenticationError as err:
            logger.error("LLM Auth Error: %s", err)
            error_payload = json.dumps({"detail": "AI Provider authentication failure. Check backend configuration."})
            yield f"event: error\ndata: {error_payload}\n\n"
        except LLMQuotaExceededError as err:
            logger.error("LLM Quota Error: %s", err)
            error_payload = json.dumps({"detail": "AI Provider quota exceeded or rate limit reached."})
            yield f"event: error\ndata: {error_payload}\n\n"
        except LLMTimeoutError as err:
            logger.error("LLM Timeout: %s", err)
            error_payload = json.dumps({"detail": "AI request timed out waiting for response."})
            yield f"event: error\ndata: {error_payload}\n\n"
        except Exception as exc:
            logger.exception("Unexpected error during chat stream: %s", exc)
            error_payload = json.dumps({"detail": f"Chat stream error: {str(exc)}"})
            yield f"event: error\ndata: {error_payload}\n\n"
        finally:
            # If interrupted before complete, save partial text so user work is preserved
            if not is_completed and accumulated_chunks:
                partial_text = "".join(accumulated_chunks)
                self.repository.persist_assistant_message(
                    user_id=user.id,
                    conversation_id=conversation.id,
                    content=partial_text,
                    metadata={"interrupted": True, "model": provider.get_model_id()},
                )
                logger.info("Saved partial assistant response due to stream interruption.")


chat_service = ChatService()
