"""Unit tests for AI model selection, validation, and chat routing."""

import pytest
from app.core.config import settings
from app.services.llm.base import LLMProviderError
from app.services.llm.factory import get_llm_provider


def test_supported_gemini_models_instantiated_cleanly():
    for model_id in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]:
        provider = get_llm_provider(settings, model_id=model_id)
        assert provider.get_model_id() == model_id


def test_unsupported_models_rejected_with_understandable_error():
    unsupported_models = ["claude-3-5-sonnet", "gpt-4o", "llama-3-70b", "unknown-model"]
    for model_id in unsupported_models:
        with pytest.raises(LLMProviderError) as exc_info:
            get_llm_provider(settings, model_id=model_id)
        msg = str(exc_info.value)
        assert f"Model '{model_id}' is not supported" in msg
        assert "gemini-2.5-flash" in msg


def test_empty_or_none_model_falls_back_to_settings_default():
    provider = get_llm_provider(settings, model_id=None)
    assert provider.get_model_id() == settings.LLM_MODEL


def test_mock_model_returns_mock_provider():
    provider = get_llm_provider(settings, model_id="mock")
    assert provider.get_model_id() == "mock"
