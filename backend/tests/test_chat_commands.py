"""Tests for unified ChatCommandExecutor and SSE `app_action` orchestration across all AUREN domains."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from unittest.mock import MagicMock
import uuid

from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.security import get_current_user
from app.main import app
from app.models.user import AuthenticatedUser
from app.services.chat.chat_service import chat_service
from app.services.chat.command_executor import ChatCommandExecutor
from app.services.chat.sqlite_repository import SQLiteChatRepository
from app.services.connections.sqlite_repository import SQLiteConnectionRepository
from app.services.journal.sqlite_repository import SQLiteJournalRepository
from app.services.journeys.sqlite_repository import SQLiteJourneyRepository
from app.services.llm.base import BaseLLMProvider, ChatMessage
from app.services.memory.sqlite_repository import SQLiteMemoryRepository
from app.services.productivity.sqlite_repository import SQLiteProductivityRepository
from app.services.profile_service import ProfileService
from app.services.reminders.sqlite_repository import SQLiteReminderRepository


TEST_USER = AuthenticatedUser(
    id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    email="commander@auren.ai",
    role="authenticated",
    token=None,
)


def _init_repos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", None)
    monkeypatch.setattr(settings, "CHAT_REPOSITORY_TYPE", "sqlite")
    db_file = tmp_path / "cmd_test.db"
    prod_repo = SQLiteProductivityRepository(db_path=db_file)
    rem_repo = SQLiteReminderRepository(db_path=db_file)
    mem_repo = SQLiteMemoryRepository(db_path=db_file)
    journal_repo = SQLiteJournalRepository(db_path=db_file)
    conn_repo = SQLiteConnectionRepository(db_path=db_file)
    journey_repo = SQLiteJourneyRepository(db_path=db_file)
    chat_repo = SQLiteChatRepository(db_path=db_file)
    prof_svc = ProfileService(db_path=db_file)

    return {
        "db_file": db_file,
        "prod": prod_repo,
        "rem": rem_repo,
        "mem": mem_repo,
        "journal": journal_repo,
        "conn": conn_repo,
        "journey": journey_repo,
        "chat": chat_repo,
        "prof": prof_svc,
    }


@pytest.mark.asyncio
async def test_command_executor_full_app_control_and_safety_guards(tmp_path, monkeypatch):
    repos = _init_repos(tmp_path, monkeypatch)
    prof_svc = repos["prof"]
    monkeypatch.setattr("app.services.productivity.task_reminder_sync.get_reminder_repository", lambda user_token=None: repos["rem"])
    monkeypatch.setattr("app.services.productivity.task_reminder_sync.profile_service", prof_svc)

    executor = ChatCommandExecutor(
        user=TEST_USER,
        default_timezone="Africa/Nairobi",
        prod_repo=repos["prod"],
        rem_repo=repos["rem"],
        mem_repo=repos["mem"],
        journal_repo=repos["journal"],
        conn_repo=repos["conn"],
        journey_repo=repos["journey"],
        profile_svc=prof_svc,
    )

    due_tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
    due_next_week = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0).isoformat()

    markdown = f"""
