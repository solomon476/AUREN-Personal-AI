"""Unit tests for FallbackLLMProvider cross-provider automatic failover."""

import pytest
from typing import AsyncIterator, List, Optional
from app.services.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    LLMQuotaExceededError,
    LLMResponse,
)
from app.services.llm.fallback import FallbackLLMProvider


class FailingProvider(BaseLLMProvider):
    def __init__(self, model_id: str = "failing-model"):
        self.model_id = model_id

    def get_model_id(self) -> str:
        return self.model_id

    async def generate_response(self, messages: List[ChatMessage], **kwargs) -> LLMResponse:
        raise LLMQuotaExceededError("Rate limit exceeded 429")

    async def stream_response(self, messages: List[ChatMessage], **kwargs) -> AsyncIterator[str]:
        raise LLMQuotaExceededError("Rate limit exceeded 429")
        if False:
            yield ""


class WorkingProvider(BaseLLMProvider):
    def __init__(self, model_id: str = "backup-model", response: str = "Recovered response"):
        self.model_id = model_id
        self.response = response

    def get_model_id(self) -> str:
        return self.model_id

    async def generate_response(self, messages: List[ChatMessage], **kwargs) -> LLMResponse:
        return LLMResponse(content=self.response, model=self.model_id)

    async def stream_response(self, messages: List[ChatMessage], **kwargs) -> AsyncIterator[str]:
        for word in self.response.split(" "):
            yield word + " "


@pytest.mark.asyncio
async def test_fallback_generate_response():
    primary = FailingProvider("gemini-2.5-flash")
    backup = WorkingProvider("llama-3.3-70b-versatile", "Hello from Groq")

    fallback_provider = FallbackLLMProvider(primary=primary, fallbacks=[backup])
    res = await fallback_provider.generate_response([ChatMessage(role="user", content="Hi")])

    assert res.content == "Hello from Groq"
    assert fallback_provider.get_model_id() == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_fallback_stream_response():
    primary = FailingProvider("gemini-2.5-flash")
    backup = WorkingProvider("llama-3.3-70b-versatile", "Hello from Groq")

    fallback_provider = FallbackLLMProvider(primary=primary, fallbacks=[backup])
    tokens = []
    async for chunk in fallback_provider.stream_response([ChatMessage(role="user", content="Hi")]):
        tokens.append(chunk)

    full = "".join(tokens).strip()
    assert full == "Hello from Groq"
    assert fallback_provider.get_model_id() == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_primary_succeeds_without_fallback():
    primary = WorkingProvider("gemini-2.5-flash", "Hello from Gemini")
    backup = WorkingProvider("llama-3.3-70b-versatile", "Hello from Groq")

    fallback_provider = FallbackLLMProvider(primary=primary, fallbacks=[backup])
    tokens = []
    async for chunk in fallback_provider.stream_response([ChatMessage(role="user", content="Hi")]):
        tokens.append(chunk)

    full = "".join(tokens).strip()
    assert full == "Hello from Gemini"
    assert fallback_provider.get_model_id() == "gemini-2.5-flash"
