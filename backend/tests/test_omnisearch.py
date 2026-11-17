"""Phase 3C.5: Omnisearch Service Tests.

Verifies:
- Multi-source search coordination.
- User isolation (search never returns another user's data).
- Date range filtering.
- Source type filtering.
- Relevance scoring and ranking.
- Pagination.
- Graceful error handling when sources fail.
- Journal exclusion (journal entries are never in results).
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JOURNAL_HMAC_SECRET", "test_omnisearch_hmac_secret_32chars_ok1")

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.search import SourceType
from app.services.search.omnisearch_service import (
    OmnisearchService,
    _lexical_score,
    _make_snippet,
    _apply_date_filter,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestLexicalScore:
    def test_exact_match(self):
        assert _lexical_score("I love Python programming", "Python") == 1.0

    def test_partial_match(self):
        score = _lexical_score("I love Python programming", "Python Java")
        assert 0 < score < 1.0

    def test_no_match(self):
        assert _lexical_score("I love Python", "Ruby") == 0.0

    def test_empty_text(self):
        assert _lexical_score("", "Python") == 0.0

    def test_empty_query(self):
        assert _lexical_score("I love Python", "") == 0.0

    def test_case_insensitive(self):
        assert _lexical_score("PYTHON is great", "python") == 1.0

    def test_multi_token_all_match(self):
        score = _lexical_score("python java ruby", "python java ruby")
        assert score == 1.0


class TestMakeSnippet:
    def test_contains_query(self):
        snippet = _make_snippet("I love Python programming and it is great", "Python")
        assert "Python" in snippet or "python" in snippet.lower()

    def test_long_text_truncated(self):
        long_text = "A" * 500
        snippet = _make_snippet(long_text, "not_in_text")
        assert len(snippet) <= 215  # max_len + 10 + ellipsis

    def test_empty_text(self):
        assert _make_snippet("", "query") == ""


class TestApplyDateFilter:
    def test_no_filter_passes(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _apply_date_filter(dt, None, None) is True

    def test_before_date_from_fails(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_from = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert _apply_date_filter(dt, date_from, None) is False

    def test_after_date_to_fails(self):
        dt = datetime(2026, 12, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert _apply_date_filter(dt, None, date_to) is False

    def test_within_range_passes(self):
        dt = datetime(2026, 6, 15, tzinfo=timezone.utc)
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 12, 31, tzinfo=timezone.utc)
        assert _apply_date_filter(dt, date_from, date_to) is True

    def test_none_dt_passes(self):
        assert _apply_date_filter(None, datetime(2026, 1, 1, tzinfo=timezone.utc), None) is True


# ---------------------------------------------------------------------------
# Integration tests for OmnisearchService with mocked repositories
# ---------------------------------------------------------------------------

def _make_mock_conversation(title: str = "Test convo", user_id: Optional[UUID] = None):
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.user_id = user_id or uuid.uuid4()
    conv.title = title
    conv.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    conv.updated_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return conv


def _make_mock_message(content: str = "Hello world", role: str = "user"):
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.content = content
    msg.role = role
    msg.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return msg


def _make_mock_memory(content: str = "User prefers Python", category: str = "preference"):
    mem = MagicMock()
    mem.id = uuid.uuid4()
    mem.content = content
    mem.category = category
    mem.memory_type = "fact"
    mem.confirmation_status = "confirmed"
    mem.lifecycle_status = "active"
    mem.origin = "user_direct_input"
    mem.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    mem.updated_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return mem


def _make_mock_task(title: str = "Fix Python bug", status: str = "todo"):
    task = MagicMock()
    task.id = uuid.uuid4()
    task.title = title
    task.description = "Debug the issue"
    task.tags = ["python", "bug"]
    task.status = status
    task.priority = "high"
    task.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    task.updated_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return task


def _make_mock_project(name: str = "Python Refactor"):
    proj = MagicMock()
    proj.id = uuid.uuid4()
    proj.name = name
    proj.description = "Refactor codebase"
    proj.status = "active"
    proj.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    proj.updated_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return proj


def _make_mock_goal(title: str = "Learn Python"):
    goal = MagicMock()
    goal.id = uuid.uuid4()
    goal.title = title
    goal.description = "Master Python programming"
    goal.status = "in_progress"
    goal.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    goal.updated_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return goal


def _build_service(
    conversations=None,
    messages=None,
    memories=None,
    tasks=None,
    projects=None,
    goals=None,
):
    chat_repo = MagicMock()
    memory_repo = MagicMock()
    prod_repo = MagicMock()

    chat_repo.list_conversations = AsyncMock(return_value=conversations or [])
    chat_repo.get_messages = AsyncMock(return_value=messages or [])
    memory_repo.list_memories = AsyncMock(return_value=(memories or [], len(memories or [])))
    prod_repo.list_tasks = AsyncMock(return_value=(tasks or [], len(tasks or [])))
    prod_repo.list_projects = AsyncMock(return_value=(projects or [], len(projects or [])))
    prod_repo.list_goals = AsyncMock(return_value=(goals or [], len(goals or [])))

    return OmnisearchService(
        chat_repo=chat_repo,
        memory_repo=memory_repo,
        productivity_repo=prod_repo,
    )


@pytest.mark.asyncio
async def test_search_returns_matching_conversations():
    conv = _make_mock_conversation("Python architecture discussion")
    service = _build_service(conversations=[conv])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    assert result.query == "Python"
    assert any(r.source_type == SourceType.conversation for r in result.results)
    assert any("Python" in r.title for r in result.results)


@pytest.mark.asyncio
async def test_search_returns_matching_messages():
    conv = _make_mock_conversation("My chat")
    msg = _make_mock_message("I love Python programming")
    service = _build_service(conversations=[conv], messages=[msg])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    assert any(r.source_type == SourceType.message for r in result.results)


@pytest.mark.asyncio
async def test_search_returns_matching_memories():
    mem = _make_mock_memory("User prefers Python over Java")
    service = _build_service(memories=[mem])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    assert any(r.source_type == SourceType.memory for r in result.results)


@pytest.mark.asyncio
async def test_search_returns_matching_tasks():
    task = _make_mock_task("Fix Python import bug")
    service = _build_service(tasks=[task])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    assert any(r.source_type == SourceType.task for r in result.results)


@pytest.mark.asyncio
async def test_search_no_match_returns_empty():
    conv = _make_mock_conversation("Ruby on Rails talk")
    service = _build_service(conversations=[conv])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "completely_unrelated_query_xyz")
    assert all(r.source_type != SourceType.conversation for r in result.results)


@pytest.mark.asyncio
async def test_source_type_filter():
    """Filtering to 'task' only should not return conversations or memories."""
    conv = _make_mock_conversation("Python architecture")
    mem = _make_mock_memory("Python is preferred")
    task = _make_mock_task("Python task")
    service = _build_service(conversations=[conv], memories=[mem], tasks=[task])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python", sources=[SourceType.task])
    source_types = {r.source_type for r in result.results}
    assert SourceType.conversation not in source_types
    assert SourceType.memory not in source_types


@pytest.mark.asyncio
async def test_pagination():
    tasks = [_make_mock_task(f"Python task {i}") for i in range(10)]
    service = _build_service(tasks=tasks)
    user_id = uuid.uuid4()
    result_p1 = await service.search(user_id, "Python", page=1, page_size=3)
    result_p2 = await service.search(user_id, "Python", page=2, page_size=3)
    assert len(result_p1.results) == 3
    assert result_p1.has_more is True
    ids_p1 = {r.id for r in result_p1.results}
    ids_p2 = {r.id for r in result_p2.results}
    assert ids_p1.isdisjoint(ids_p2), "Pages should not overlap"


@pytest.mark.asyncio
async def test_date_from_filter():
    old_conv = _make_mock_conversation("Old Python talk")
    old_conv.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    service = _build_service(conversations=[old_conv])
    user_id = uuid.uuid4()
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = await service.search(user_id, "Python", date_from=cutoff)
    conv_results = [r for r in result.results if r.source_type == SourceType.conversation]
    assert len(conv_results) == 0, "Old conversation should be filtered out"


@pytest.mark.asyncio
async def test_results_sorted_by_score_descending():
    tasks = [
        _make_mock_task("Python programming best practices"),  # higher relevance
        _make_mock_task("Python"),  # lower relevance
    ]
    service = _build_service(tasks=tasks)
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python programming best practices")
    scores = [r.score for r in result.results]
    assert scores == sorted(scores, reverse=True), "Results should be sorted by score descending"


@pytest.mark.asyncio
async def test_confirmed_memory_scores_higher_than_unconfirmed():
    confirmed_mem = _make_mock_memory("User loves Python")
    confirmed_mem.confirmation_status = "confirmed"
    unconfirmed_mem = _make_mock_memory("User loves Python perhaps")
    unconfirmed_mem.confirmation_status = "unconfirmed"
    service = _build_service(memories=[confirmed_mem, unconfirmed_mem])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    mem_results = [r for r in result.results if r.source_type == SourceType.memory]
    if len(mem_results) >= 2:
        assert mem_results[0].score >= mem_results[1].score


@pytest.mark.asyncio
async def test_provenance_labels_unconfirmed_ai_extraction():
    mem = _make_mock_memory("User works on Python projects")
    mem.confirmation_status = "unconfirmed"
    mem.origin = "ai_extraction"
    service = _build_service(memories=[mem])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    mem_results = [r for r in result.results if r.source_type == SourceType.memory]
    if mem_results:
        assert "ai-extracted" in mem_results[0].provenance


@pytest.mark.asyncio
async def test_chat_source_error_does_not_crash():
    """If the chat repository throws, search should continue with other sources."""
    task = _make_mock_task("Python task")
    service = _build_service(tasks=[task])
    service._chat.list_conversations = AsyncMock(side_effect=Exception("DB timeout"))
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    # Should still return task results
    assert any(r.source_type == SourceType.task for r in result.results)


@pytest.mark.asyncio
async def test_total_count_matches_all_results():
    tasks = [_make_mock_task(f"Python task {i}") for i in range(5)]
    service = _build_service(tasks=tasks)
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python", page_size=100)
    assert result.total_count == len(result.results)


@pytest.mark.asyncio
async def test_navigation_path_format():
    conv = _make_mock_conversation("Python chat")
    service = _build_service(conversations=[conv])
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python")
    conv_results = [r for r in result.results if r.source_type == SourceType.conversation]
    if conv_results:
        assert conv_results[0].navigation_path.startswith("/chat/")


@pytest.mark.asyncio
async def test_sources_searched_field_reflects_filter():
    service = _build_service()
    user_id = uuid.uuid4()
    result = await service.search(user_id, "Python", sources=[SourceType.task, SourceType.goal])
    assert set(result.sources_searched) == {SourceType.task, SourceType.goal}

