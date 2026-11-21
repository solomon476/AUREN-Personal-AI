"""Abstract interface and standard types for replaceable LLM providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional
from pydantic import BaseModel, Field


class LLMException(Exception):
    """Base exception for all LLM provider errors."""
    pass


class LLMAuthenticationError(LLMException):
    """Raised when provider API credentials are invalid or missing."""
    pass


class LLMQuotaExceededError(LLMException):
    """Raised when rate limits or quota are exhausted."""
    pass


class LLMTimeoutError(LLMException):
    """Raised when provider request exceeds execution deadline."""
    pass


class LLMProviderError(LLMException):
    """Generic downstream failure from an LLM provider."""
    pass


class ChatMessage(BaseModel):
    """Represents a message in a conversation thread."""

    role: str = Field(..., description="Role of the author: system, user, or assistant")
    content: str = Field(..., description="Message text content")
    images: Optional[List[str]] = Field(default=None, description="Optional list of base64 image strings or data URLs")


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""

    content: str
    model: str
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class BaseLLMProvider(ABC):
    """Pluggable abstract interface for LLM backends (Gemini, OpenAI, Anthropic, local)."""

    @abstractmethod
    def get_model_id(self) -> str:
        """Return the active model ID string."""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """Generate a complete completion for a sequence of chat messages."""
        pass

    @abstractmethod
    async def stream_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream response chunks for real-time text delivery."""
        pass

    async def count_tokens(self, text: str) -> Optional[int]:
        """Count tokens in text using provider native tokenizer.

        Returns None if provider does not support native token counting or
        if token counting fails/offline. Context manager uses this for strict
        fail-safe budget enforcement.
        """
        return None
