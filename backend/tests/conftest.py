"""Pytest configuration and environment-specific fixtures for AUREN tests.

Ensures that tests do not depend on a globally configured secret on the host OS.
"""

import os
import secrets
import pytest

# Ensure test session runs in test environment with an explicit test secret
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "JOURNAL_HMAC_SECRET",
    "test_conftest_hmac_secret_32_chars_entropy_ok_12345",
)


@pytest.fixture
def valid_hmac_secret() -> str:
    """Returns a cryptographically secure random 32-byte hex secret."""
    return secrets.token_hex(32)


@pytest.fixture
def dev_test_secret() -> str:
    """Returns an explicit development secret meeting minimum length."""
    return "dev_explicit_secret_32_chars_entropy_ok!"


@pytest.fixture
def development_env(monkeypatch, dev_test_secret) -> dict:
    """Environment fixture for local development settings."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JOURNAL_HMAC_SECRET", dev_test_secret)
    return {"ENVIRONMENT": "development", "JOURNAL_HMAC_SECRET": dev_test_secret}


@pytest.fixture
def staging_env(monkeypatch, valid_hmac_secret) -> dict:
    """Environment fixture for staging environment with cryptographic secret."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("JOURNAL_HMAC_SECRET", valid_hmac_secret)
    return {"ENVIRONMENT": "staging", "JOURNAL_HMAC_SECRET": valid_hmac_secret}


@pytest.fixture
def production_env(monkeypatch, valid_hmac_secret) -> dict:
    """Environment fixture for production environment with cryptographic secret."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JOURNAL_HMAC_SECRET", valid_hmac_secret)
    return {"ENVIRONMENT": "production", "JOURNAL_HMAC_SECRET": valid_hmac_secret}
