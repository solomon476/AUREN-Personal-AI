"""Memory persistence repository factory and exports.

Provides repository selection between:
1. SupabaseMemoryRepository: Cloud Supabase PostgreSQL adapter enforcing RLS.
2. SQLiteMemoryRepository: Local-development and offline-testing adapter.
"""

import logging
from typing import Optional

from app.core.config import settings
from app.services.memory.base_repository import BaseMemoryRepository
from app.services.memory.sqlite_repository import SQLiteMemoryRepository
from app.services.memory.supabase_repository import SupabaseMemoryRepository

logger = logging.getLogger(__name__)

# Backward-compatibility alias
MemoryRepository = SQLiteMemoryRepository

# Default singleton for local development and unit tests
memory_repository: BaseMemoryRepository = SQLiteMemoryRepository()


def get_memory_repository(user_token: Optional[str] = None) -> BaseMemoryRepository:
    """Resolve and return the appropriate memory repository adapter.

    Selection rules:
    - If CHAT_REPOSITORY_TYPE == "supabase" or (
        settings.CHAT_REPOSITORY_TYPE == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
      ):
        Returns SupabaseMemoryRepository configured with the user's bearer token
        and public anon key (evaluating PostgreSQL Row Level Security as authenticated user).
    - Otherwise (local development, offline testing, CI):
        Returns the SQLiteMemoryRepository (disk-backed local development option).
    """
    repo_type = (settings.CHAT_REPOSITORY_TYPE or "auto").lower()

    if repo_type == "supabase" or (
        repo_type == "auto"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
        and user_token
    ):
        return SupabaseMemoryRepository(
            supabase_url=settings.SUPABASE_URL,
            supabase_anon_key=settings.SUPABASE_ANON_KEY or "",
            user_token=user_token,
        )

    return memory_repository


__all__ = [
    "BaseMemoryRepository",
    "SQLiteMemoryRepository",
    "SupabaseMemoryRepository",
    "MemoryRepository",
    "memory_repository",
    "get_memory_repository",
]

