"""Adapter for Groq models via fast HTTP streaming API."""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, List, Optional
import httpx

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


class GroqProvider(BaseLLMProvider):
    """Adapter for ultra-low latency inference on Groq LPUs (<300ms TTFT, 500-800 tokens/sec)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: str = "openai/gpt-oss-120b",
        timeout_seconds: float = 30.0,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds

    def get_model_id(self) -> str:
        return self.model_id

    def _get_candidate_models(self) -> List[str]:
        candidates = [self.model_id]
        for fallback in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"):
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def _convert_messages(self, messages: List[ChatMessage]) -> List[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def generate_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        if not self.api_key:
            raise LLMAuthenticationError("GROQ_API_KEY (or LLM_API_KEY) is not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        candidates = self._get_candidate_models()
        last_error = None
        async with httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            timeout=httpx.Timeout(self.timeout_seconds, connect=4.0),
        ) as client:
            for candidate in candidates:
                payload: dict[str, Any] = {
                    "model": candidate,
                    "messages": self._convert_messages(messages),
                    "temperature": temperature,
                }
                if max_tokens:
                    payload["max_tokens"] = max_tokens

                try:
                    response = await client.post("/chat/completions", headers=headers, json=payload)
                    if response.status_code == 401:
                        raise LLMAuthenticationError("Invalid Groq API key")
                    if response.status_code == 429:
                        raise LLMQuotaExceededError("Groq rate limit exceeded")
                    response.raise_for_status()

                    data = response.json()
                    choice = data["choices"][0]
                    return LLMResponse(
                        content=choice["message"]["content"],
                        model=candidate,
                        finish_reason=choice.get("finish_reason"),
                        prompt_tokens=data.get("usage", {}).get("prompt_tokens"),
                        completion_tokens=data.get("usage", {}).get("completion_tokens"),
                    )
                except (LLMAuthenticationError, LLMQuotaExceededError):
                    raise
                except Exception as exc:
                    last_error = exc
                    logger.warning("Groq generation failed on %s: %s", candidate, exc)
                    continue

        raise LLMProviderError(f"All Groq candidates failed: {last_error}")

    async def stream_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise LLMAuthenticationError("GROQ_API_KEY (or LLM_API_KEY) is not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        candidates = self._get_candidate_models()
        async with httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            timeout=httpx.Timeout(self.timeout_seconds, connect=4.0),
        ) as client:
            for idx, candidate in enumerate(candidates):
                has_fallback = idx < len(candidates) - 1
                payload: dict[str, Any] = {
                    "model": candidate,
                    "messages": self._convert_messages(messages),
                    "temperature": temperature,
                    "stream": True,
                }
                if max_tokens:
                    payload["max_tokens"] = max_tokens

                try:
                    async with client.stream("POST", "/chat/completions", headers=headers, json=payload) as resp:
                        if resp.status_code == 401:
                            raise LLMAuthenticationError("Invalid Groq API key")
                        if resp.status_code == 429:
                            raise LLMQuotaExceededError("Groq rate limit exceeded")
                        resp.raise_for_status()

                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            raw = line[6:].strip()
                            if raw == "[DONE]":
                                break
                            try:
                                chunk = json.loads(raw)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield content
                            except Exception:
                                continue
                    return
                except (LLMAuthenticationError, LLMQuotaExceededError):
                    raise
                except Exception as exc:
                    logger.warning("Groq stream error on %s: %s", candidate, exc)
                    if not has_fallback:
                        raise LLMProviderError(f"Groq streaming failed: {exc}")
                    continue

