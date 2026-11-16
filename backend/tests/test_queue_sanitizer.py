"""Unit tests for memory extraction queue error sanitization."""

from app.services.memory.queue_sanitizer import (
    sanitize_extraction_error,
    categorize_error,
)


def test_api_key_redaction():
    error_msg = (
        "Provider error from OpenAI: sk-ant-api03-abcdef1234567890_XYZ and Gemini key AIzaSyA1234567890abcdef12345 failed."
    )
    sanitized = sanitize_extraction_error(error_msg)
    assert "sk-ant-api03" not in sanitized
    assert "AIzaSyA1234567890" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized


def test_bearer_and_jwt_redaction():
    error_msg = (
        "Authentication failed with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc"
    )
    sanitized = sanitize_extraction_error(error_msg)
    assert "eyJhbGci" not in sanitized
    assert "Bearer [REDACTED_TOKEN]" in sanitized or "[REDACTED_JWT]" in sanitized


def test_password_and_credential_assignment_redaction():
    error_msg = "Database connection error: password=superSecretPassword123 with apiKey: a1b2c3d4e5f6g7h8"
    sanitized = sanitize_extraction_error(error_msg)
    assert "superSecretPassword123" not in sanitized
    assert "password=[REDACTED]" in sanitized or "apiKey=[REDACTED]" in sanitized


def test_hex_hash_redaction():
    error_msg = "Failed with HMAC digest: 8f3b2a1c9e4d5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a"
    sanitized = sanitize_extraction_error(error_msg)
    assert "8f3b2a1c9e4d" not in sanitized
    assert "[REDACTED_HEX]" in sanitized


def test_error_categorization():
    assert categorize_error("Error 429: Resource exhausted, quota exceeded") == "[RATE_LIMIT]"
    assert categorize_error("Request timed out after 30.0s deadline_exceeded") == "[TIMEOUT]"
    assert categorize_error("401 Unauthorized: Invalid API key") == "[AUTH_ERROR]"
    assert categorize_error("Maximum context length exceeded (8192 tokens)") == "[CONTEXT_LENGTH]"
    assert categorize_error("503 Service Unavailable") == "[PROVIDER_UNAVAILABLE]"
    assert categorize_error("Validation error: field 'x' required") == "[INVALID_REQUEST]"


def test_max_length_truncation():
    long_msg = "A" * 1000
    sanitized = sanitize_extraction_error(long_msg, max_length=100)
    assert len(sanitized) <= 100
    assert sanitized.endswith("...")
