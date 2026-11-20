"""Profile and User Data Management Service."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.models.user import (
    AuthenticatedUser,
    UserDataExportResponse,
    UserProfileResponse,
    UserProfileUpdate,
)

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PROFILES_DB_PATH = DB_DIR / "auren_profiles.db"


class ProfileService:
    """Manages user profile, preferences, and GDPR data export."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or PROFILES_DB_PATH
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path), timeout=20.0) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id TEXT PRIMARY KEY,
                    email TEXT,
                    full_name TEXT,
                    avatar_url TEXT,
                    preferences TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
            """)
            conn.commit()

    async def get_profile(self, user: AuthenticatedUser) -> UserProfileResponse:
        """Fetch user profile and preferences from Supabase PostgREST or local SQLite."""
        # 1. Try Supabase PostgREST if configured and token is present
        if settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY and user.token:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                        params={"id": f"eq.{user.id}", "select": "*"},
                        headers={
                            "apikey": settings.SUPABASE_ANON_KEY,
                            "Authorization": f"Bearer {user.token}",
                            "Accept": "application/json",
                        },
                    )
                    if resp.status_code == 200:
                        records = resp.json()
                        if records:
                            rec = records[0]
                            return UserProfileResponse(
                                id=user.id,
                                email=user.email or rec.get("email"),
                                role=user.role,
                                full_name=rec.get("full_name") or user.user_metadata.get("full_name"),
                                avatar_url=rec.get("avatar_url") or user.user_metadata.get("avatar_url"),
                                preferences=rec.get("preferences") or {},
                                app_metadata=user.app_metadata,
                                user_metadata=user.user_metadata,
                            )
            except Exception as e:
                logger.warning("Supabase profile fetch error (falling back to SQLite): %s", e)

        # 2. SQLite local lookup
        def _get_sqlite() -> UserProfileResponse:
            with sqlite3.connect(str(self.db_path), timeout=20.0) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM user_profiles WHERE id = ?", (str(user.id),)).fetchone()
                if row:
                    try:
                        prefs = json.loads(row["preferences"])
                    except Exception:
                        prefs = {}
                    return UserProfileResponse(
                        id=user.id,
                        email=user.email or row["email"],
                        role=user.role,
                        full_name=row["full_name"],
                        avatar_url=row["avatar_url"],
                        preferences=prefs,
                        app_metadata=user.app_metadata,
                        user_metadata=user.user_metadata,
                    )
            # Default from user token metadata
            full_name = user.user_metadata.get("full_name") or user.user_metadata.get("name")
            avatar_url = user.user_metadata.get("avatar_url") or user.user_metadata.get("picture")
            prefs = user.user_metadata.get("preferences") or {}
            return UserProfileResponse(
                id=user.id,
                email=user.email,
                role=user.role,
                full_name=full_name,
                avatar_url=avatar_url,
                preferences=prefs,
                app_metadata=user.app_metadata,
                user_metadata=user.user_metadata,
            )

        return await asyncio.to_thread(_get_sqlite)

    async def update_profile(
        self,
        user: AuthenticatedUser,
        update: UserProfileUpdate,
    ) -> UserProfileResponse:
        """Update user profile and preferences in Supabase or SQLite."""
        current_profile = await self.get_profile(user)

        new_full_name = update.full_name if update.full_name is not None else current_profile.full_name
        new_avatar_url = update.avatar_url if update.avatar_url is not None else current_profile.avatar_url
        new_prefs = dict(current_profile.preferences)
        if update.preferences is not None:
            new_prefs.update(update.preferences)

        now_iso = datetime.now(timezone.utc).isoformat()

        # Update Supabase if configured
        if settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY and user.token:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.patch(
                        f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
                        params={"id": f"eq.{user.id}"},
                        json={
                            "full_name": new_full_name,
                            "avatar_url": new_avatar_url,
                            "preferences": new_prefs,
                            "updated_at": now_iso,
                        },
                        headers={
                            "apikey": settings.SUPABASE_ANON_KEY,
                            "Authorization": f"Bearer {user.token}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal",
                        },
                    )
            except Exception as e:
                logger.warning("Supabase profile update warning: %s", e)

        # Update SQLite
        def _save_sqlite() -> None:
            with sqlite3.connect(str(self.db_path), timeout=20.0) as conn:
                conn.execute(
                    """
                    INSERT INTO user_profiles (id, email, full_name, avatar_url, preferences, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        full_name = excluded.full_name,
                        avatar_url = excluded.avatar_url,
                        preferences = excluded.preferences,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(user.id),
                        user.email or "",
                        new_full_name,
                        new_avatar_url,
                        json.dumps(new_prefs),
                        now_iso,
                    ),
                )
                conn.commit()

        await asyncio.to_thread(_save_sqlite)

        return UserProfileResponse(
            id=user.id,
            email=user.email,
            role=user.role,
            full_name=new_full_name,
            avatar_url=new_avatar_url,
            preferences=new_prefs,
            app_metadata=user.app_metadata,
            user_metadata=user.user_metadata,
        )

    async def export_data(self, user: AuthenticatedUser) -> UserDataExportResponse:
        """Export all user data across Productivity, Memories, Journal, and Profile."""
        profile = await self.get_profile(user)

        # Lazy load repositories with caller token
        from app.services.productivity.repository import get_productivity_repository
        from app.services.memory.repository import get_memory_repository
        from app.services.journal.repository import get_journal_repository
        from app.services.chat.repository import get_chat_repository

        prod_repo = get_productivity_repository(user_token=user.token)
        mem_repo = get_memory_repository(user_token=user.token)
        journal_repo = get_journal_repository(user_token=user.token)
        chat_repo = get_chat_repository(user_token=user.token)

        tasks, _ = await prod_repo.list_tasks(user_id=user.id, page=1, page_size=1000)
        projects, _ = await prod_repo.list_projects(user_id=user.id, page=1, page_size=1000)
        goals, _ = await prod_repo.list_goals(user_id=user.id, page=1, page_size=1000)
        memories, _ = await mem_repo.list_memories(user_id=user.id, page=1, page_size=1000)
        journal_entries, _ = await journal_repo.list_entries(user_id=user.id, page=1, page_size=1000)

        conversations_list = []
        try:
            convs = await chat_repo.list_conversations(user_id=user.id, limit=500)
            for c in convs:
                msgs = await chat_repo.get_messages(user_id=user.id, conversation_id=c.id, limit=1000)
                c_dict = c.model_dump(mode="json")
                c_dict["messages"] = [m.model_dump(mode="json") for m in msgs]
                conversations_list.append(c_dict)
        except Exception as e:
            logger.warning("Conversations export warning: %s", e)

        return UserDataExportResponse(
            user_id=user.id,
            email=user.email,
            exported_at=datetime.now(timezone.utc),
            preferences=profile.preferences,
            tasks=[t.model_dump(mode="json") for t in tasks],
            projects=[p.model_dump(mode="json") for p in projects],
            goals=[g.model_dump(mode="json") for g in goals],
            memories=[m.model_dump(mode="json") for m in memories],
            journal_entries=[j.model_dump(mode="json") for j in journal_entries],
            conversations=conversations_list,
        )


profile_service = ProfileService()
