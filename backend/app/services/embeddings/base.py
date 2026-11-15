"""Abstract interface for replaceable embedding providers."""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingProvider(ABC):
    """Pluggable abstract interface for vector embedding providers.

    Does not lock the application into a specific dimension or model provider.
    """

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the vector dimension produced by this embedding provider."""
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Generate a vector embedding for a single text input."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for a batch of text inputs."""
        pass

