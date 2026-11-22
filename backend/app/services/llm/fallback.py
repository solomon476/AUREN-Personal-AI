"""Fallback LLM Provider adapter for seamless multi-provider failover."""

import logging
from typing import AsyncIterator, List, Optional
from app.services.llm.base import BaseLLMProvider, ChatMessage, LLMException, LLMResponse

logger = logging.getLogger(__name__)


class FallbackLLMProvider(BaseLLMProvider):
    """Wraps a primary provider with one or more backup providers for high-availability failover.

    If the primary provider experiences a rate limit (429), capacity exhaustion (503),
    timeout, or provider crash before yielding any tokens to the client, FallbackLLMProvider
    transparently switches to the next available backup provider without user-visible errors.
    """

    def __init__(self, primary: BaseLLMProvider, fallbacks: Optional[List[BaseLLMProvider]] = None):
        self.primary = primary
        self.fallbacks = fallbacks or []
        self._active_provider = primary

    def get_model_id(self) -> str:
        return self._active_provider.get_model_id()

    async def generate_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        providers = [self.primary] + self.fallbacks
        last_error = None

        for prov in providers:
            try:
                res = await prov.generate_response(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                self._active_provider = prov
                return res
            except Exception as exc:
                logger.warning(
                    "LLM provider '%s' failed in generate_response (%s). Attempting fallback...",
                    prov.get_model_id(),
                    exc,
                )
                last_error = exc

        if last_error:
            raise last_error
        raise LLMException("No active LLM providers configured.")

    async def stream_response(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        providers = [self.primary] + self.fallbacks
        last_error = None

        for i, prov in enumerate(providers):
            yielded_any = False
            try:
                async for chunk in prov.stream_response(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ):
                    yielded_any = True
                    self._active_provider = prov
                    yield chunk
                # Stream completed successfully
                return
            except Exception as exc:
                logger.warning(
                    "LLM provider '%s' failed during stream_response (yielded_any=%s): %s",
                    prov.get_model_id(),
                    yielded_any,
                    exc,
                )
                last_error = exc
                if yielded_any:
                    # Tokens were already emitted to client; cannot restart mid-generation
                    raise exc

                # Check if there is another provider to try
                if i < len(providers) - 1:
                    next_prov = providers[i + 1]
                    logger.info(
                        "Seamlessly failing over from '%s' to backup provider '%s'...",
                        prov.get_model_id(),
                        next_prov.get_model_id(),
                    )
                    continue

        if last_error:
            raise last_error
        raise LLMException("No active LLM providers configured.")
