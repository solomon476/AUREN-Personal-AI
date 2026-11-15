"""Factory module for instantiating replaceable LLM providers."""

import logging
from typing import AsyncIterator, List, Optional
from app.core.config import Settings, settings as default_settings
from app.services.llm.base import BaseLLMProvider, ChatMessage, LLMProviderError, LLMResponse
from app.services.llm.gemini import GeminiProvider

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


def get_llm_provider(settings: Settings = default_settings) -> BaseLLMProvider:
    """Return an initialized LLM provider instance matching the active configuration."""
    provider_name = settings.LLM_PROVIDER.lower().strip()

    if provider_name == "gemini":
        return GeminiProvider(
            api_key=settings.LLM_API_KEY,
            model_id=settings.LLM_MODEL,
            timeout_seconds=float(settings.CHAT_STREAM_TIMEOUT_SECONDS),
        )
    elif provider_name == "mock":
        return MockLLMProvider(model_id=settings.LLM_MODEL)
    else:
        raise LLMProviderError(
            f"Unsupported LLM provider '{provider_name}'. Supported providers: 'gemini', 'mock'."
        )

