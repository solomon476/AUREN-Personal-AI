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
    assert provider.get_model_id() == "gemini-embedding-2"

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
    """Verify GeminiEmbeddingProvider masks secret API keys in string representation and defaults to gemini-embedding-2."""
    secret_key = "super-secret-gemini-api-key-12345"
    provider = GeminiEmbeddingProvider(api_key=secret_key, dimension=768)
    assert provider.get_dimension() == 768
    assert provider.get_model_id() == "gemini-embedding-2"

    repr_str = repr(provider)
    assert secret_key not in repr_str
    assert "***" in repr_str

    # Incompatible dimension rejected at construction
    with pytest.raises(EmbeddingDimensionError, match="expected 768"):
        GeminiEmbeddingProvider(api_key=secret_key, dimension=1536)


def test_gemini_embedding_provider_default_model():
    """Verify Settings and GeminiEmbeddingProvider default to gemini-embedding-2."""
    settings = Settings(
        ENVIRONMENT="test",
        JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )
    assert settings.EMBEDDING_MODEL == "gemini-embedding-2"

    provider = GeminiEmbeddingProvider(api_key="key")
    assert provider.get_model_id() == "gemini-embedding-2"
    assert provider.get_dimension() == 768


@pytest.mark.asyncio
async def test_gemini_provider_explicitly_requests_768_dimensions():
    """Verify Gemini provider explicitly passes output_dimensionality=768 to SDK client."""
    from unittest.mock import AsyncMock, MagicMock
    from google.genai import types

    provider = GeminiEmbeddingProvider(api_key="test-api-key", model_id="gemini-embedding-2", dimension=768)

    captured_configs = []

    async def mock_embed_content(*args, **kwargs):
        captured_configs.append(kwargs.get("config"))
        mock_resp = MagicMock()
        mock_emb = MagicMock()
        mock_emb.values = [0.01] * 768
        mock_resp.embeddings = [mock_emb]
        return mock_resp

    mock_client = MagicMock()
    mock_client.aio.models.embed_content = AsyncMock(side_effect=mock_embed_content)
    provider._client = mock_client

    # 1. Single text embedding
    vec = await provider.embed_text("sample document memory")
    assert len(vec) == 768
    assert len(captured_configs) == 1
    assert captured_configs[0].output_dimensionality == 768

    # 2. Batch embedding
    async def mock_embed_batch(*args, **kwargs):
        captured_configs.append(kwargs.get("config"))
        mock_resp = MagicMock()
        mock_emb1 = MagicMock()
        mock_emb1.values = [0.01] * 768
        mock_emb2 = MagicMock()
        mock_emb2.values = [0.02] * 768
        mock_resp.embeddings = [mock_emb1, mock_emb2]
        return mock_resp

    mock_client.aio.models.embed_content = AsyncMock(side_effect=mock_embed_batch)
    batch_vecs = await provider.embed_batch(["text1", "text2"])
    assert len(batch_vecs) == 2
    assert len(captured_configs) == 2
    assert captured_configs[1].output_dimensionality == 768


@pytest.mark.asyncio
async def test_query_and_document_embeddings_compatible_configuration():
    """Verify document (batch) and query (single) embedding generation produce identical dimension and model spaces."""
    provider = MockEmbeddingProvider(model_id="gemini-embedding-2", dimension=768)

    doc_text = "User loves Python programming"
    query_text = "What language does the user like?"

    # Document embedding
    doc_embeddings = await provider.embed_batch([doc_text])
    # Query embedding
    query_embedding = await provider.embed_text(query_text)

    assert len(doc_embeddings) == 1
    assert len(doc_embeddings[0]) == 768
    assert len(query_embedding) == 768
    assert provider.get_model_id() == "gemini-embedding-2"

    # Both vectors are finite and L2 normalized
    assert math.isclose(math.sqrt(sum(x * x for x in doc_embeddings[0])), 1.0, rel_tol=1e-3)
    assert math.isclose(math.sqrt(sum(x * x for x in query_embedding)), 1.0, rel_tol=1e-3)


@pytest.mark.asyncio
async def test_provider_failure_does_not_fabricate_embeddings():
    """Verify that provider failure raises appropriate exception without fabricating fake vectors."""
    from unittest.mock import AsyncMock, MagicMock

    provider = GeminiEmbeddingProvider(api_key="test-key", model_id="gemini-embedding-2", dimension=768)

    mock_client = MagicMock()
    mock_client.aio.models.embed_content = AsyncMock(side_effect=RuntimeError("Google API 503 Service Unavailable"))
    provider._client = mock_client

    with pytest.raises(EmbeddingProviderError, match="Gemini embedding error: Google API 503"):
        await provider.embed_text("test query")

    with pytest.raises(EmbeddingProviderError, match="Gemini batch embedding error: Google API 503"):
        await provider.embed_batch(["test doc"])


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

    # Gemini provider default
    gemini_default_settings = Settings(
        ENVIRONMENT="test",
        JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_API_KEY="test-gemini-emb-key",
    )
    p_gemini_def = get_embedding_provider(gemini_default_settings)
    assert isinstance(p_gemini_def, GeminiEmbeddingProvider)
    assert p_gemini_def.get_dimension() == 768
    assert p_gemini_def.get_model_id() == "gemini-embedding-2"

    # Gemini provider explicit model
    gemini_settings = Settings(
        ENVIRONMENT="test",
        JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_API_KEY="test-gemini-emb-key",
        EMBEDDING_MODEL="gemini-embedding-2",
    )
    p_gemini = get_embedding_provider(gemini_settings)
    assert isinstance(p_gemini, GeminiEmbeddingProvider)
    assert p_gemini.get_dimension() == 768
    assert p_gemini.get_model_id() == "gemini-embedding-2"

    # Unsupported provider
    bad_settings = Settings(
        ENVIRONMENT="test",
        JOURNAL_HMAC_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        EMBEDDING_PROVIDER="unsupported_provider",
    )
    with pytest.raises(EmbeddingProviderError, match="Unsupported EMBEDDING_PROVIDER"):
        get_embedding_provider(bad_settings)

