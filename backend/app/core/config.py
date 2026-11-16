"""Application configuration module using Pydantic Settings."""

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
}


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
            if secret_val.lower() in KNOWN_INSECURE_SECRETS:
                raise ValueError(
                    f"JOURNAL_HMAC_SECRET cannot be a known default or insecure test value in {env}."
                )
            if len(secret_val) < 32:
                raise ValueError(
                    f"JOURNAL_HMAC_SECRET must be at least 32 characters (256 bits) in {env}; got {len(secret_val)} characters."
                )
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

