"""Google Gemini LLM provider adapter using official google-genai SDK."""

import asyncio
import logging
from typing import AsyncIterator, List, Optional

from app.services.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    LLMAuthenticationError,
    LLMException,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMResponse,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Adapter for Google Gemini models via google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: str = "gemini-2.5-flash",
        timeout_seconds: float = 60.0,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self._client = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                logger.warning("Could not initialize google-genai Client: %s", exc)
                self._client = None

    def get_model_id(self) -> str:
        return self.model_id

    def _convert_messages(self, messages: List[ChatMessage]):
        """Convert standard ChatMessages into Gemini contents and system instruction."""
        system_instructions = []
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_instructions.append(msg.content)
            elif msg.role in ("user", "human"):
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role in ("assistant", "model"):
                contents.append({"role": "model", "parts": [{"text": msg.content}]})

        system_instruction = "\n\n".join(system_instructions) if system_instructions else None
        return contents, system_instruction

    async def generate_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """Execute a non-streaming completion using Gemini."""
        if not self.api_key or self._client is None:
            raise LLMAuthenticationError(
                "Gemini API key is not configured. Set LLM_API_KEY in backend/.env"
            )

        contents, system_instruction = self._convert_messages(messages)

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                system_instruction=system_instruction,
            )

            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model_id,
                    contents=contents,
                    config=config,
                ),
                timeout=self.timeout_seconds,
            )

            text_content = response.text or ""
            return LLMResponse(
                content=text_content,
                model=self.model_id,
                finish_reason="stop",
            )
        except asyncio.TimeoutError:
            raise LLMTimeoutError(f"Gemini request timed out after {self.timeout_seconds}s")
        except Exception as exc:
            error_str = str(exc)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                raise LLMQuotaExceededError(f"Gemini quota exceeded: {error_str}")
            if "API_KEY_INVALID" in error_str or "401" in error_str or "403" in error_str:
                raise LLMAuthenticationError(f"Gemini authentication failed: {error_str}")
            raise LLMProviderError(f"Gemini generation error: {error_str}")

    async def stream_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream chunks from Gemini model in real time."""
        if not self.api_key or self._client is None:
            raise LLMAuthenticationError(
                "Gemini API key is not configured. Set LLM_API_KEY in backend/.env"
            )

        contents, system_instruction = self._convert_messages(messages)

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                system_instruction=system_instruction,
            )

            stream = await self._client.aio.models.generate_content_stream(
                model=self.model_id,
                contents=contents,
                config=config,
            )

            async for chunk in stream:
                if chunk.text:
                    yield chunk.text

        except asyncio.TimeoutError:
            raise LLMTimeoutError(f"Gemini stream timed out after {self.timeout_seconds}s")
        except LLMException:
            raise
        except Exception as exc:
            error_str = str(exc)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                raise LLMQuotaExceededError(f"Gemini quota exceeded: {error_str}")
            if "API_KEY_INVALID" in error_str or "401" in error_str or "403" in error_str:
                raise LLMAuthenticationError(f"Gemini authentication failed: {error_str}")
            raise LLMProviderError(f"Gemini streaming error: {error_str}")

    async def count_tokens(self, text: str) -> Optional[int]:
        """Count tokens using Gemini's native API.

        Returns None if client is unconfigured, offline, or request fails.
        """
        if not self.api_key or self._client is None:
            return None

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.count_tokens(
                    model=self.model_id,
                    contents=text,
                ),
                timeout=10.0,
            )
            return response.total_tokens
        except Exception as exc:
            logger.warning("Gemini native count_tokens failed: %s", exc)
            return None

