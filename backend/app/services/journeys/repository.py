"""Factory for Journey Repository resolution."""

import logging
from typing import Optional

from app.core.config import settings
from app.services.journeys.base_repository import BaseJourneyRepository
from app.services.journeys.sqlite_repository import SQLiteJourneyRepository
from app.services.journeys.supabase_repository import SupabaseJourneyRepository

logger = logging.getLogger(__name__)

_sqlite_journey_singleton = SQLiteJourneyRepository()


def get_journey_repository(user_token: Optional[str] = None) -> BaseJourneyRepository:
    """Resolve journey repository based on environment configuration and auth session."""
    repo_type = (settings.CHAT_REPOSITORY_TYPE or "auto").lower()

    if repo_type == "supabase" or (
        repo_type == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
        and len(user_token.split(".")) == 3
    ):
        return SupabaseJourneyRepository(
            supabase_url=settings.SUPABASE_URL,
            supabase_anon_key=settings.SUPABASE_ANON_KEY or "",
            user_token=user_token,
        )

    return _sqlite_journey_singleton


__all__ = [
    "BaseJourneyRepository",
    "SQLiteJourneyRepository",
    "SupabaseJourneyRepository",
    "get_journey_repository",
]
