"""Factory for Connections Repository resolution."""

import logging
from typing import Optional

from app.core.config import settings
from app.services.connections.base_repository import BaseConnectionRepository
from app.services.connections.sqlite_repository import SQLiteConnectionRepository
from app.services.connections.supabase_repository import SupabaseConnectionRepository

logger = logging.getLogger(__name__)

_sqlite_connection_singleton = SQLiteConnectionRepository()


def get_connection_repository(user_token: Optional[str] = None) -> BaseConnectionRepository:
    """Resolve connection repository based on environment configuration and auth session."""
    repo_type = (settings.CHAT_REPOSITORY_TYPE or "auto").lower()

    if repo_type == "supabase" or (
        repo_type == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
        and len(user_token.split(".")) == 3
    ):
        return SupabaseConnectionRepository(
            supabase_url=settings.SUPABASE_URL,
            supabase_anon_key=settings.SUPABASE_ANON_KEY or "",
            user_token=user_token,
        )

    return _sqlite_connection_singleton


__all__ = [
    "BaseConnectionRepository",
    "SQLiteConnectionRepository",
    "SupabaseConnectionRepository",
    "get_connection_repository",
]
