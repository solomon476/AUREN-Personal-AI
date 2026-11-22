"""Tests for OpenAI LLM Provider."""

import pytest
from app.services.llm.base import LLMAuthenticationError
from app.services.llm.factory import get_llm_provider
from app.services.llm.openai import OpenAIProvider
from app.core.config import Settings


def test_openai_provider_initialization():
    provider = OpenAIProvider(api_key="sk-test-fake", model_id="gpt-4o-mini")
    assert provider.get_model_id() == "gpt-4o-mini"
    assert "gpt-4o-mini" in provider._get_candidate_models()


def test_factory_returns_openai_provider():
    test_settings = Settings(
        LLM_PROVIDER="openai",
        LLM_API_KEY="sk-test-fake",
        LLM_MODEL="gpt-4o-mini",
    )
    provider = get_llm_provider(settings=test_settings)
    assert isinstance(provider, OpenAIProvider)
    assert provider.get_model_id() == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_openai_provider_missing_key_raises_auth_error():
    provider = OpenAIProvider(api_key=None, model_id="gpt-4o-mini")
    with pytest.raises(LLMAuthenticationError):
        await provider.generate_response([])

    with pytest.raises(LLMAuthenticationError):
        async for _ in provider.stream_response([]):
            pass
