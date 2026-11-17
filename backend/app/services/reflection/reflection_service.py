"""Phase 3C.5 Reflective Intelligence Service.

Provides three analytical capabilities:
  1. Contradiction detection — finds memories with potentially conflicting facts.
  2. Staleness detection — flags overdue tasks, expired projects/goals, and
     unreviewed memories that exceed their review_after date.
  3. Relationship discovery — surfaces cross-entity links from structural FK
     relationships and inferred lexical affinity.

Design constraints:
  - READ-ONLY. This service never modifies records.
  - Epistemic honesty: every finding is framed as a suggestion, not a fact.
  - Journal exclusion: journal entries are never examined or returned.
  - Ownership: every query is strictly scoped to user_id.
  - No automatic confirmation, deletion or mutation of any record.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from app.models.search import (
    ContradictionItem,
    RelatedRecord,
    ReflectionInsightsResponse,
    RelationshipsResponse,
    RelationshipType,
    SourceType,
    StalenessItem,
)
from app.services.memory.base_repository import BaseMemoryRepository
from app.services.productivity.base_repository import BaseProductivityRepository

logger = logging.getLogger(__name__)

# Thresholds
_STALENESS_TASK_OVERDUE_DAYS = 1          # due_date passed and task not done
_STALENESS_PROJECT_OVERDUE_DAYS = 0       # target_date passed, still active
_STALENESS_GOAL_OVERDUE_DAYS = 0          # target_date passed, still in_progress
_STALENESS_MEMORY_UNREVIEWED_DAYS = 90    # confirmed/unconfirmed fact not reviewed in 90 days
_CONTRADICTION_MIN_CONFIDENCE = 0.5


class ReflectionService:
    """Read-only analytical reflection over AUREN personal data."""

    def __init__(
        self,
        memory_repo: BaseMemoryRepository,
        productivity_repo: BaseProductivityRepository,
    ) -> None:
        self._memory = memory_repo
        self._prod = productivity_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_insights(self, user_id: UUID) -> ReflectionInsightsResponse:
        """Return a combined overview of contradictions and staleness items."""
        import asyncio
        contradictions, staleness = await asyncio.gather(
            self.get_contradictions(user_id),
            self.get_staleness(user_id),
            return_exceptions=True,
        )
        if isinstance(contradictions, Exception):
            logger.warning("Contradiction detection error: %s", contradictions)
            contradictions = []
        if isinstance(staleness, Exception):
            logger.warning("Staleness detection error: %s", staleness)
            staleness = []

        # Inferred link count — count memories with superseded_by_id set
        try:
            memories, _ = await self._memory.list_memories(
                user_id=user_id,
                lifecycle_status="superseded",
                page=1,
                page_size=200,
            )
            inferred_link_count = len(memories)
        except Exception:
            inferred_link_count = 0

        return ReflectionInsightsResponse(
            contradiction_count=len(contradictions),
            staleness_count=len(staleness),
            inferred_link_count=inferred_link_count,
            contradictions=contradictions,
            staleness_items=staleness,
            generated_at=datetime.now(timezone.utc),
        )

    async def get_contradictions(self, user_id: UUID) -> List[ContradictionItem]:
        """Detect potential contradictions among active and superseded memories."""
        try:
            active_memories, _ = await self._memory.list_memories(
                user_id=user_id,
                lifecycle_status="active",
                page=1,
                page_size=500,
            )
        except Exception as exc:
            logger.warning("Cannot load memories for contradiction check: %s", exc)
            return []

        contradictions: List[ContradictionItem] = []

        # --- Strategy 1: Supersession-chain conflicts ---
        # A memory with superseded_by_id pointing to another should be reflected
        for mem in active_memories:
            if mem.superseded_by_id:
                # Active memory claims superseded_by — this is a chain worth reviewing
                superseded_mem = next(
                    (m for m in active_memories if m.id == mem.superseded_by_id), None
                )
                if superseded_mem:
                    contradictions.append(ContradictionItem(
                        memory_a_id=mem.id,
                        memory_a_content=mem.content,
                        memory_a_status=mem.confirmation_status,
                        memory_b_id=superseded_mem.id,
                        memory_b_content=superseded_mem.content,
                        memory_b_status=superseded_mem.confirmation_status,
                        contradiction_type="supersession_chain",
                        explanation=(
                            "One memory indicates it supersedes another that is still marked active. "
                            "Review whether the earlier record should be archived."
                        ),
                        confidence=0.85,
                        suggested_action="Archive or confirm the older memory record.",
                    ))

        # --- Strategy 2: Same-category value conflicts ---
        # Group memories by category, look for opposing value signals
        by_category: Dict[str, list] = {}
        for mem in active_memories:
            by_category.setdefault(mem.category, []).append(mem)

        _NEGATION_PAIRS = [
            (r"\blike\b", r"\bdislike\b"),
            (r"\bprefer\b", r"\bavoid\b"),
            (r"\byes\b", r"\bno\b"),
            (r"\bdo\b", r"\bdon't\b"),
            (r"\bcan\b", r"\bcannot\b"),
        ]

        seen_pairs: Set[Tuple[UUID, UUID]] = set()

        for category, mems in by_category.items():
            if len(mems) < 2:
                continue
            for i, mem_a in enumerate(mems):
                for mem_b in mems[i + 1:]:
                    pair_key = (min(mem_a.id, mem_b.id), max(mem_a.id, mem_b.id))
                    if pair_key in seen_pairs:
                        continue
                    for pat_a, pat_b in _NEGATION_PAIRS:
                        a_has = bool(re.search(pat_a, mem_a.content, re.IGNORECASE))
                        b_has = bool(re.search(pat_b, mem_b.content, re.IGNORECASE))
                        b_a_has = bool(re.search(pat_a, mem_b.content, re.IGNORECASE))
                        a_b_has = bool(re.search(pat_b, mem_a.content, re.IGNORECASE))
                        if (a_has and b_has) or (b_a_has and a_b_has):
                            seen_pairs.add(pair_key)
                            contradictions.append(ContradictionItem(
                                memory_a_id=mem_a.id,
                                memory_a_content=mem_a.content,
                                memory_a_status=mem_a.confirmation_status,
                                memory_b_id=mem_b.id,
                                memory_b_content=mem_b.content,
                                memory_b_status=mem_b.confirmation_status,
                                contradiction_type="value_conflict",
                                explanation=(
                                    f"Two active memories in the '{category}' category appear to "
                                    f"express opposing views. This may reflect a changed preference "
                                    f"or an extraction error."
                                ),
                                confidence=_CONTRADICTION_MIN_CONFIDENCE,
                                suggested_action=(
                                    "Review both memories. Confirm the current preference and "
                                    "archive or correct the outdated one."
                                ),
                            ))
                            break

        return contradictions[:50]  # Cap at 50 to avoid overwhelming the UI

    async def get_staleness(self, user_id: UUID) -> List[StalenessItem]:
        """Detect records that are potentially outdated and need user review."""
        now = datetime.now(timezone.utc)
        items: List[StalenessItem] = []

        # --- Memories: past review_after date ---
        try:
            memories, _ = await self._memory.list_memories(
                user_id=user_id,
                lifecycle_status="active",
                page=1,
                page_size=500,
            )
            for mem in memories:
                stale = False
                reason = ""
                score = 0.0
                # review_after has passed
                if mem.review_after and mem.review_after < now:
                    days_past = (now - mem.review_after).days
                    stale = True
                    reason = f"Review date was {days_past} day(s) ago."
                    score = min(1.0, 0.5 + days_past / 60)
                # unconfirmed fact older than threshold
                elif (
                    mem.confirmation_status == "unconfirmed"
                    and mem.memory_type == "fact"
                    and (now - mem.created_at).days > _STALENESS_MEMORY_UNREVIEWED_DAYS
                ):
                    days_old = (now - mem.created_at).days
                    stale = True
                    reason = f"Unconfirmed fact memory is {days_old} days old without review."
                    score = min(1.0, 0.4 + days_old / 180)

                if stale:
                    items.append(StalenessItem(
                        source_type=SourceType.memory,
                        id=mem.id,
                        title=f"[{mem.category}] {mem.content[:80]}",
                        reason=reason,
                        last_updated=mem.updated_at,
                        navigation_path="/memories",
                        staleness_score=round(score, 3),
                    ))
        except Exception as exc:
            logger.warning("Memory staleness check error: %s", exc)

        # --- Tasks: overdue ---
        try:
            tasks, _ = await self._prod.list_tasks(
                user_id=user_id, page=1, page_size=200
            )
            for task in tasks:
                if task.status in ("done", "cancelled"):
                    continue
                if task.due_date and task.due_date < now:
                    days_overdue = (now - task.due_date).days
                    score = min(1.0, 0.5 + days_overdue / 14)
                    items.append(StalenessItem(
                        source_type=SourceType.task,
                        id=task.id,
                        title=task.title,
                        reason=f"Task is {days_overdue} day(s) overdue (due: {task.due_date.date()}).",
                        last_updated=task.updated_at,
                        navigation_path="/tasks",
                        staleness_score=round(score, 3),
                    ))
        except Exception as exc:
            logger.warning("Task staleness check error: %s", exc)

        # --- Projects: past target_date and still active ---
        try:
            projects, _ = await self._prod.list_projects(
                user_id=user_id, page=1, page_size=200
            )
            for proj in projects:
                if proj.status != "active":
                    continue
                if proj.target_date:
                    # target_date is a date object
                    from datetime import date
                    today = datetime.now(timezone.utc).date()
                    if isinstance(proj.target_date, str):
                        from datetime import date as _date
                        proj_target = _date.fromisoformat(proj.target_date)
                    else:
                        proj_target = proj.target_date
                    if proj_target < today:
                        days_overdue = (today - proj_target).days
                        score = min(1.0, 0.4 + days_overdue / 30)
                        items.append(StalenessItem(
                            source_type=SourceType.project,
                            id=proj.id,
                            title=proj.name,
                            reason=f"Project is {days_overdue} day(s) past target date and still active.",
                            last_updated=proj.updated_at,
                            navigation_path="/projects",
                            staleness_score=round(score, 3),
                        ))
        except Exception as exc:
            logger.warning("Project staleness check error: %s", exc)

        # --- Goals: past target_date and still in_progress ---
        try:
            goals, _ = await self._prod.list_goals(
                user_id=user_id, page=1, page_size=200
            )
            for goal in goals:
                if goal.status not in ("in_progress", "not_started"):
                    continue
                if goal.target_date:
                    from datetime import date
                    today = datetime.now(timezone.utc).date()
                    if isinstance(goal.target_date, str):
                        from datetime import date as _date
                        goal_target = _date.fromisoformat(goal.target_date)
                    else:
                        goal_target = goal.target_date
                    if goal_target < today:
                        days_overdue = (today - goal_target).days
                        score = min(1.0, 0.4 + days_overdue / 60)
                        items.append(StalenessItem(
                            source_type=SourceType.goal,
                            id=goal.id,
                            title=goal.title,
                            reason=f"Goal is {days_overdue} day(s) past target date and still in progress.",
                            last_updated=goal.updated_at,
                            navigation_path="/goals",
                            staleness_score=round(score, 3),
                        ))
        except Exception as exc:
            logger.warning("Goal staleness check error: %s", exc)

        # Sort by staleness score descending
        items.sort(key=lambda x: -x.staleness_score)
        return items[:100]

    async def get_relationships(
        self,
        user_id: UUID,
        source_type: SourceType,
        source_id: UUID,
    ) -> RelationshipsResponse:
        """Discover cross-entity relationships for a given source record."""
        relationships: List[RelatedRecord] = []

        # Structural relationships from FK schema
        if source_type == SourceType.task:
            relationships.extend(
                await self._relationships_for_task(user_id, source_id)
            )
        elif source_type == SourceType.project:
            relationships.extend(
                await self._relationships_for_project(user_id, source_id)
            )
        elif source_type == SourceType.goal:
            relationships.extend(
                await self._relationships_for_goal(user_id, source_id)
            )
        elif source_type == SourceType.memory:
            relationships.extend(
                await self._relationships_for_memory(user_id, source_id)
            )

        return RelationshipsResponse(
            source_type=source_type,
            source_id=source_id,
            relationships=relationships,
            total_count=len(relationships),
        )

    # ------------------------------------------------------------------
    # Relationship helpers
    # ------------------------------------------------------------------

    async def _relationships_for_task(
        self, user_id: UUID, task_id: UUID
    ) -> List[RelatedRecord]:
        results = []
        try:
            task = await self._prod.get_task(user_id, task_id)
            if not task:
                return []
            # Task → Project
            if task.project_id:
                proj = await self._prod.get_project(user_id, task.project_id)
                if proj:
                    results.append(RelatedRecord(
                        source_type=SourceType.project,
                        id=proj.id,
                        title=proj.name,
                        relationship_type=RelationshipType.related,
                        relationship_source="structural",
                        confidence=1.0,
                        navigation_path="/projects",
                    ))
            # Task → Goal
            if task.goal_id:
                goal = await self._prod.get_goal(user_id, task.goal_id)
                if goal:
                    results.append(RelatedRecord(
                        source_type=SourceType.goal,
                        id=goal.id,
                        title=goal.title,
                        relationship_type=RelationshipType.supports,
                        relationship_source="structural",
                        confidence=1.0,
                        navigation_path="/goals",
                    ))
            # Task → Parent task
            if task.parent_task_id:
                parent = await self._prod.get_task(user_id, task.parent_task_id)
                if parent:
                    results.append(RelatedRecord(
                        source_type=SourceType.task,
                        id=parent.id,
                        title=parent.title,
                        relationship_type=RelationshipType.derived_from,
                        relationship_source="structural",
                        confidence=1.0,
                        navigation_path="/tasks",
                    ))
        except Exception as exc:
            logger.warning("Task relationship discovery error: %s", exc)
        return results

    async def _relationships_for_project(
        self, user_id: UUID, project_id: UUID
    ) -> List[RelatedRecord]:
        results = []
        try:
            proj = await self._prod.get_project(user_id, project_id)
            if not proj:
                return []
            # Project → Goal
            if proj.goal_id:
                goal = await self._prod.get_goal(user_id, proj.goal_id)
                if goal:
                    results.append(RelatedRecord(
                        source_type=SourceType.goal,
                        id=goal.id,
                        title=goal.title,
                        relationship_type=RelationshipType.supports,
                        relationship_source="structural",
                        confidence=1.0,
                        navigation_path="/goals",
                    ))
            # Project → Tasks
            tasks, _ = await self._prod.list_tasks(
                user_id=user_id, project_id=project_id, page=1, page_size=20
            )
            for task in tasks:
                results.append(RelatedRecord(
                    source_type=SourceType.task,
                    id=task.id,
                    title=task.title,
                    relationship_type=RelationshipType.related,
                    relationship_source="structural",
                    confidence=1.0,
                    navigation_path="/tasks",
                ))
        except Exception as exc:
            logger.warning("Project relationship discovery error: %s", exc)
        return results

    async def _relationships_for_goal(
        self, user_id: UUID, goal_id: UUID
    ) -> List[RelatedRecord]:
        results = []
        try:
            # Goal → Projects
            projects, _ = await self._prod.list_projects(
                user_id=user_id, goal_id=goal_id, page=1, page_size=20
            )
            for proj in projects:
                results.append(RelatedRecord(
                    source_type=SourceType.project,
                    id=proj.id,
                    title=proj.name,
                    relationship_type=RelationshipType.related,
                    relationship_source="structural",
                    confidence=1.0,
                    navigation_path="/projects",
                ))
            # Goal → Tasks
            tasks, _ = await self._prod.list_tasks(
                user_id=user_id, goal_id=goal_id, page=1, page_size=20
            )
            for task in tasks:
                results.append(RelatedRecord(
                    source_type=SourceType.task,
                    id=task.id,
                    title=task.title,
                    relationship_type=RelationshipType.supports,
                    relationship_source="structural",
                    confidence=1.0,
                    navigation_path="/tasks",
                ))
        except Exception as exc:
            logger.warning("Goal relationship discovery error: %s", exc)
        return results

    async def _relationships_for_memory(
        self, user_id: UUID, memory_id: UUID
    ) -> List[RelatedRecord]:
        results = []
        try:
            mem = await self._memory.get_memory(user_id, memory_id)
            if not mem:
                return []
            # Memory → Source conversation
            if mem.source_conversation_id:
                results.append(RelatedRecord(
                    source_type=SourceType.conversation,
                    id=mem.source_conversation_id,
                    title=f"Source conversation {str(mem.source_conversation_id)[:8]}",
                    relationship_type=RelationshipType.derived_from,
                    relationship_source="structural",
                    confidence=1.0,
                    navigation_path=f"/chat/{mem.source_conversation_id}",
                ))
            # Memory → Superseded-by chain
            if mem.superseded_by_id:
                results.append(RelatedRecord(
                    source_type=SourceType.memory,
                    id=mem.superseded_by_id,
                    title=f"Correction memory {str(mem.superseded_by_id)[:8]}",
                    relationship_type=RelationshipType.supersedes,
                    relationship_source="structural",
                    confidence=1.0,
                    navigation_path="/memories",
                ))
        except Exception as exc:
            logger.warning("Memory relationship discovery error: %s", exc)
        return results

