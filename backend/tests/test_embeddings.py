"""Comprehensive test suite for vector embedding providers and validation invariants."""

import asyncio
import math
import pytest

from app.core.config import Settings
from app.services.embeddings.base import (
    EmbeddingAuthenticationError,
    EmbeddingDimensionError,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
    validate_embedding_vector,
)
from app.services.embeddings.factory import MockEmbeddingProvider, get_embedding_provider
from app.services.embeddings.gemini import GeminiEmbeddingProvider


def test_embedding_vector_validation_valid():
    """Verify validate_embedding_vector accepts clean 768-dim finite numeric vectors."""
    vec = [0.01 * (i % 50) for i in range(768)]
    clean = validate_embedding_vector(vec, expected_dimension=768)
    assert len(clean) == 768
    assert all(math.isfinite(x) for x in clean)


def test_embedding_vector_validation_invalid_dimension():
    """Verify dimension mismatch raises EmbeddingDimensionError."""
    with pytest.raises(EmbeddingDimensionError, match="expected 768, got 512"):
        validate_embedding_vector([0.1] * 512, expected_dimension=768)

    with pytest.raises(EmbeddingDimensionError, match="expected 768, got 1024"):
        validate_embedding_vector([0.1] * 1024, expected_dimension=768)


def test_embedding_vector_validation_non_finite_values():
    """Verify NaN and Inf values are strictly rejected."""
    nan_vec = [0.1] * 768
    nan_vec[10] = float("nan")
    with pytest.raises(EmbeddingProviderError, match="Non-finite numeric value"):
        validate_embedding_vector(nan_vec, expected_dimension=768)

    inf_vec = [0.1] * 768
    inf_vec[20] = float("inf")
    with pytest.raises(EmbeddingProviderError, match="Non-finite numeric value"):
        validate_embedding_vector(inf_vec, expected_dimension=768)

    neg_inf_vec = [0.1] * 768
    neg_inf_vec[30] = float("-inf")
    with pytest.raises(EmbeddingProviderError, match="Non-finite numeric value"):
        validate_embedding_vector(neg_inf_vec, expected_dimension=768)


def test_embedding_vector_validation_non_numeric():
    """Verify non-numeric types are rejected."""
    bad_vec = [0.1] * 768
    bad_vec[5] = "not_a_number"
    with pytest.raises(EmbeddingProviderError, match="Invalid non-numeric value"):
        validate_embedding_vector(bad_vec, expected_dimension=768)


@pytest.mark.asyncio
async def test_mock_embedding_provider_deterministic_generation():
    """Verify MockEmbeddingProvider generates normalized 768-dim vectors deterministically."""
    provider = MockEmbeddingProvider(dimension=768)
    assert provider.get_dimension() == 768
    assert provider.get_model_id() == "mock-embedding-v1"

    vec1 = await provider.embed_text("user likes dark mode")
    vec2 = await provider.embed_text("user likes dark mode")
    vec_different = await provider.embed_text("user lives in Zurich")

    assert len(vec1) == 768
    assert vec1 == vec2  # Deterministic
    assert vec1 != vec_different  # Distinguishable

    # Check L2 normalization: norm should be ~1.0
    norm = math.sqrt(sum(x * x for x in vec1))
    assert abs(norm - 1.0) < 1e-4


@pytest.mark.asyncio
async def test_mock_embedding_provider_batch():
    """Verify batch embedding operation preserves ordering and dimensions."""
    provider = MockEmbeddingProvider(dimension=768)
    texts = ["First statement", "Second statement", "Third statement"]
    vectors = await provider.embed_batch(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 768

    # Empty batch returns empty list
    assert await provider.embed_batch([]) == []


@pytest.mark.asyncio
async def test_mock_embedding_provider_rejections():
    """Verify empty text rejection."""
    provider = MockEmbeddingProvider(dimension=768)
    with pytest.raises(EmbeddingProviderError, match="Cannot generate embedding for empty text"):
        await provider.embed_text("")
    with pytest.raises(EmbeddingProviderError, match="Cannot generate embedding for empty text"):
        await provider.embed_text("   ")


@pytest.mark.asyncio
async def test_mock_embedding_provider_failure_simulations():
    """Verify timeout, auth, and non-finite simulation hooks."""
    timeout_provider = MockEmbeddingProvider(simulate_timeout=True)
    with pytest.raises(EmbeddingTimeoutError, match="timeout"):
        await timeout_provider.embed_text("text")

    auth_provider = MockEmbeddingProvider(simulate_auth_error=True)
    with pytest.raises(EmbeddingAuthenticationError, match="authentication"):
        await auth_provider.embed_text("text")

    dim_provider = MockEmbeddingProvider(simulate_invalid_dimension=512)
    with pytest.raises(EmbeddingDimensionError, match="expected 768, got 512"):
        await dim_provider.embed_text("text")

    nan_provider = MockEmbeddingProvider(simulate_non_finite=True)
    with pytest.raises(EmbeddingProviderError, match="Non-finite"):
        await nan_provider.embed_text("text")


def test_gemini_embedding_provider_init_and_secret_masking():
    """Verify GeminiEmbeddingProvider masks secret API keys in string representation."""
    secret_key = "super-secret-gemini-api-key-12345"
    provider = GeminiEmbeddingProvider(api_key=secret_key, model_id="text-embedding-004", dimension=768)
    assert provider.get_dimension() == 768
    assert provider.get_model_id() == "text-embedding-004"

    repr_str = repr(provider)
    assert secret_key not in repr_str
    assert "***" in repr_str

    # Incompatible dimension rejected at construction
    with pytest.raises(EmbeddingDimensionError, match="expected 768"):
        GeminiEmbeddingProvider(api_key=secret_key, dimension=1536)


def test_gemini_embedding_provider_unconfigured_auth_error():
    """Verify invoking unconfigured Gemini provider raises EmbeddingAuthenticationError without leaking."""
    provider = GeminiEmbeddingProvider(api_key=None, dimension=768)
    with pytest.raises(EmbeddingAuthenticationError, match="API key is unconfigured"):
        asyncio.run(provider.embed_text("sample text"))


def test_gemini_embedding_provider_empty_text_error():
    """Verify empty text rejected before network call."""
    provider = GeminiEmbeddingProvider(api_key="fake-key", dimension=768)
    with pytest.raises(EmbeddingProviderError, match="Cannot generate embedding for empty"):
        asyncio.run(provider.embed_text(""))


def test_embedding_factory():
    """Verify get_embedding_provider correctly resolves configured providers."""
    # Mock provider
    mock_settings = Settings(
        ENVIRONMENT="test",
        JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        EMBEDDING_PROVIDER="mock",
    )
    p_mock = get_embedding_provider(mock_settings)
    assert isinstance(p_mock, MockEmbeddingProvider)
    assert p_mock.get_dimension() == 768

    # Gemini provider
    gemini_settings = Settings(
        ENVIRONMENT="test",
        JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_API_KEY="test-gemini-emb-key",
        EMBEDDING_MODEL="text-embedding-004",
    )
    p_gemini = get_embedding_provider(gemini_settings)
    assert isinstance(p_gemini, GeminiEmbeddingProvider)
    assert p_gemini.get_dimension() == 768
    assert p_gemini.get_model_id() == "text-embedding-004"

    # Unsupported provider
    bad_settings = Settings(
        ENVIRONMENT="test",
        JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        EMBEDDING_PROVIDER="unsupported_provider",
    )
    with pytest.raises(EmbeddingProviderError, match="Unsupported EMBEDDING_PROVIDER"):
        get_embedding_provider(bad_settings)
