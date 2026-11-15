"""Chat and message persistence repository factory and exports.

Provides repository selection between:
1. SupabasePostgresChatRepository: Cloud Supabase PostgreSQL adapter enforcing RLS.
2. SQLiteChatRepository: Explicitly identified local-development and offline-testing adapter.
"""

import logging
from typing import Optional

from app.core.config import settings
from app.services.chat.base_repository import BaseChatRepository
from app.services.chat.sqlite_repository import SQLiteChatRepository
from app.services.chat.supabase_repository import SupabasePostgresChatRepository

logger = logging.getLogger(__name__)

# Backward-compatibility alias
ChatRepository = SQLiteChatRepository

# Default singleton for local development and unit tests
chat_repository: BaseChatRepository = SQLiteChatRepository()


def get_chat_repository(user_token: Optional[str] = None) -> BaseChatRepository:
    """Resolve and return the appropriate chat repository adapter.

    Selection rules:
    - If CHAT_REPOSITORY_TYPE == "supabase" or (
        settings.CHAT_REPOSITORY_TYPE == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
      ):
        Returns SupabasePostgresChatRepository configured with the user's bearer token
        and public anon key (evaluating PostgreSQL Row Level Security as authenticated user).
    - Otherwise (local development, offline testing, CI):
        Returns the SQLiteChatRepository (explicitly identified local-development option).
    """
    repo_type = (settings.CHAT_REPOSITORY_TYPE or "auto").lower()

    if repo_type == "supabase" or (
        repo_type == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
    ):
        return SupabasePostgresChatRepository(
            supabase_url=settings.SUPABASE_URL,
            supabase_anon_key=settings.SUPABASE_ANON_KEY or "",
            user_token=user_token,
        )

    return chat_repository


__all__ = [
    "BaseChatRepository",
    "SQLiteChatRepository",
    "SupabasePostgresChatRepository",
    "ChatRepository",
    "chat_repository",
    "get_chat_repository",
]
