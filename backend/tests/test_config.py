"""Tests for application configuration validation, specifically JOURNAL_HMAC_SECRET fail-closed security rules."""

import os
from pathlib import Path
import subprocess
import sys
import pytest
from pydantic import SecretStr, ValidationError

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
    """Ensures secret values passed via kwargs never leak into exception messages or stringified ValidationErrors."""
    secret_attempt = "changeme"
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            JOURNAL_HMAC_SECRET=secret_attempt,
            _env_file=None,
        )
    exc = exc_info.value
    err_text = str(exc)
    err_repr = repr(exc)
    assert secret_attempt not in err_text, f"Secret was leaked in str(exc): {err_text}"
    assert secret_attempt not in err_repr, f"Secret was leaked in repr(exc): {err_repr}"
    for err in exc.errors():
        inp = err.get("input")
        if isinstance(inp, dict) and "JOURNAL_HMAC_SECRET" in inp:
            secret_in_error = inp["JOURNAL_HMAC_SECRET"]
            assert isinstance(secret_in_error, SecretStr)
            assert secret_attempt not in str(secret_in_error)
            assert secret_attempt not in repr(secret_in_error)


def test_env_var_secret_never_leaks_in_validation_error(monkeypatch):
    """Ensures secret values loaded from environment variables never leak into stringified ValidationErrors.

    Genuinely asserts that ValidationError is raised when an invalid secret is configured in the environment,
    and verifies that the plaintext secret is completely absent from str(exc), repr(exc), and exc.errors().
    """
    secret_attempt = "changeme"  # Known default guaranteed to fail production validation
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JOURNAL_HMAC_SECRET", secret_attempt)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    exc = exc_info.value
    err_text = str(exc)
    err_repr = repr(exc)
    assert secret_attempt not in err_text, f"Env secret was leaked in str(exc): {err_text}"
    assert secret_attempt not in err_repr, f"Env secret was leaked in repr(exc): {err_repr}"

    # Verify that in exc.errors(), the input value for JOURNAL_HMAC_SECRET is masked as SecretStr
    found_secret_entry = False
    for err in exc.errors():
        inp = err.get("input")
        if isinstance(inp, dict) and "JOURNAL_HMAC_SECRET" in inp:
            found_secret_entry = True
            secret_in_error = inp["JOURNAL_HMAC_SECRET"]
            assert isinstance(secret_in_error, SecretStr), "Secret in error input was not masked as SecretStr!"
            assert secret_attempt not in str(secret_in_error)
            assert secret_attempt not in repr(secret_in_error)
    assert found_secret_entry, "Expected JOURNAL_HMAC_SECRET in validation error input"

    # Also test with a known default dev secret in production
    dev_default = "auren_dev_hmac_secret_32_chars_long_entropy_ok!"
    monkeypatch.setenv("JOURNAL_HMAC_SECRET", dev_default)
    with pytest.raises(ValidationError) as exc_info_dev:
        Settings(_env_file=None)

    assert dev_default not in str(exc_info_dev.value)
    assert dev_default not in repr(exc_info_dev.value)


def test_baseline_leakage_demonstration_without_masking():
    """Proves requirement 5: confirms that without SecretMaskingSource, standard BaseSettings
    would leak the raw plaintext secret string directly into validation errors.
    """
    from pydantic_settings import BaseSettings as RawBaseSettings
    from pydantic import model_validator

    class RawUnmaskedSettings(RawBaseSettings):
        JOURNAL_HMAC_SECRET: SecretStr

        @model_validator(mode="after")
        def check(self):
            if self.JOURNAL_HMAC_SECRET.get_secret_value() == "changeme":
                raise ValueError("bad secret")
            return self

    with pytest.raises(ValidationError) as exc_info:
        RawUnmaskedSettings(JOURNAL_HMAC_SECRET="changeme")

    # Confirms that unmasked BaseSettings leaks plaintext into exc.errors() and str(exc)
    assert "changeme" in str(exc_info.value)
    raw_input_type = type(exc_info.value.errors()[0]["input"]["JOURNAL_HMAC_SECRET"])
    assert raw_input_type is str, "Expected raw unmasked BaseSettings to contain str"


def test_compatibility_against_minimum_pydantic_settings_2_4_0():
    """Verifies that Settings runs seamlessly under pydantic-settings 2.4.0 (declared minimum).

    Uses the committed fixture wheel in backend/tests/fixtures/ and fails explicitly if absent.
    """
    fixture_dir = Path(__file__).parent / "fixtures"
    wheel_path = fixture_dir / "pydantic_settings-2.4.0-py3-none-any.whl"

    if not wheel_path.exists():
        pytest.fail(f"Required minimum-version fixture wheel missing: {wheel_path}")

    code = f"""
import sys, os
sys.path.insert(0, {str(wheel_path)!r})
import pydantic_settings
assert pydantic_settings.__version__ == '2.4.0', f"Expected 2.4.0, got {{pydantic_settings.__version__}}"
print(f"VERIFYING_MINIMUM_VERSION={{pydantic_settings.__version__}}")

os.environ['ENVIRONMENT'] = 'test'
os.environ['JOURNAL_HMAC_SECRET'] = 'test_secret_for_compat_validation_123456'
sys.path.insert(0, 'backend')
from app.core.config import Settings
from pydantic import ValidationError

# 1. Valid construction with 2.4.0
s = Settings(ENVIRONMENT='development', JOURNAL_HMAC_SECRET='mysecret1234567890')
assert s.get_journal_hmac_secret() == 'mysecret1234567890'

# 2. Kwarg bad secret rejected without leaking
try:
    Settings(ENVIRONMENT='production', JOURNAL_HMAC_SECRET='changeme', _env_file=None)
    assert False, 'Should fail'
except ValidationError as e:
    assert 'cannot be a known default or insecure test value in production' in str(e)
    assert 'changeme' not in str(e)

# 3. Env var bad secret rejected without leaking
os.environ['ENVIRONMENT'] = 'production'
os.environ['JOURNAL_HMAC_SECRET'] = 'changeme'
try:
    Settings(_env_file=None)
    assert False, 'Should fail'
except ValidationError as e:
    assert 'cannot be a known default or insecure test value in production' in str(e)
    assert 'changeme' not in str(e)

print('MINIMUM_VERSION_2_4_0_VERIFIED_SUCCESSFULLY')
"""
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, f"pydantic-settings 2.4.0 compatibility check failed:\n{res.stderr}"
    assert "MINIMUM_VERSION_2_4_0_VERIFIED_SUCCESSFULLY" in res.stdout
    assert "VERIFYING_MINIMUM_VERSION=2.4.0" in res.stdout

