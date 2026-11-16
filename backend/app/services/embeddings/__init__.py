"""Embeddings package providing replaceable vector embedding providers."""

from app.services.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingAuthenticationError,
    EmbeddingDimensionError,
    EmbeddingException,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
    validate_embedding_vector,
)
from app.services.embeddings.factory import MockEmbeddingProvider, get_embedding_provider
from app.services.embeddings.gemini import GeminiEmbeddingProvider

__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingException",
    "EmbeddingProviderError",
    "EmbeddingDimensionError",
    "EmbeddingAuthenticationError",
    "EmbeddingTimeoutError",
    "validate_embedding_vector",
    "GeminiEmbeddingProvider",
    "MockEmbeddingProvider",
    "get_embedding_provider",
]
