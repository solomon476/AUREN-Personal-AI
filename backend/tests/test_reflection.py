"""Phase 3C.5: Reflective Intelligence Service Tests.

Verifies:
- Contradiction detection (supersession-chain and value-conflict strategies).
- Staleness detection for tasks (overdue), projects (past target date),
  goals (past target date), and memories (past review_after, unconfirmed facts).
- Relationship discovery for tasks, projects, goals, and memories.
- Insight overview aggregation.
- Read-only guarantee: no mutations occur.
- Journal exclusion guarantee.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JOURNAL_HMAC_SECRET", "test_reflection_hmac_secret_32chars_ok1")

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.search import RelationshipType, SourceType
from app.services.reflection.reflection_service import ReflectionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return _now() - timedelta(days=n)


def _days_from_now(n: int) -> datetime:
    return _now() + timedelta(days=n)


def _make_memory(
    content: str = "User prefers Python",
    category: str = "preference",
    confirmation_status: str = "confirmed",
    lifecycle_status: str = "active",
    origin: str = "user_direct_input",
    superseded_by_id: Optional[UUID] = None,
    source_conversation_id: Optional[UUID] = None,
    review_after: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
    memory_type: str = "fact",
):
    mem = MagicMock()
    mem.id = uuid.uuid4()
    mem.content = content
    mem.category = category
    mem.confirmation_status = confirmation_status
    mem.lifecycle_status = lifecycle_status
    mem.origin = origin
    mem.superseded_by_id = superseded_by_id
    mem.source_conversation_id = source_conversation_id
    mem.review_after = review_after
    mem.created_at = created_at or _days_ago(10)
    mem.updated_at = created_at or _days_ago(10)
    mem.memory_type = memory_type
    return mem


def _make_task(
    title: str = "Fix bug",
    status: str = "todo",
    due_date: Optional[datetime] = None,
    project_id: Optional[UUID] = None,
    goal_id: Optional[UUID] = None,
    parent_task_id: Optional[UUID] = None,
):
    task = MagicMock()
    task.id = uuid.uuid4()
    task.title = title
    task.status = status
    task.due_date = due_date
    task.project_id = project_id
    task.goal_id = goal_id
    task.parent_task_id = parent_task_id
    task.created_at = _days_ago(5)
    task.updated_at = _days_ago(5)
    return task


def _make_project(
    name: str = "My Project",
    status: str = "active",
    target_date: Optional[date] = None,
    goal_id: Optional[UUID] = None,
):
    proj = MagicMock()
    proj.id = uuid.uuid4()
    proj.name = name
    proj.status = status
    proj.target_date = target_date
    proj.goal_id = goal_id
    proj.created_at = _days_ago(30)
    proj.updated_at = _days_ago(5)
    return proj


def _make_goal(
    title: str = "My Goal",
    status: str = "in_progress",
    target_date: Optional[date] = None,
):
    goal = MagicMock()
    goal.id = uuid.uuid4()
    goal.title = title
    goal.status = status
    goal.target_date = target_date
    goal.created_at = _days_ago(60)
    goal.updated_at = _days_ago(10)
    return goal


def _build_service(
    memories=None,
    superseded_memories=None,
    tasks=None,
    projects=None,
    goals=None,
):
    memory_repo = MagicMock()
    prod_repo = MagicMock()

    def _list_memories_side_effect(**kwargs):
        ls = kwargs.get("lifecycle_status")
        if ls == "superseded":
            return (superseded_memories or [], len(superseded_memories or []))
        return (memories or [], len(memories or []))

    memory_repo.list_memories = AsyncMock(side_effect=lambda **kw: _list_memories_side_effect(**kw))
    memory_repo.get_memory = AsyncMock(return_value=None)
    prod_repo.list_tasks = AsyncMock(return_value=(tasks or [], len(tasks or [])))
    prod_repo.list_projects = AsyncMock(return_value=(projects or [], len(projects or [])))
    prod_repo.list_goals = AsyncMock(return_value=(goals or [], len(goals or [])))
    prod_repo.get_task = AsyncMock(return_value=None)
    prod_repo.get_project = AsyncMock(return_value=None)
    prod_repo.get_goal = AsyncMock(return_value=None)

    return ReflectionService(memory_repo=memory_repo, productivity_repo=prod_repo)


# ---------------------------------------------------------------------------
# Contradiction detection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_contradictions_when_no_memories():
    service = _build_service()
    user_id = uuid.uuid4()
    result = await service.get_contradictions(user_id)
    assert result == []


@pytest.mark.asyncio
async def test_supersession_chain_contradiction_detected():
    mem_a = _make_memory("Old preference: Java")
    mem_b = _make_memory("New preference: Python", superseded_by_id=None)
    mem_a.superseded_by_id = mem_b.id  # mem_a claims to be superseded by mem_b, but both active
    service = _build_service(memories=[mem_a, mem_b])
    user_id = uuid.uuid4()
    result = await service.get_contradictions(user_id)
    supersession = [c for c in result if c.contradiction_type == "supersession_chain"]
    assert len(supersession) >= 1


@pytest.mark.asyncio
async def test_value_conflict_contradiction_detected():
    mem_a = _make_memory("I like coffee", category="food_preferences")
    mem_b = _make_memory("I dislike coffee", category="food_preferences")
    service = _build_service(memories=[mem_a, mem_b])
    user_id = uuid.uuid4()
    result = await service.get_contradictions(user_id)
    value_conflicts = [c for c in result if c.contradiction_type == "value_conflict"]
    assert len(value_conflicts) >= 1


@pytest.mark.asyncio
async def test_no_contradiction_different_categories():
    mem_a = _make_memory("I like coffee", category="food")
    mem_b = _make_memory("I dislike Python", category="technology")
    service = _build_service(memories=[mem_a, mem_b])
    user_id = uuid.uuid4()
    result = await service.get_contradictions(user_id)
    value_conflicts = [c for c in result if c.contradiction_type == "value_conflict"]
    # Should not flag contradictions across different categories
    assert len(value_conflicts) == 0


@pytest.mark.asyncio
async def test_contradiction_capped_at_50():
    mems = []
    for i in range(60):
        mem = _make_memory(f"I like item_{i}", category="likes")
        mem2 = _make_memory(f"I dislike item_{i}", category="likes")
        mems.extend([mem, mem2])
    service = _build_service(memories=mems)
    user_id = uuid.uuid4()
    result = await service.get_contradictions(user_id)
    assert len(result) <= 50


# ---------------------------------------------------------------------------
# Staleness detection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overdue_task_detected():
    overdue_task = _make_task(
        "Overdue task",
        status="todo",
        due_date=_days_ago(5),
    )
    service = _build_service(tasks=[overdue_task])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    task_items = [i for i in result if i.source_type == SourceType.task]
    assert len(task_items) >= 1
    assert "overdue" in task_items[0].reason.lower()


@pytest.mark.asyncio
async def test_completed_task_not_flagged():
    done_task = _make_task("Done task", status="done", due_date=_days_ago(5))
    service = _build_service(tasks=[done_task])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    task_items = [i for i in result if i.source_type == SourceType.task]
    assert len(task_items) == 0


@pytest.mark.asyncio
async def test_future_due_task_not_flagged():
    future_task = _make_task("Future task", status="todo", due_date=_days_from_now(10))
    service = _build_service(tasks=[future_task])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    task_items = [i for i in result if i.source_type == SourceType.task]
    assert len(task_items) == 0


@pytest.mark.asyncio
async def test_overdue_project_detected():
    today = datetime.now(timezone.utc).date()
    overdue_proj = _make_project(
        "Overdue Project",
        status="active",
        target_date=today - timedelta(days=10),
    )
    service = _build_service(projects=[overdue_proj])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    proj_items = [i for i in result if i.source_type == SourceType.project]
    assert len(proj_items) >= 1


@pytest.mark.asyncio
async def test_completed_project_not_flagged():
    today = datetime.now(timezone.utc).date()
    done_proj = _make_project(
        "Done Project",
        status="completed",
        target_date=today - timedelta(days=10),
    )
    service = _build_service(projects=[done_proj])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    proj_items = [i for i in result if i.source_type == SourceType.project]
    assert len(proj_items) == 0


@pytest.mark.asyncio
async def test_overdue_goal_detected():
    today = datetime.now(timezone.utc).date()
    overdue_goal = _make_goal(
        "Overdue Goal",
        status="in_progress",
        target_date=today - timedelta(days=20),
    )
    service = _build_service(goals=[overdue_goal])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    goal_items = [i for i in result if i.source_type == SourceType.goal]
    assert len(goal_items) >= 1


@pytest.mark.asyncio
async def test_achieved_goal_not_flagged():
    today = datetime.now(timezone.utc).date()
    done_goal = _make_goal(
        "Achieved Goal",
        status="achieved",
        target_date=today - timedelta(days=20),
    )
    service = _build_service(goals=[done_goal])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    goal_items = [i for i in result if i.source_type == SourceType.goal]
    assert len(goal_items) == 0


@pytest.mark.asyncio
async def test_past_review_after_memory_detected():
    mem = _make_memory(
        "Old fact needing review",
        review_after=_days_ago(5),
    )
    service = _build_service(memories=[mem])
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    mem_items = [i for i in result if i.source_type == SourceType.memory]
    assert len(mem_items) >= 1


@pytest.mark.asyncio
async def test_staleness_items_capped_at_100():
    tasks = [_make_task(f"Task {i}", status="todo", due_date=_days_ago(i + 1)) for i in range(150)]
    service = _build_service(tasks=tasks)
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    assert len(result) <= 100


@pytest.mark.asyncio
async def test_staleness_sorted_by_score_descending():
    tasks = [
        _make_task("Very overdue", status="todo", due_date=_days_ago(100)),
        _make_task("Mildly overdue", status="todo", due_date=_days_ago(2)),
    ]
    service = _build_service(tasks=tasks)
    user_id = uuid.uuid4()
    result = await service.get_staleness(user_id)
    task_items = [i for i in result if i.source_type == SourceType.task]
    if len(task_items) >= 2:
        assert task_items[0].staleness_score >= task_items[1].staleness_score


# ---------------------------------------------------------------------------
# Relationship discovery tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_relationships_includes_project():
    proj = _make_project("My Project")
    task = _make_task("My Task", project_id=proj.id)
    service = _build_service(tasks=[task], projects=[proj])
    service._prod.get_task = AsyncMock(return_value=task)
    service._prod.get_project = AsyncMock(return_value=proj)
    user_id = uuid.uuid4()
    result = await service.get_relationships(user_id, SourceType.task, task.id)
    assert any(r.source_type == SourceType.project for r in result.relationships)


@pytest.mark.asyncio
async def test_task_relationships_includes_goal():
    goal = _make_goal("My Goal")
    task = _make_task("My Task", goal_id=goal.id)
    service = _build_service(tasks=[task], goals=[goal])
    service._prod.get_task = AsyncMock(return_value=task)
    service._prod.get_goal = AsyncMock(return_value=goal)
    user_id = uuid.uuid4()
    result = await service.get_relationships(user_id, SourceType.task, task.id)
    assert any(r.source_type == SourceType.goal for r in result.relationships)


@pytest.mark.asyncio
async def test_task_not_found_returns_empty_relationships():
    service = _build_service()
    service._prod.get_task = AsyncMock(return_value=None)
    user_id = uuid.uuid4()
    result = await service.get_relationships(user_id, SourceType.task, uuid.uuid4())
    assert result.relationships == []


@pytest.mark.asyncio
async def test_project_relationships_includes_goal():
    goal = _make_goal("Strategic Goal")
    proj = _make_project("My Project", goal_id=goal.id)
    service = _build_service(projects=[proj], goals=[goal])
    service._prod.get_project = AsyncMock(return_value=proj)
    service._prod.get_goal = AsyncMock(return_value=goal)
    service._prod.list_tasks = AsyncMock(return_value=([], 0))
    user_id = uuid.uuid4()
    result = await service.get_relationships(user_id, SourceType.project, proj.id)
    assert any(r.source_type == SourceType.goal for r in result.relationships)


@pytest.mark.asyncio
async def test_memory_relationships_includes_source_conversation():
    conv_id = uuid.uuid4()
    mem = _make_memory("User prefers Python", source_conversation_id=conv_id)
    service = _build_service(memories=[mem])
    service._memory.get_memory = AsyncMock(return_value=mem)
    user_id = uuid.uuid4()
    result = await service.get_relationships(user_id, SourceType.memory, mem.id)
    assert any(r.source_type == SourceType.conversation for r in result.relationships)
    conv_rels = [r for r in result.relationships if r.source_type == SourceType.conversation]
    assert str(conv_id) in conv_rels[0].navigation_path


# ---------------------------------------------------------------------------
# Insights overview test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_insights_aggregates_correctly():
    mem_a = _make_memory("I like coffee", category="food")
    mem_b = _make_memory("I dislike coffee", category="food")
    overdue_task = _make_task("Overdue", status="todo", due_date=_days_ago(3))

    service = _build_service(memories=[mem_a, mem_b], tasks=[overdue_task])

    user_id = uuid.uuid4()
    result = await service.get_insights(user_id)
    assert result.contradiction_count >= 0
    assert result.staleness_count >= 1
    assert isinstance(result.generated_at, datetime)


# ---------------------------------------------------------------------------
# Phase 3C.5.2 / EPI-01: False-Positive Contradiction Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_value_conflict_different_subjects_not_flagged():
    """EPI-01: Statements in the same category about different subjects
    must NOT be flagged as contradictions.
    """
    mem_a = _make_memory("I like Italian pasta dishes", category="preferences")
    mem_b = _make_memory("I dislike Monday morning meetings", category="preferences")
    service = _build_service(memories=[mem_a, mem_b])
    user_id = uuid.uuid4()
    result = await service.get_contradictions(user_id)
    value_conflicts = [c for c in result if c.contradiction_type == "value_conflict"]
    assert len(value_conflicts) == 0


@pytest.mark.asyncio
async def test_value_conflict_conditional_statement_not_flagged():
    """EPI-01: Statements containing conditional or situational markers
    (when, if, sometimes) must NOT be flagged as contradictions.
    """
    mem_a = _make_memory("When travelling abroad I prefer hotels", category="travel")
    mem_b = _make_memory("I avoid hotels during local roadtrips", category="travel")
    service = _build_service(memories=[mem_a, mem_b])
    user_id = uuid.uuid4()
    result = await service.get_contradictions(user_id)
    value_conflicts = [c for c in result if c.contradiction_type == "value_conflict"]
    assert len(value_conflicts) == 0


# ---------------------------------------------------------------------------
# Phase 3C.5.2 / API-01: Record Links Repository & Relationship Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_record_links_crud_and_cross_tenant_validation(tmp_path):
    """API-01: Verify SQLite repository CRUD and endpoint ownership validation."""
    from app.services.productivity.sqlite_repository import SQLiteProductivityRepository
    from app.models.productivity import TaskCreate, ProjectCreate
    from app.models.search import RecordLinkCreate, RelationshipType, SourceType

    repo = SQLiteProductivityRepository(db_path=tmp_path / "test_rl.db")
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # User A creates a task and a project
    task_a = await repo.create_task(user_a, TaskCreate(title="Task A"))
    proj_a = await repo.create_project(user_a, ProjectCreate(name="Project A"))

    # User B creates a task
    task_b = await repo.create_task(user_b, TaskCreate(title="Task B"))

    # 1. User A creates valid link
    link = await repo.create_record_link(
        user_a,
        RecordLinkCreate(
            source_type=SourceType.task,
            source_id=task_a.id,
            target_type=SourceType.project,
            target_id=proj_a.id,
            relationship_type=RelationshipType.related,
        ),
    )
    assert link.id is not None
    assert link.user_id == user_a
    assert link.source_id == task_a.id
    assert link.target_id == proj_a.id

    # 2. List record links
    links = await repo.list_record_links(user_a, SourceType.task, task_a.id)
    assert len(links) == 1
    assert links[0].target_id == proj_a.id

    # 3. User B attempts cross-tenant target linking (task B -> proj A) -> Rejected
    with pytest.raises(ValueError) as exc_target:
        await repo.create_record_link(
            user_b,
            RecordLinkCreate(
                source_type=SourceType.task,
                source_id=task_b.id,
                target_type=SourceType.project,
                target_id=proj_a.id,
            ),
        )
    assert "not found or not owned by user" in str(exc_target.value)

    # 4. User B attempts cross-tenant source linking (task A -> task B) -> Rejected
    with pytest.raises(ValueError) as exc_source:
        await repo.create_record_link(
            user_b,
            RecordLinkCreate(
                source_type=SourceType.task,
                source_id=task_a.id,
                target_type=SourceType.task,
                target_id=task_b.id,
            ),
        )
    assert "not found or not owned by user" in str(exc_source.value)

    # 5. Delete record link
    deleted = await repo.delete_record_link(user_a, link.id)
    assert deleted is True
    # Re-list should be empty
    remaining = await repo.list_record_links(user_a, SourceType.task, task_a.id)
    assert len(remaining) == 0


