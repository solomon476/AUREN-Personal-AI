"""Tests for application configuration validation, specifically JOURNAL_HMAC_SECRET security rules."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_missing_hmac_secret_rejected():
    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in production"):
        Settings(ENVIRONMENT="production", JOURNAL_HMAC_SECRET=None)


def test_production_known_default_hmac_secret_rejected():
    with pytest.raises(ValidationError, match="cannot be a known default or insecure test value in production"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="auren-journal-hmac-test-secret-change-in-prod",
        )

    with pytest.raises(ValidationError, match="cannot be a known default or insecure test value in production"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="changeme",
        )


def test_production_short_hmac_secret_rejected():
    with pytest.raises(ValidationError, match="must be at least 32 characters"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="short-secret-under-32-chars",
        )


def test_production_valid_hmac_secret_accepted():
    valid_secret = "auren_super_secure_production_hmac_key_2026_512bits_entropy"
    cfg = Settings(
        ENVIRONMENT="production",
        JOURNAL_HMAC_SECRET=valid_secret,
    )
    assert cfg.get_journal_hmac_secret() == valid_secret
    # Ensure raw secret is not exposed in string conversion
    assert valid_secret not in str(cfg.JOURNAL_HMAC_SECRET)
    assert "**********" in str(cfg.JOURNAL_HMAC_SECRET)


def test_staging_missing_hmac_secret_rejected():
    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in staging"):
        Settings(ENVIRONMENT="staging", JOURNAL_HMAC_SECRET=None)


def test_development_fallback_hmac_secret():
    cfg = Settings(ENVIRONMENT="development", JOURNAL_HMAC_SECRET=None)
    assert len(cfg.get_journal_hmac_secret()) >= 32
