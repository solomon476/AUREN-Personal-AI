"""Reminder repository factory and dependency resolver."""

import logging
from typing import Optional

from app.core.config import settings
from app.services.reminders.base_repository import BaseReminderRepository
from app.services.reminders.sqlite_repository import SQLiteReminderRepository
from app.services.reminders.supabase_repository import SupabaseReminderRepository

logger = logging.getLogger(__name__)

_sqlite_reminder_singleton = SQLiteReminderRepository()


def get_reminder_repository(user_token: Optional[str] = None) -> BaseReminderRepository:
    """Resolve Reminder repository (Supabase RLS or local SQLite WAL)."""
    repo_type = (settings.CHAT_REPOSITORY_TYPE or "auto").lower()

    if repo_type == "supabase" or (
        repo_type == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
        and len(user_token.split(".")) == 3
    ):
        return SupabaseReminderRepository(
            supabase_url=settings.SUPABASE_URL,
            supabase_anon_key=settings.SUPABASE_ANON_KEY or "",
            user_token=user_token or "",
        )

    return _sqlite_reminder_singleton


def get_sqlite_reminder_repository() -> SQLiteReminderRepository:
    """Expose local SQLite reminder singleton for background scheduler."""
    return _sqlite_reminder_singleton


__all__ = [
    "BaseReminderRepository",
    "SQLiteReminderRepository",
    "SupabaseReminderRepository",
    "get_reminder_repository",
    "get_sqlite_reminder_repository",
]

