"""Google Gemini embedding provider adapter using official google-genai SDK."""

import asyncio
import logging
from typing import List, Optional

from app.services.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingAuthenticationError,
    EmbeddingDimensionError,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
    validate_embedding_vector,
)

logger = logging.getLogger(__name__)

SUPPORTED_GEMINI_EMBEDDING_MODELS = {
    "gemini-embedding-2": 768,
    "text-embedding-004": 768,  # retired on 14 Jan 2026; retained for backward compatibility / validation
}


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Adapter for Google Gemini embedding models via google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: str = "gemini-embedding-2",
        dimension: int = 768,
        timeout_seconds: float = 30.0,
    ):
        self._api_key = api_key
        self.model_id = model_id
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds
        self._client = None

        if self.dimension != 768:
            raise EmbeddingDimensionError(
                f"Configured dimension {self.dimension} is incompatible with PostgreSQL schema (expected 768)"
            )

        if self.model_id == "text-embedding-004":
            raise EmbeddingProviderError(
                "Model 'text-embedding-004' was retired on 14 January 2026 and cannot be used for new embedding generation; "
                "use 'gemini-embedding-2' instead"
            )

        if self._api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except Exception as exc:
                sanitized = self._sanitize_message(str(exc))
                raise EmbeddingProviderError(f"Could not initialize google-genai Client: {sanitized}") from exc

    def get_dimension(self) -> int:
        return self.dimension

    def get_model_id(self) -> str:
        return self.model_id

    def get_provider_name(self) -> str:
        return "gemini"

    def get_version(self) -> str:
        return "v1"

    def _ensure_authenticated_client(self):
        """Verify client and credentials availability before invocation."""
        if not self._api_key:
            raise EmbeddingAuthenticationError("Gemini embedding API key is unconfigured")
        if self._client is None:
            raise EmbeddingAuthenticationError("Gemini client initialization failed")

    def __repr__(self) -> str:
        key_repr = "***" if self._api_key else "None"
        return f"<GeminiEmbeddingProvider model={self.model_id} dim={self.dimension} api_key={key_repr}>"

    def _sanitize_message(self, message: str) -> str:
        """Strip raw API key if present in error message."""
        if self._api_key and self._api_key in message:
            return message.replace(self._api_key, "[REDACTED]")
        return message

    def _ensure_authenticated_client(self):
        """Verify client and credentials availability before invocation."""
        if not self._api_key:
            raise EmbeddingAuthenticationError("Gemini embedding API key is unconfigured")
        if self._client is None:
            raise EmbeddingAuthenticationError("Gemini client initialization failed")

    async def embed_text(self, text: str, task_type: Optional[str] = None) -> List[float]:
        """Generate a 768-dimensional vector embedding for a single text input."""
        if not text or not text.strip():
            raise EmbeddingProviderError("Cannot generate embedding for empty or whitespace-only text")

        self._ensure_authenticated_client()

        from google.genai import types

        config = types.EmbedContentConfig(
            output_dimensionality=self.dimension,
            task_type=task_type,
        )
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.embed_content(
                    model=self.model_id,
                    contents=text.strip(),
                    config=config,
                ),
                timeout=self.timeout_seconds,
            )

            if not response.embeddings:
                raise EmbeddingProviderError("Gemini API returned empty embeddings list")

            first_emb = response.embeddings[0]
            if not hasattr(first_emb, "values") or first_emb.values is None:
                raise EmbeddingProviderError("Gemini API returned embedding without values")

            return validate_embedding_vector(first_emb.values, expected_dimension=self.dimension)

        except asyncio.TimeoutError:
            raise EmbeddingTimeoutError(
                f"Embedding request to Gemini model '{self.model_id}' timed out after {self.timeout_seconds}s"
            )
        except (EmbeddingDimensionError, EmbeddingProviderError, EmbeddingAuthenticationError, EmbeddingTimeoutError):
            raise
        except Exception as exc:
            err_msg = self._sanitize_message(str(exc))
            err_lower = err_msg.lower()
            if any(term in err_lower for term in ("unauthenticated", "invalid api key", "permission_denied", "401", "403")):
                raise EmbeddingAuthenticationError(f"Gemini embedding authentication failed: {err_msg}")
            raise EmbeddingProviderError(f"Gemini embedding error: {err_msg}")

    async def embed_batch(self, texts: List[str], task_type: Optional[str] = None) -> List[List[float]]:
        """Generate 768-dimensional vector embeddings for a batch of text inputs."""
        if not texts:
            return []

        cleaned_texts: List[str] = []
        for idx, t in enumerate(texts):
            if not t or not t.strip():
                raise EmbeddingProviderError(f"Cannot generate embedding for empty text at batch index {idx}")
            cleaned_texts.append(t.strip())

        self._ensure_authenticated_client()

        from google.genai import types

        config = types.EmbedContentConfig(
            output_dimensionality=self.dimension,
            task_type=task_type,
        )
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.embed_content(
                    model=self.model_id,
                    contents=cleaned_texts,
                    config=config,
                ),
                timeout=self.timeout_seconds,
            )

            if not response.embeddings or len(response.embeddings) != len(cleaned_texts):
                raise EmbeddingProviderError(
                    f"Gemini API returned {len(response.embeddings) if response.embeddings else 0} embeddings "
                    f"for {len(cleaned_texts)} input texts"
                )

            vectors: List[List[float]] = []
            for idx, emb in enumerate(response.embeddings):
                if not hasattr(emb, "values") or emb.values is None:
                    raise EmbeddingProviderError(f"Gemini API returned embedding without values at index {idx}")
                vectors.append(validate_embedding_vector(emb.values, expected_dimension=self.dimension))

            return vectors

        except asyncio.TimeoutError:
            raise EmbeddingTimeoutError(
                f"Batch embedding request to Gemini model '{self.model_id}' timed out after {self.timeout_seconds}s"
            )
        except (EmbeddingDimensionError, EmbeddingProviderError, EmbeddingAuthenticationError, EmbeddingTimeoutError):
            raise
        except Exception as exc:
            err_msg = self._sanitize_message(str(exc))
            err_lower = err_msg.lower()
            if any(term in err_lower for term in ("unauthenticated", "invalid api key", "permission_denied", "401", "403")):
                raise EmbeddingAuthenticationError(f"Gemini embedding authentication failed: {err_msg}")
            raise EmbeddingProviderError(f"Gemini batch embedding error: {err_msg}")

