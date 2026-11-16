"""Productivity repository factory and dependency provider."""

import logging
from typing import Optional

from app.core.config import settings
from app.services.productivity.base_repository import BaseProductivityRepository
from app.services.productivity.sqlite_repository import SQLiteProductivityRepository
from app.services.productivity.supabase_repository import SupabaseProductivityRepository

logger = logging.getLogger(__name__)

# Default SQLite singleton for local development, offline mode, and unit tests
_sqlite_singleton = SQLiteProductivityRepository()


def get_productivity_repository(user_token: Optional[str] = None) -> BaseProductivityRepository:
    """Resolve the appropriate repository based on environment configuration and auth session."""
    repo_type = (settings.CHAT_REPOSITORY_TYPE or "auto").lower()

    if repo_type == "supabase" or (
        repo_type == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
    ):
        return SupabaseProductivityRepository(
            supabase_url=settings.SUPABASE_URL,
            supabase_anon_key=settings.SUPABASE_ANON_KEY or "",
            user_token=user_token,
        )

    return _sqlite_singleton


__all__ = [
    "BaseProductivityRepository",
    "SQLiteProductivityRepository",
    "SupabaseProductivityRepository",
    "get_productivity_repository",
]

