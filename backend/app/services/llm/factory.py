"""Factory module for instantiating replaceable LLM providers."""

import logging
from typing import AsyncIterator, List, Optional
from app.core.config import Settings, settings as default_settings
from app.services.llm.base import BaseLLMProvider, ChatMessage, LLMProviderError, LLMResponse
from app.services.llm.fallback import FallbackLLMProvider
from app.services.llm.gemini import GeminiProvider
from app.services.llm.groq import GroqProvider
from app.services.llm.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider for automated unit tests without external API calls."""

    def __init__(self, model_id: str = "mock-model-v1", canned_response: str = "AUREN test response"):
        self.model_id = model_id
        self.canned_response = canned_response

    def get_model_id(self) -> str:
        return self.model_id

    async def generate_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        return LLMResponse(content=self.canned_response, model=self.model_id)

    async def stream_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        words = self.canned_response.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")


SUPPORTED_GEMINI_MODELS = {
    "gemini-3.8-flash",
    "gemini-3.8-pro",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
}


SUPPORTED_GROQ_MODELS = {
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
}


SUPPORTED_OPENAI_MODELS = {
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
}


def get_llm_provider(
    settings: Settings = default_settings,
    model_id: Optional[str] = None,
) -> BaseLLMProvider:
    """Return an initialized LLM provider instance matching the active configuration.

    If model_id is specified, validates model compatibility with the configured provider.
    Automatically wraps with FallbackLLMProvider if secondary provider API keys are present,
    providing seamless high-availability failover across providers.
    """
    provider_name = settings.LLM_PROVIDER.lower().strip()
    active_model = model_id.strip() if model_id and str(model_id).strip() else settings.LLM_MODEL
    timeout_sec = float(settings.CHAT_STREAM_TIMEOUT_SECONDS)

    if active_model == "mock" or provider_name == "mock":
        return MockLLMProvider(model_id=active_model)

    primary: BaseLLMProvider
    fallbacks: List[BaseLLMProvider] = []

    # Determine primary provider based on model prefix or explicit setting
    if active_model.startswith("gpt-") or provider_name == "openai":
        primary = OpenAIProvider(
            api_key=settings.OPENAI_API_KEY or settings.LLM_API_KEY,
            model_id=active_model if active_model in SUPPORTED_OPENAI_MODELS else "gpt-4o-mini",
            timeout_seconds=timeout_sec,
        )
        if settings.GROQ_API_KEY:
            fallbacks.append(GroqProvider(api_key=settings.GROQ_API_KEY, model_id="openai/gpt-oss-120b", timeout_seconds=timeout_sec))
        if settings.LLM_API_KEY and not settings.LLM_API_KEY.startswith("sk-") and not settings.LLM_API_KEY.startswith("gsk_"):
            fallbacks.append(GeminiProvider(api_key=settings.LLM_API_KEY, model_id="gemini-3.5-flash", timeout_seconds=timeout_sec))

    elif active_model.startswith("openai/gpt-oss") or active_model.startswith("qwen/") or active_model.startswith("llama-") or active_model.startswith("mixtral-") or provider_name == "groq":
        primary = GroqProvider(
            api_key=settings.GROQ_API_KEY or settings.LLM_API_KEY,
            model_id=active_model if active_model in SUPPORTED_GROQ_MODELS else "openai/gpt-oss-120b",
            timeout_seconds=timeout_sec,
        )
        if settings.LLM_API_KEY and not settings.LLM_API_KEY.startswith("gsk_") and not settings.LLM_API_KEY.startswith("sk-"):
            fallbacks.append(GeminiProvider(api_key=settings.LLM_API_KEY, model_id="gemini-3.5-flash", timeout_seconds=timeout_sec))
        if settings.OPENAI_API_KEY:
            fallbacks.append(OpenAIProvider(api_key=settings.OPENAI_API_KEY, model_id="gpt-4o-mini", timeout_seconds=timeout_sec))

    elif provider_name == "gemini" or active_model.startswith("gemini-"):
        if active_model not in SUPPORTED_GEMINI_MODELS:
            raise LLMProviderError(
                f"Model '{active_model}' is not supported by the Gemini provider. "
                f"Supported operational models: {', '.join(sorted(SUPPORTED_GEMINI_MODELS))}."
            )
        primary = GeminiProvider(
            api_key=settings.LLM_API_KEY,
            model_id=active_model,
            timeout_seconds=timeout_sec,
        )
        # Automatic cross-provider fallback to Groq and/or OpenAI when available
        if settings.GROQ_API_KEY or (settings.LLM_API_KEY and settings.LLM_API_KEY.startswith("gsk_")):
            groq_key = settings.GROQ_API_KEY or settings.LLM_API_KEY
            fallbacks.append(GroqProvider(api_key=groq_key, model_id="openai/gpt-oss-120b", timeout_seconds=timeout_sec))
        if settings.OPENAI_API_KEY or (settings.LLM_API_KEY and settings.LLM_API_KEY.startswith("sk-")):
            openai_key = settings.OPENAI_API_KEY or settings.LLM_API_KEY
            fallbacks.append(OpenAIProvider(api_key=openai_key, model_id="gpt-4o-mini", timeout_seconds=timeout_sec))

    else:
        raise LLMProviderError(
            f"Unsupported LLM provider '{provider_name}'. Supported providers: 'gemini', 'groq', 'openai', 'mock'."
        )

    if fallbacks:
        return FallbackLLMProvider(primary=primary, fallbacks=fallbacks)
    return primary

