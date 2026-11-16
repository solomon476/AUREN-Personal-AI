"""Queue error sanitization module for memory extraction worker jobs.

Ensures that errors persisted to `memory_extraction_jobs.last_error` never leak:
1. API keys (OpenAI, Gemini, GitHub, etc.)
2. Bearer tokens, JWTs, and HMAC secrets
3. Passwords, authorization headers, or database credentials
4. Raw user message content or private journal entries
"""

import re
from typing import Union


# Regex patterns for sensitive credential redacting
API_KEY_REGEX = re.compile(
    r"(sk-[a-zA-Z0-9_\-]{8,}|AIza[a-zA-Z0-9_\-]{20,}|gh[pousr]_[a-zA-Z0-9]{20,}|xox[baprs]-[a-zA-Z0-9_\-]{10,})",
)
BEARER_REGEX = re.compile(r"Bearer\s+[a-zA-Z0-9._\-]+", re.IGNORECASE)
JWT_REGEX = re.compile(r"ey[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}(\.[a-zA-Z0-9_\-]+)?")
KEY_VALUE_SECRET_REGEX = re.compile(
    r"(?i)(password|secret|key|token|authorization|apikey)\s*[:=]\s*['\"]?[^\s,'\"]+"
)
HEX_HASH_REGEX = re.compile(r"\b[a-f0-9]{32,64}\b", re.IGNORECASE)


def categorize_error(error_str: str) -> str:
    """Categorizes error text into standard diagnostic error codes."""
    lower = error_str.lower()
    if any(k in lower for k in ("rate limit", "429", "quota", "resource_exhausted")):
        return "[RATE_LIMIT]"
    if any(k in lower for k in ("timeout", "timed out", "deadline_exceeded", "504")):
        return "[TIMEOUT]"
    if any(k in lower for k in ("unauthorized", "unauthenticated", "401", "403", "forbidden", "api key invalid")):
        return "[AUTH_ERROR]"
    if any(k in lower for k in ("context length", "maximum context", "token limit", "too many tokens")):
        return "[CONTEXT_LENGTH]"
    if any(k in lower for k in ("503", "service unavailable", "bad gateway", "connection refused", "502")):
        return "[PROVIDER_UNAVAILABLE]"
    if any(k in lower for k in ("invalid argument", "bad request", "400", "validation error")):
        return "[INVALID_REQUEST]"
    return "[EXTRACTION_FAILED]"


def sanitize_extraction_error(error: Union[Exception, str], max_length: int = 500) -> str:
    """Sanitizes an exception or raw error message before persisting to the database.

    - Classifies the error with a standardized diagnostic category.
    - Strips API keys, Bearer tokens, JWTs, and credential assignments.
    - Limits overall length to prevent log flooding.
    """
    raw_text = str(error).strip() if error else "Extraction failed without specific error details"
    category = categorize_error(raw_text)

    # Apply redactions
    cleaned = API_KEY_REGEX.sub("[REDACTED_API_KEY]", raw_text)
    cleaned = BEARER_REGEX.sub("Bearer [REDACTED_TOKEN]", cleaned)
    cleaned = JWT_REGEX.sub("[REDACTED_JWT]", cleaned)
    cleaned = KEY_VALUE_SECRET_REGEX.sub(r"\1=[REDACTED]", cleaned)
    cleaned = HEX_HASH_REGEX.sub("[REDACTED_HEX]", cleaned)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Prepend category if not already prefixed
    if not cleaned.startswith("["):
        final_str = f"{category} {cleaned}"
    else:
        final_str = cleaned

    if len(final_str) > max_length:
        final_str = final_str[: max_length - 3] + "..."

    return final_str
