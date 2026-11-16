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


def test_production_low_variety_hmac_secret_rejected():
    # Only 1 unique character
    with pytest.raises(ValidationError, match="insufficient character variety"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="a" * 32,
        )

    # Only 2 unique characters
    with pytest.raises(ValidationError, match="insufficient character variety"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="ab" * 16,
        )


def test_production_predictable_sequence_hmac_secret_rejected():
    # Consecutive alphabet run >= 6
    with pytest.raises(ValidationError, match="predictable sequential characters"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="abcdefghijklmnopqrstuvwxyz!@#$%^",
        )

    # Consecutive digit run >= 6
    with pytest.raises(ValidationError, match="predictable sequential characters"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="0123456789abcdefghijklmnopqrstuv",
        )


def test_production_valid_hmac_secret_accepted():
    # Valid hex output (like 'openssl rand -hex 32')
    valid_hex = "8f3b2a1c9e4d5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a"
    cfg_hex = Settings(
        ENVIRONMENT="production",
        JOURNAL_HMAC_SECRET=valid_hex,
    )
    assert cfg_hex.get_journal_hmac_secret() == valid_hex
    assert valid_hex not in str(cfg_hex.JOURNAL_HMAC_SECRET)
    assert valid_hex not in repr(cfg_hex.JOURNAL_HMAC_SECRET)

    # Valid base64url output (like 'secrets.token_urlsafe(32)')
    valid_urlsafe = "D8s7F_3kL9m-Qz2wX4vB1nC6vM8kP0qR_tY5uI7oP9s"
    cfg_url = Settings(
        ENVIRONMENT="production",
        JOURNAL_HMAC_SECRET=valid_urlsafe,
    )
    assert cfg_url.get_journal_hmac_secret() == valid_urlsafe
    assert valid_urlsafe not in str(cfg_url.JOURNAL_HMAC_SECRET)
    assert valid_urlsafe not in repr(cfg_url.JOURNAL_HMAC_SECRET)


def test_staging_missing_hmac_secret_rejected():
    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in staging"):
        Settings(ENVIRONMENT="staging", JOURNAL_HMAC_SECRET=None)


def test_development_fallback_hmac_secret():
    cfg = Settings(ENVIRONMENT="development", JOURNAL_HMAC_SECRET=None)
    assert len(cfg.get_journal_hmac_secret()) >= 32

