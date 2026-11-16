"""Application configuration module using Pydantic Settings."""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    JOURNAL_HMAC_SECRET: str = Field(
        default="auren-journal-hmac-test-secret-change-in-prod",
        description="Backend HMAC secret for journal consent verification",
    )


settings = Settings()

