"""Factory module for instantiating replaceable vector embedding providers."""

import hashlib
import logging
import math
from typing import List, Optional

from app.core.config import Settings, settings as default_settings
from app.services.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingAuthenticationError,
    EmbeddingDimensionError,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
    validate_embedding_vector,
)
from app.services.embeddings.gemini import GeminiEmbeddingProvider

logger = logging.getLogger(__name__)


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic mock embedding provider for automated testing and offline development."""

    def __init__(
        self,
        dimension: int = 768,
        model_id: str = "gemini-embedding-2",
        canned_vector: Optional[List[float]] = None,
        simulate_timeout: bool = False,
        simulate_invalid_dimension: Optional[int] = None,
        simulate_non_finite: bool = False,
        simulate_auth_error: bool = False,
    ):
        self.dimension = dimension
        self.model_id = model_id
        self.canned_vector = canned_vector
        self.simulate_timeout = simulate_timeout
        self.simulate_invalid_dimension = simulate_invalid_dimension
        self.simulate_non_finite = simulate_non_finite
        self.simulate_auth_error = simulate_auth_error

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_id(self) -> str:
        return self.model_id

    def _generate_deterministic_vector(self, text: str) -> List[float]:
        """Generates a deterministic L2-normalized vector from text content."""
        if self.simulate_auth_error:
            raise EmbeddingAuthenticationError("Mock simulated authentication error")
        if self.simulate_timeout:
            raise EmbeddingTimeoutError("Mock simulated embedding timeout")

        if self.simulate_invalid_dimension is not None:
            raw = [0.1] * self.simulate_invalid_dimension
            return validate_embedding_vector(raw, expected_dimension=self.dimension)

        if self.simulate_non_finite:
            raw = [0.1] * self.dimension
            raw[0] = float("nan")
            return validate_embedding_vector(raw, expected_dimension=self.dimension)

        if self.canned_vector is not None:
            return validate_embedding_vector(self.canned_vector, expected_dimension=self.dimension)

        # Derive 768-dim floats deterministically using SHA-256 rounds
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec: List[float] = []
        for i in range(self.dimension):
            # Deterministic pseudo-random float in [-1.0, 1.0]
            byte_val = h[(i * 3) % len(h)]
            val = (byte_val / 127.5) - 1.0
            vec.append(val)

        # L2-normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            vec = [1.0 / math.sqrt(self.dimension)] * self.dimension

        return validate_embedding_vector(vec, expected_dimension=self.dimension)

    async def embed_text(self, text: str, task_type: Optional[str] = None) -> List[float]:
        if not text or not text.strip():
            raise EmbeddingProviderError("Cannot generate embedding for empty text")
        return self._generate_deterministic_vector(text.strip())

    async def embed_batch(self, texts: List[str], task_type: Optional[str] = None) -> List[List[float]]:
        if not texts:
            return []
        vectors: List[List[float]] = []
        for t in texts:
            vectors.append(await self.embed_text(t, task_type=task_type))
        return vectors


def get_embedding_provider(settings: Settings = default_settings) -> BaseEmbeddingProvider:
    """Return an initialized embedding provider instance matching the active configuration."""
    provider_name = settings.EMBEDDING_PROVIDER.lower().strip()

    if provider_name == "gemini":
        api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        return GeminiEmbeddingProvider(
            api_key=api_key,
            model_id=settings.EMBEDDING_MODEL,
            dimension=768,
        )
    elif provider_name == "mock":
        return MockEmbeddingProvider(dimension=768)
    else:
        raise EmbeddingProviderError(f"Unsupported EMBEDDING_PROVIDER: '{settings.EMBEDDING_PROVIDER}'")