Here is everything updated for you:
```auren-action
[
  {{"type": "create_goal", "title": "Launch Personal Command Center", "target_date": "2026-12-31"}},
  {{"type": "create_project", "name": "Q4 Execution", "goal_title": "Launch Personal Command Center"}},
  {{"type": "create_task", "title": "Submit Weekly Audit", "priority": "high", "due_date": "{due_tomorrow}", "project_name": "Q4 Execution", "reminder_mode": "before_due", "reminder_offset_minutes": 30}},
  {{"type": "update_task", "target_title": "Submit Weekly Audit", "due_date": "{due_next_week}", "new_title": "Submit Monthly Audit"}},
  {{"type": "create_journal", "title": "Evening Wins", "content": "Shipped full chat control safely.", "mood": "focused", "tags": ["wins"]}},
  {{"type": "create_memory", "content": "User prefers high-contrast obsidian mode at night", "memory_type": "preference", "category": "personal", "importance": 4}},
  {{"type": "create_connection_invite", "display_name": "Dr. Wanjiku"}},
  {{"type": "create_journey", "title": "Site Inspection", "assignment_site": "Westlands Hub", "assignment_purpose": "Fiber check"}},
  {{"type": "update_settings", "theme": "dark", "quiet_hours_enabled": true, "quiet_hours_start": "22:00", "quiet_hours_end": "06:30", "hide_sensitive_lockscreen": false, "evil_key": "ignored"}},
  {{"type": "navigate", "path": "/tasks"}},
  {{"type": "delete_task", "title": "Submit Monthly Audit"}}
]
```
"""

    batch = await executor.execute_blocks_from_text(markdown)

    assert len(batch.failures) == 0
    assert {"goals", "projects", "tasks", "journal", "memories", "connections", "journeys", "settings", "navigation"}.issubset(batch.domains)
    assert batch.navigate_to == "/tasks"
    assert batch.updated_preferences is not None
    assert batch.updated_preferences.get("theme") == "dark"
    assert "evil_key" not in batch.updated_preferences

    # Task created, updated/renamed, and auto-linked reminder rescheduled cleanly
    tasks, t_total = await repos["prod"].list_tasks(user_id=TEST_USER.id)
    assert t_total == 1
    assert tasks[0].title == "Submit Monthly Audit"

    rems, r_total = await repos["rem"].list_reminders(user_id=TEST_USER.id)
    assert r_total == 1
    assert rems[0].task_id == tasks[0].id

    # Destructive delete was NOT silently executed (marked requires_confirmation for UI 1-tap Confirm button)
    del_res = [r for r in batch.results if r.action_type == "delete_task"][0]
    assert del_res.status == "requires_confirmation"

    # Journal, Memory, Connection Invite, Journey, & Profile Settings all persisted cleanly
    journals, j_total = await repos["journal"].list_entries(user_id=TEST_USER.id)
    assert j_total == 1
    assert journals[0].is_private is True

    memories, m_total = await repos["mem"].list_memories(user_id=TEST_USER.id)
    assert m_total == 1
    assert "obsidian" in memories[0].content.lower()

    conns = await repos["conn"].list_connections(user_id=TEST_USER.id)
    assert len(conns) == 1
    assert conns[0].display_name == "Dr. Wanjiku"

    journeys, jr_total = await repos["journey"].list_journeys(user_id=TEST_USER.id)
    assert jr_total == 1
    assert journeys[0].assignment_site == "Westlands Hub"

    prof = await prof_svc.get_profile(TEST_USER)
    assert prof.preferences["theme"] == "dark"
    assert prof.preferences["quiet_hours_enabled"] is True
    assert "evil_key" not in prof.preferences

    # Memory correction & archive commands succeed
    corr = await executor.execute_action({
        "type": "correct_memory",
        "target_content": "obsidian",
        "new_content": "User prefers executive white during day and dark at night",
    })
    assert corr.status == "executed"


def test_chat_stream_emits_app_action_sse_event_and_persists_executed_metadata(tmp_path, monkeypatch):
    repos = _init_repos(tmp_path, monkeypatch)
    prof_svc = repos["prof"]

    class _CmdLLM(BaseLLMProvider):
        def get_model_id(self) -> str:
            return "mock-cmd-model"

        async def stream_response(self, messages, temperature=0.7, max_tokens=2048):
            yield "Done! I updated your preferences and created your project.\n```auren-action\n"
            yield json.dumps([
                {"type": "create_project", "name": "Personal Command Upgrade"},
                {"type": "update_settings", "reminder_sound": "bell", "hide_sensitive_lockscreen": False},
                {"type": "navigate", "path": "settings"},
            ])
            yield "\n```"

        async def generate_response(self, messages, temperature=0.3, max_tokens=1024):
            return ""

    monkeypatch.setattr("app.services.chat.chat_service.get_llm_provider", lambda *a, **kw: _CmdLLM())
    monkeypatch.setattr("app.services.chat.chat_service.get_chat_repository", lambda user_token=None: repos["chat"])
    monkeypatch.setattr("app.services.chat.command_executor.get_productivity_repository", lambda user_token=None: repos["prod"])
    monkeypatch.setattr("app.services.chat.command_executor.get_reminder_repository", lambda user_token=None: repos["rem"])
    monkeypatch.setattr("app.services.chat.command_executor.profile_service", prof_svc)
    monkeypatch.setattr("app.services.profile_service.profile_service", prof_svc)
    monkeypatch.setattr("app.api.v1.chat.get_chat_repository", lambda user_token=None: repos["chat"])

    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/chat/completions",
            json={"message": "Create project Personal Command Upgrade, set sound bell, and open settings"},
        )
        assert resp.status_code == 200
        assert "event: app_action" in resp.text
        assert "/settings" in resp.text
        assert "Personal Command Upgrade" in resp.text
        assert "event: done" in resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)

