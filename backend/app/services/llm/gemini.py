"""Google Gemini LLM provider adapter using official google-genai SDK."""

import asyncio
import logging
from typing import Any, AsyncIterator, List, Optional

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
        model_id: str = "gemini-2.0-flash",
        timeout_seconds: float = 60.0,
    ):
        self.api_key = api_key
        self.model_id = model_id

        # Gracefully remap simulated or deprecated alias models to real production Google endpoints
        api_model = model_id
        # Normalize model string; preserve modern 3.x models recommended by Google
        api_model = model_id.strip()
        if api_model.startswith("models/"):
            api_model = api_model[len("models/"):]
        self._api_model = api_model

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

    def _get_candidate_models(self) -> List[str]:
        """Return prioritized list of verified fast models for minimum latency and resilience."""
        candidates = [self._api_model]
        for fallback in ("gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"):
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def _convert_messages(self, messages: List[ChatMessage]):
        """Convert standard ChatMessages into Gemini contents and system instruction."""
        system_instructions = []
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_instructions.append(msg.content)
            elif msg.role in ("user", "human"):
                parts = []
                if msg.content and msg.content.strip():
                    parts.append({"text": msg.content})
                # Check for multimodal image attachments
                images = getattr(msg, "images", None) or []
                if images:
                    import base64
                    from google.genai import types
                    for img in images:
                        mime_type = "image/jpeg"
                        img_data = img
                        if img.startswith("data:"):
                            header, _, encoded = img.partition(",")
                            if ";base64" in header:
                                mime_type = header.split(";")[0].replace("data:", "")
                                img_data = encoded
                        try:
                            raw_bytes = base64.b64decode(img_data)
                            parts.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime_type))
                        except Exception as exc:
                            logger.warning("Failed to decode base64 image: %s", exc)
                if not parts:
                    parts.append({"text": msg.content or " "})
                contents.append({"role": "user", "parts": parts})
            elif msg.role in ("assistant", "model"):
                contents.append({"role": "model", "parts": [{"text": msg.content or " "}]})

        system_instruction = "\n\n".join(system_instructions) if system_instructions else None
        return contents, system_instruction

    async def generate_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """Execute a non-streaming completion using Gemini with automatic fallback."""
        if not self.api_key or self._client is None:
            raise LLMAuthenticationError(
                "Gemini API key is not configured. Set LLM_API_KEY in backend/.env"
            )

        contents, system_instruction = self._convert_messages(messages)

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        last_error = None
        candidates = self._get_candidate_models()
        for idx, candidate in enumerate(candidates):
            has_fallback = idx < len(candidates) - 1
            candidate_timeout = min(self.timeout_seconds, 15.0) if has_fallback else self.timeout_seconds
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=candidate,
                        contents=contents,
                        config=config,
                    ),
                    timeout=candidate_timeout,
                )

                text_content = response.text or ""
                return LLMResponse(
                    content=text_content,
                    model=self.model_id,
                    finish_reason="stop",
                )
            except asyncio.TimeoutError:
                last_error = LLMTimeoutError(f"Gemini request timed out on {candidate} after {candidate_timeout}s")
                logger.warning("Gemini timeout on model %s, trying fallback...", candidate)
                continue
            except Exception as exc:
                error_str = str(exc)
                if "API_KEY_INVALID" in error_str or "401" in error_str or "403" in error_str:
                    raise LLMAuthenticationError(f"Gemini authentication failed: {error_str}")
                if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                    logger.warning("Gemini 429 rate limit on %s; pausing 2s before fallback...", candidate)
                    if has_fallback:
                        await asyncio.sleep(2.0)
                logger.warning("Gemini generation error on model %s: %s (trying fallback)", candidate, error_str)
                last_error = exc
                continue

        if last_error:
            error_str = str(last_error)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                raise LLMQuotaExceededError(f"Gemini quota exceeded: {error_str}")
            if isinstance(last_error, LLMTimeoutError):
                raise last_error
            raise LLMProviderError(f"Gemini generation error: {error_str}")
        raise LLMProviderError("No response received from any model candidate")

    async def stream_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream chunks from Gemini model in real time with resilient multi-model failover."""
        if not self.api_key or self._client is None:
            raise LLMAuthenticationError(
                "Gemini API key is not configured. Set LLM_API_KEY in backend/.env"
            )

        contents, system_instruction = self._convert_messages(messages)

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        last_error = None
        candidates = self._get_candidate_models()
        for idx, candidate in enumerate(candidates):
            has_fallback = idx < len(candidates) - 1
            first_token_timeout = 4.0 if has_fallback else min(self.timeout_seconds, 15.0)
            try:
                stream = await self._client.aio.models.generate_content_stream(
                    model=candidate,
                    contents=contents,
                    config=config,
                )

                # Verify connectivity and pull first token with fast failover timeout
                stream_iter = stream.__aiter__()
                try:
                    first_chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=first_token_timeout)
                except StopAsyncIteration:
                    return

                if first_chunk.text:
                    yield first_chunk.text

                # Stream remaining tokens
                async for chunk in stream_iter:
                    if chunk.text:
                        yield chunk.text
                return

            except asyncio.TimeoutError:
                logger.warning("Gemini initial stream timed out after %.1fs on model %s (trying fast fallback)", first_token_timeout, candidate)
                last_error = LLMTimeoutError(f"Gemini stream timed out on {candidate}")
                continue
            except Exception as exc:
                error_str = str(exc)
                if "API_KEY_INVALID" in error_str or "401" in error_str or "403" in error_str:
                    raise LLMAuthenticationError(f"Gemini authentication failed: {error_str}")
                if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                    logger.warning("Gemini 429 rate limit on %s; pausing 2s before fallback...", candidate)
                    if has_fallback:
                        await asyncio.sleep(2.0)
                logger.warning("Gemini streaming failed on model %s: %s (trying fallback)", candidate, error_str)
                last_error = exc
                continue

        if last_error:
            error_str = str(last_error)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                raise LLMQuotaExceededError(f"Gemini quota exceeded: {error_str}")
            if isinstance(last_error, LLMTimeoutError):
                raise last_error
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
                    model=self._api_model,
                    contents=text,
                ),
                timeout=10.0,
            )
            return response.total_tokens
        except Exception as exc:
            logger.warning("Gemini native count_tokens failed: %s", exc)
            return None

