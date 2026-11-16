"""Tests for application configuration validation, specifically JOURNAL_HMAC_SECRET fail-closed security rules."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_missing_hmac_secret_rejected(monkeypatch):
    monkeypatch.delenv("JOURNAL_HMAC_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in production"):
        Settings(ENVIRONMENT="production", JOURNAL_HMAC_SECRET=None, _env_file=None)

    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in production"):
        Settings(ENVIRONMENT="production", JOURNAL_HMAC_SECRET="", _env_file=None)

    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in production"):
        Settings(ENVIRONMENT="production", JOURNAL_HMAC_SECRET="   ", _env_file=None)


def test_staging_missing_hmac_secret_rejected(monkeypatch):
    monkeypatch.delenv("JOURNAL_HMAC_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in staging"):
        Settings(ENVIRONMENT="staging", JOURNAL_HMAC_SECRET=None, _env_file=None)

    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in staging"):
        Settings(ENVIRONMENT="staging", JOURNAL_HMAC_SECRET="", _env_file=None)


def test_development_missing_hmac_secret_rejected_no_silent_fallback(monkeypatch):
    """Verifies that development fails closed when no secret is provided (silent fallback removed)."""
    monkeypatch.delenv("JOURNAL_HMAC_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in development"):
        Settings(ENVIRONMENT="development", JOURNAL_HMAC_SECRET=None, _env_file=None)

    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in development"):
        Settings(ENVIRONMENT="development", JOURNAL_HMAC_SECRET="", _env_file=None)


def test_test_environment_missing_hmac_secret_rejected(monkeypatch):
    """Verifies that test environment also requires an explicit secret."""
    monkeypatch.delenv("JOURNAL_HMAC_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JOURNAL_HMAC_SECRET must be explicitly configured in test"):
        Settings(ENVIRONMENT="test", JOURNAL_HMAC_SECRET=None, _env_file=None)


def test_unsupported_environment_rejected(monkeypatch, valid_hmac_secret):
    for bad_env in ["prod", "dev", "sandbox", "stage", "testing", "invalid_env"]:
        with pytest.raises(ValidationError, match="Unsupported ENVIRONMENT"):
            Settings(ENVIRONMENT=bad_env, JOURNAL_HMAC_SECRET=valid_hmac_secret, _env_file=None)


def test_production_known_default_hmac_secret_rejected():
    insecure_defaults = [
        "auren-journal-hmac-test-secret-change-in-prod",
        "auren_dev_hmac_secret_32_chars_long_entropy_ok!",
        "auren_test_hmac_secret_32_chars_dev_only!!",
        "test_default_hmac_secret_32_chars_entropy_ok!",
        "changeme",
        "password",
        "default",
        "test",
        "1234567890",
        "admin",
    ]
    for bad_secret in insecure_defaults:
        with pytest.raises(ValidationError, match="cannot be a known default or insecure test value in production"):
            Settings(
                ENVIRONMENT="production",
                JOURNAL_HMAC_SECRET=bad_secret,
                _env_file=None,
            )


def test_staging_known_default_hmac_secret_rejected():
    with pytest.raises(ValidationError, match="cannot be a known default or insecure test value in staging"):
        Settings(
            ENVIRONMENT="staging",
            JOURNAL_HMAC_SECRET="auren_dev_hmac_secret_32_chars_long_entropy_ok!",
            _env_file=None,
        )


def test_development_explicit_secret_accepted():
    # Valid explicit development secret (>= 16 characters)
    dev_secret = "dev_secret_16chr"
    cfg = Settings(ENVIRONMENT="development", JOURNAL_HMAC_SECRET=dev_secret, _env_file=None)
    assert cfg.get_journal_hmac_secret() == dev_secret

    # Too short (< 16 chars) rejected even in development
    with pytest.raises(ValidationError, match="must be at least 16 characters in development"):
        Settings(ENVIRONMENT="development", JOURNAL_HMAC_SECRET="short-dev", _env_file=None)


def test_production_short_hmac_secret_rejected():
    with pytest.raises(ValidationError, match="must be at least 32 characters"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="short-secret-under-32-chars",
            _env_file=None,
        )


def test_production_low_variety_hmac_secret_rejected():
    # Only 1 unique character
    with pytest.raises(ValidationError, match="insufficient character variety"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="a" * 32,
            _env_file=None,
        )

    # Only 2 unique characters
    with pytest.raises(ValidationError, match="insufficient character variety"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="ab" * 16,
            _env_file=None,
        )


def test_production_predictable_sequence_hmac_secret_rejected():
    # Consecutive alphabet run >= 6
    with pytest.raises(ValidationError, match="predictable sequential characters"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="abcdefghijklmnopqrstuvwxyz!@#$%^",
            _env_file=None,
        )

    # Consecutive digit run >= 6
    with pytest.raises(ValidationError, match="predictable sequential characters"):
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET="0123456789abcdefghijklmnopqrstuv",
            _env_file=None,
        )


def test_production_valid_hmac_secret_accepted():
    # Valid hex output (like 'openssl rand -hex 32')
    valid_hex = "8f3b2a1c9e4d5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a"
    cfg_hex = Settings(
        ENVIRONMENT="production",
        JOURNAL_HMAC_SECRET=valid_hex,
        _env_file=None,
    )
    assert cfg_hex.get_journal_hmac_secret() == valid_hex
    assert valid_hex not in str(cfg_hex.JOURNAL_HMAC_SECRET)
    assert valid_hex not in repr(cfg_hex.JOURNAL_HMAC_SECRET)

    # Valid base64url output (like 'secrets.token_urlsafe(32)')
    valid_urlsafe = "D8s7F_3kL9m-Qz2wX4vB1nC6vM8kP0qR_tY5uI7oP9s"
    cfg_url = Settings(
        ENVIRONMENT="production",
        JOURNAL_HMAC_SECRET=valid_urlsafe,
        _env_file=None,
    )
    assert cfg_url.get_journal_hmac_secret() == valid_urlsafe
    assert valid_urlsafe not in str(cfg_url.JOURNAL_HMAC_SECRET)
    assert valid_urlsafe not in repr(cfg_url.JOURNAL_HMAC_SECRET)


def test_configuration_error_never_leaks_secret():
    """Ensures secret values never leak into exception messages or stringified ValidationErrors."""
    secret_attempt = "super_secret_forbidden_value_123456"
    try:
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET=secret_attempt,
            _env_file=None,
        )
    except ValidationError as exc:
        err_text = str(exc)
        assert secret_attempt not in err_text, f"Secret was leaked in ValidationError: {err_text}"
