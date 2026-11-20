"""Journal repository factory and provider."""

import logging
from typing import Optional

from app.core.config import settings
from app.services.journal.base_repository import BaseJournalRepository
from app.services.journal.sqlite_repository import SQLiteJournalRepository
from app.services.journal.supabase_repository import SupabaseJournalRepository

logger = logging.getLogger(__name__)

_sqlite_singleton = SQLiteJournalRepository()


def get_journal_repository(user_token: Optional[str] = None) -> BaseJournalRepository:
    """Resolve the appropriate repository based on environment configuration and auth session."""
    repo_type = (settings.CHAT_REPOSITORY_TYPE or "auto").lower()

    if repo_type == "supabase" or (
        repo_type == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
    ):
        return SupabaseJournalRepository(
            supabase_url=settings.SUPABASE_URL,
            supabase_anon_key=settings.SUPABASE_ANON_KEY or "",
            user_token=user_token,
        )

    return _sqlite_singleton


__all__ = [
    "BaseJournalRepository",
    "SQLiteJournalRepository",
    "SupabaseJournalRepository",
    "get_journal_repository",
]
