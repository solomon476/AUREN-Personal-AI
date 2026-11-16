"""Abstract interface and exceptions for replaceable vector embedding providers."""

import math
from abc import ABC, abstractmethod
from typing import List


class EmbeddingException(Exception):
    """Base exception for all embedding-related failures."""
    pass


class EmbeddingProviderError(EmbeddingException):
    """General provider-level error (API failure, non-finite values, malformed response)."""
    pass


class EmbeddingDimensionError(EmbeddingException):
    """Raised when generated embedding dimension differs from expected dimension."""
    pass


class EmbeddingAuthenticationError(EmbeddingException):
    """Raised when API credentials are missing, invalid, or unauthorized."""
    pass


class EmbeddingTimeoutError(EmbeddingException):
    """Raised when embedding generation request times out."""
    pass


def validate_embedding_vector(vector: List[float], expected_dimension: int = 768) -> List[float]:
    """Validates that a returned vector matches expected dimension and has finite values.

    Never silently truncates, pads, or fabricates values.
    """
    if not isinstance(vector, (list, tuple)):
        raise EmbeddingProviderError(f"Embedding vector must be a list of floats, got {type(vector).__name__}")

    if len(vector) != expected_dimension:
        raise EmbeddingDimensionError(
            f"Embedding dimension mismatch: expected {expected_dimension}, got {len(vector)}"
        )

    clean_vector: List[float] = []
    for idx, val in enumerate(vector):
        if not isinstance(val, (int, float)):
            raise EmbeddingProviderError(f"Invalid non-numeric value at index {idx}: {type(val).__name__}")
        f_val = float(val)
        if not math.isfinite(f_val):
            raise EmbeddingProviderError(
                f"Non-finite numeric value (NaN or Inf) detected at vector index {idx}"
            )
        clean_vector.append(f_val)

    return clean_vector


class BaseEmbeddingProvider(ABC):
    """Pluggable abstract interface for vector embedding providers.

    Does not lock the application into a specific dimension or model provider.
    """

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the vector dimension produced by this embedding provider."""
        pass

    @abstractmethod
    def get_model_id(self) -> str:
        """Return the model identifier."""
        pass

    def get_provider_name(self) -> str:
        """Return the provider identifier (e.g. 'gemini')."""
        return "gemini"

    def get_version(self) -> str:
        """Return the model release/version string (e.g. 'v1')."""
        return "v1"

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Generate a vector embedding for a single text input."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for a batch of text inputs."""
        pass
