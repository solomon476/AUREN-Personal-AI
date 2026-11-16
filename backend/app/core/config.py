"""Application configuration module using Pydantic Settings."""

from collections import Counter
import math
from typing import List, Optional, Set
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWN_INSECURE_SECRETS: Set[str] = {
    "auren-journal-hmac-test-secret-change-in-prod",
    "changeme",
    "secret",
    "password",
    "default",
    "test",
    "1234567890",
    "admin",
    "root",
}


def calculate_shannon_entropy(s: str) -> float:
    """Calculates Shannon entropy in bits per character."""
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def validate_cryptographic_secret_strength(secret_val: str, env: str) -> None:
    """Validates that a secret is a securely generated cryptographic secret.

    Cryptographic secret generation methods:
      - OpenSSL (CLI): openssl rand -hex 32
      - Python:        python3 -c "import secrets; print(secrets.token_urlsafe(32))"

    Never reveals the secret value in exception messages or logs.
    """
    if secret_val.lower() in KNOWN_INSECURE_SECRETS:
        raise ValueError(
            f"JOURNAL_HMAC_SECRET cannot be a known default or insecure test value in {env}."
        )

    if len(secret_val) < 32:
        raise ValueError(
            f"JOURNAL_HMAC_SECRET must be at least 32 characters (256 bits) in {env}; got {len(secret_val)} characters."
        )

    # Reject low character variety
    unique_count = len(set(secret_val))
    if unique_count < 12:
        raise ValueError(
            f"JOURNAL_HMAC_SECRET has insufficient character variety ({unique_count} unique characters in {env}). "
            f"Use a cryptographic secret generated with: openssl rand -hex 32"
        )

    # Reject low Shannon entropy
    entropy = calculate_shannon_entropy(secret_val)
    if entropy < 3.0:
        raise ValueError(
            f"JOURNAL_HMAC_SECRET has insufficient entropy ({entropy:.2f} bits/character < 3.0 required in {env}). "
            f"Use a cryptographic secret generated with: openssl rand -hex 32"
        )

    # Reject predictable sequential characters (e.g. '12345678' or 'abcdefgh')
    consecutive_run = 1
    for i in range(len(secret_val) - 1):
        if ord(secret_val[i + 1]) == ord(secret_val[i]) + 1:
            consecutive_run += 1
            if consecutive_run >= 6:
                raise ValueError(
                    f"JOURNAL_HMAC_SECRET contains predictable sequential characters in {env}. "
                    f"Use a cryptographic secret generated with: openssl rand -hex 32"
                )
        else:
            consecutive_run = 1


class Settings(BaseSettings):
    """Central configuration for the AUREN backend application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    APP_NAME: str = "AUREN Personal AI API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", description="development, staging, or production")
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Supabase Configuration
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = None
    SUPABASE_JWKS_URL: Optional[str] = None

    # Replaceable AI Provider Configuration
    LLM_PROVIDER: str = "gemini"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-2.5-flash"

    # Replaceable Embedding Provider Configuration
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-004"

    # Chat & Stream Configuration
    CHAT_REPOSITORY_TYPE: str = Field(default="auto", description="'auto', 'supabase', or 'sqlite'")
    CHAT_MAX_MESSAGE_LENGTH: int = 10000
    CHAT_STREAM_TIMEOUT_SECONDS: int = 60
    CHAT_STREAM_HEARTBEAT_SECONDS: float = 15.0
    CHAT_HISTORY_LIMIT: int = 10

    # Journal Privacy & Consent Configuration
    JOURNAL_HMAC_SECRET: Optional[SecretStr] = Field(
        default=None,
        description="Backend HMAC secret for journal consent verification (minimum 32 characters in staging/production)",
    )

    @model_validator(mode="after")
    def validate_journal_hmac_secret(self) -> "Settings":
        env = (self.ENVIRONMENT or "development").lower()
        secret_val = self.JOURNAL_HMAC_SECRET.get_secret_value() if self.JOURNAL_HMAC_SECRET else None

        if env in ("production", "staging"):
            if not secret_val:
                raise ValueError(
                    f"JOURNAL_HMAC_SECRET must be explicitly configured in {env} environment."
                )
            validate_cryptographic_secret_strength(secret_val, env)
        elif env in ("development", "test"):
            if not secret_val:
                object.__setattr__(
                    self,
                    "JOURNAL_HMAC_SECRET",
                    SecretStr("auren_dev_hmac_secret_32_chars_long_entropy_ok!"),
                )
            elif len(secret_val) < 16:
                raise ValueError("JOURNAL_HMAC_SECRET must be at least 16 characters even in development/test.")
        return self

    def get_journal_hmac_secret(self) -> str:
        """Returns the raw secret string for cryptographic operations. Never expose in logs or APIs."""
        if not self.JOURNAL_HMAC_SECRET:
            raise ValueError("JOURNAL_HMAC_SECRET is not configured.")
        return self.JOURNAL_HMAC_SECRET.get_secret_value()


settings = Settings()


def get_journal_hmac_secret() -> str:
    """Convenience helper returning the configured HMAC secret from central settings."""
    return settings.get_journal_hmac_secret()

