"""Chat service managing context assembly, persistent database storage,

resilient SSE streaming, heartbeats, and strict idempotency lifecycle tracking.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional
from uuid import UUID

from fastapi import HTTPException, Request, status

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
    LLMProviderError,
    LLMQuotaExceededError,
    LLMTimeoutError,
)
from app.services.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are AUREN, an intelligent, private, and premium personal AI assistant.
Your goal is to provide concise, structured, thoughtful, and deeply helpful assistance to the user.
Communicate clearly, avoid unnecessary filler, and maintain a calm, highly capable demeanor."""


class ChatService:
    """Orchestrates persistent chat flows, context management, and resilient SSE streaming."""

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
        HTTP 404/413 errors are delivered with standard HTTP status codes.
        """
        if len(request.message) > settings.CHAT_MAX_MESSAGE_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Message length exceeds maximum permitted limit ({settings.CHAT_MAX_MESSAGE_LENGTH} characters).",
            )

        # Check if an existing request was already submitted with this idempotency key
        if request.idempotency_key:
            existing_req = self.repository.get_chat_request(user.id, request.idempotency_key)
            if existing_req:
                existing_conv = self.repository.get_conversation(user.id, existing_req.conversation_id)
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
        raw_request: Optional[Request] = None,
    ) -> AsyncIterator[str]:
        """Stream SSE events for a pre-validated chat request with strict idempotency and timeouts.

        Guarantees:
        1. If request was already completed, replays cached response with ZERO new AI generation calls.
        2. Persists user message before calling the LLM.
        3. Enforces CHAT_STREAM_TIMEOUT_SECONDS across overall stream execution.
        4. Heartbeats (every 15s) keep connection active during model latency.
        5. Handles client disconnection by persisting partial assistant response.
        6. Logs technical errors server-side and emits safe, sanitized errors to client.
        """
        # -------------------------------------------------------------------
        # 1. Idempotency Check: Already Completed Request?
        # -------------------------------------------------------------------
        if request.idempotency_key:
            existing_req = self.repository.get_chat_request(user.id, request.idempotency_key)
            if existing_req and existing_req.status == "completed" and existing_req.assistant_message_id:
                logger.info(
                    "Idempotency hit: Replaying completed response for key=%s (user=%s)",
                    request.idempotency_key, user.id,
                )
                cached_msg = self.repository.get_message_by_id(user.id, existing_req.assistant_message_id)
                if cached_msg:
                    # Replay cached response without invoking provider!
                    meta_event = {
                        "conversation_id": str(conversation.id),
                        "user_message_id": str(existing_req.user_message_id),
                        "title": conversation.title,
                        "replayed": True,
                    }
                    yield f"event: metadata\ndata: {json.dumps(meta_event)}\n\n"
                    yield f"event: token\ndata: {json.dumps({'text': cached_msg.content})}\n\n"
                    done_event = {
                        "message_id": str(cached_msg.id),
                        "finish_reason": "replayed_from_cache",
                        "model": cached_msg.metadata.get("model", "cached"),
                    }
                    yield f"event: done\ndata: {json.dumps(done_event)}\n\n"
                    return

            if existing_req and existing_req.status == "processing":
                logger.warning("Duplicate request while key=%s is still processing", request.idempotency_key)
                error_event = {
                    "detail": "A request with this idempotency key is already in progress. Please wait for it to complete."
                }
                yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                return

        # -------------------------------------------------------------------
        # 2. Persist User Message and Record Request Lifecycle
        # -------------------------------------------------------------------
        user_message = self.repository.persist_user_message(
            user_id=user.id,
            conversation_id=conversation.id,
            content=request.message,
            idempotency_key=request.idempotency_key,
        )

        if request.idempotency_key:
            self.repository.record_chat_request(
                user_id=user.id,
                idempotency_key=request.idempotency_key,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                status="processing",
            )

        # Emit initial metadata event
        init_event = {
            "conversation_id": str(conversation.id),
            "user_message_id": str(user_message.id),
            "title": conversation.title,
        }
        yield f"event: metadata\ndata: {json.dumps(init_event)}\n\n"

        # -------------------------------------------------------------------
        # 3. Assemble Sliding Window Context
        # -------------------------------------------------------------------
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

        # -------------------------------------------------------------------
        # 4. Stream Response with Heartbeats & Timeout Enforcement
        # -------------------------------------------------------------------
        provider = self._get_provider()
        accumulated_chunks = []
        is_completed = False
        deadline = time.time() + float(settings.CHAT_STREAM_TIMEOUT_SECONDS)
        heartbeat_interval = 15.0

        try:
            stream_iter = provider.stream_response(llm_messages)
            stream_gen = stream_iter.__aiter__()

            while True:
                remaining_time = deadline - time.time()
                if remaining_time <= 0:
                    raise LLMTimeoutError(f"Stream overall execution exceeded {settings.CHAT_STREAM_TIMEOUT_SECONDS}s deadline")

                wait_timeout = min(remaining_time, heartbeat_interval)

                try:
                    # Check for client disconnect
                    if raw_request and await raw_request.is_disconnected():
                        logger.info("Client disconnected during stream (user=%s)", user.id)
                        break

                    chunk = await asyncio.wait_for(stream_gen.__anext__(), timeout=wait_timeout)
                    if chunk:
                        accumulated_chunks.append(chunk)
                        yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
                except asyncio.TimeoutError:
                    if time.time() >= deadline:
                        raise LLMTimeoutError(f"Stream execution exceeded {settings.CHAT_STREAM_TIMEOUT_SECONDS}s deadline")
                    # Heartbeat ping when waiting between chunks
                    now_ts = datetime.now(timezone.utc).isoformat()
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': now_ts})}\n\n"
                except StopAsyncIteration:
                    break

            # ---------------------------------------------------------------
            # 5. Persist Completed Assistant Response
            # ---------------------------------------------------------------
            full_response = "".join(accumulated_chunks)
            assistant_msg = self.repository.persist_assistant_message(
                user_id=user.id,
                conversation_id=conversation.id,
                content=full_response,
                metadata={"model": provider.get_model_id()},
            )
            is_completed = True

            if request.idempotency_key:
                self.repository.update_chat_request_status(
                    user_id=user.id,
                    idempotency_key=request.idempotency_key,
                    status="completed",
                    assistant_message_id=assistant_msg.id,
                )

            done_event = {
                "message_id": str(assistant_msg.id),
                "finish_reason": "stop",
                "model": provider.get_model_id(),
            }
            yield f"event: done\ndata: {json.dumps(done_event)}\n\n"

        except LLMAuthenticationError as err:
            logger.error("LLM Auth Error (sanitized for client): %s", err)
            if request.idempotency_key:
                self.repository.update_chat_request_status(user.id, request.idempotency_key, status="failed")
            safe_error = {"detail": "The AI service is unavailable due to authentication configuration."}
            yield f"event: error\ndata: {json.dumps(safe_error)}\n\n"

        except LLMQuotaExceededError as err:
            logger.warning("LLM Quota Exceeded (sanitized): %s", err)
            if request.idempotency_key:
                self.repository.update_chat_request_status(user.id, request.idempotency_key, status="failed")
            safe_error = {"detail": "AI capacity or rate limit reached. Please wait a moment before trying again."}
            yield f"event: error\ndata: {json.dumps(safe_error)}\n\n"

        except LLMTimeoutError as err:
            logger.warning("LLM Timeout (sanitized): %s", err)
            if request.idempotency_key:
                self.repository.update_chat_request_status(user.id, request.idempotency_key, status="failed")
            safe_error = {"detail": f"Request timed out after {settings.CHAT_STREAM_TIMEOUT_SECONDS} seconds."}
            yield f"event: error\ndata: {json.dumps(safe_error)}\n\n"

        except Exception as exc:
            logger.exception("Internal error during chat stream: %s", exc)
            if request.idempotency_key:
                self.repository.update_chat_request_status(user.id, request.idempotency_key, status="failed")
            safe_error = {"detail": "An unexpected error occurred while processing your request. Please try again."}
            yield f"event: error\ndata: {json.dumps(safe_error)}\n\n"

        finally:
            # Handle stream interruption without losing partial tokens
            if not is_completed and accumulated_chunks:
                partial_text = "".join(accumulated_chunks)
                interrupted_msg = self.repository.persist_assistant_message(
                    user_id=user.id,
                    conversation_id=conversation.id,
                    content=partial_text,
                    metadata={"interrupted": True, "model": provider.get_model_id()},
                )
                if request.idempotency_key:
                    self.repository.update_chat_request_status(
                        user_id=user.id,
                        idempotency_key=request.idempotency_key,
                        status="interrupted",
                        assistant_message_id=interrupted_msg.id,
                    )
                logger.info("Persisted partial assistant text from interrupted stream (user=%s)", user.id)


chat_service = ChatService()
