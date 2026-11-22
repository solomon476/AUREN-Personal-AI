"""Unit tests for Groq provider and provider factory integration."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.core.config import Settings
from app.services.llm.base import ChatMessage, LLMAuthenticationError
from app.services.llm.factory import get_llm_provider
from app.services.llm.groq import GroqProvider


def test_groq_provider_initialization():
    provider = GroqProvider(api_key="gsk_test123", model_id="llama-3.3-70b-versatile")
    assert provider.get_model_id() == "llama-3.3-70b-versatile"
    assert provider.api_key == "gsk_test123"


def test_factory_returns_groq_provider():
    settings = Settings(
        LLM_PROVIDER="groq",
        LLM_API_KEY="gsk_test123",
        LLM_MODEL="llama-3.3-70b-versatile",
    )
    provider = get_llm_provider(settings=settings)
    assert isinstance(provider, GroqProvider)
    assert provider.get_model_id() == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_groq_provider_missing_key_raises_auth_error():
    provider = GroqProvider(api_key=None, model_id="llama-3.3-70b-versatile")
    with pytest.raises(LLMAuthenticationError):
        await provider.generate_response([ChatMessage(role="user", content="hello")])

    with pytest.raises(LLMAuthenticationError):
        async for _ in provider.stream_response([ChatMessage(role="user", content="hello")]):
            pass

