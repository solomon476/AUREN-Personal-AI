"""Phase 3C.5 Omnisearch Service.

Coordinates cross-entity search across conversations, messages, memories,
tasks, projects, and goals. All queries are strictly scoped by user_id;
no cross-tenant data exposure is possible through this service.

Design principles:
- Each source is searched independently with its own relevance heuristic.
- Results are merged and re-ranked by a normalised score.
- Journal entries are NEVER included (they are consent-protected).
- AI-extracted unconfirmed memories are labelled distinctly in provenance.
- All returned navigation_paths are frontend routes, not API URLs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.models.search import (
    OmnisearchResponse,
    SearchResultItem,
    SourceType,
)
from app.services.chat.base_repository import BaseChatRepository
from app.services.memory.base_repository import BaseMemoryRepository
from app.services.productivity.base_repository import BaseProductivityRepository

logger = logging.getLogger(__name__)

# Maximum snippets length (characters)
_SNIPPET_MAX = 200
# Maximum results fetched per source before merge/rank
_PER_SOURCE_LIMIT = 50


def _make_snippet(text: str, query: str, max_len: int = _SNIPPET_MAX) -> str:
    """Extract a short, query-relevant snippet from text."""
    if not text:
        return ""
    text = text.strip()
    q_lower = query.lower()
    t_lower = text.lower()
    idx = t_lower.find(q_lower)
    if idx >= 0:
        # Centre the window around the match
        start = max(0, idx - 60)
        end = min(len(text), idx + len(query) + 100)
        snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    else:
        snippet = text[:max_len] + ("…" if len(text) > max_len else "")
    return snippet[:max_len + 10]


def _lexical_score(text: str, query: str) -> float:
    """Simple TF-style lexical relevance score in [0, 1]."""
    if not text or not query:
        return 0.0
    tokens = re.findall(r"\w+", query.lower())
    if not tokens:
        return 0.0
    t_lower = text.lower()
    hits = sum(1 for tok in tokens if tok in t_lower)
    return min(1.0, hits / len(tokens))


def _apply_date_filter(
    dt: Optional[datetime],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> bool:
    """Return True if dt passes the date filter window."""
    if dt is None:
        return True
    if date_from and dt < date_from:
        return False
    if date_to and dt > date_to:
        return False
    return True


class OmnisearchService:
    """Unified search coordinator for all AUREN personal data entities."""

    def __init__(
        self,
        chat_repo: BaseChatRepository,
        memory_repo: BaseMemoryRepository,
        productivity_repo: BaseProductivityRepository,
    ) -> None:
        self._chat = chat_repo
        self._memory = memory_repo
        self._prod = productivity_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        user_id: UUID,
        query: str,
        sources: Optional[List[SourceType]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OmnisearchResponse:
        """Execute a unified search and return paginated, ranked results."""
        query = query.strip()
        active_sources = sources or list(SourceType)

        all_results: List[SearchResultItem] = []

        # Fan out across sources concurrently — each is a coroutine
        import asyncio
        tasks = []
        if SourceType.conversation in active_sources:
            tasks.append(self._search_conversations(user_id, query, date_from, date_to))
        if SourceType.message in active_sources:
            tasks.append(self._search_messages(user_id, query, date_from, date_to))
        if SourceType.memory in active_sources:
            tasks.append(self._search_memories(user_id, query, date_from, date_to))
        if SourceType.task in active_sources:
            tasks.append(self._search_tasks(user_id, query, date_from, date_to))
        if SourceType.project in active_sources:
            tasks.append(self._search_projects(user_id, query, date_from, date_to))
        if SourceType.goal in active_sources:
            tasks.append(self._search_goals(user_id, query, date_from, date_to))

        source_results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in source_results:
            if isinstance(res, Exception):
                logger.warning("Omnisearch source error: %s", res)
            elif isinstance(res, list):
                all_results.extend(res)

        # Sort by score descending, then by recency
        all_results.sort(key=lambda r: (-r.score, -(r.created_at.timestamp())))

        total_count = len(all_results)
        offset = (page - 1) * page_size
        page_results = all_results[offset : offset + page_size]

        return OmnisearchResponse(
            query=query,
            sources_searched=active_sources,
            results=page_results,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_more=(offset + page_size) < total_count,
        )

    # ------------------------------------------------------------------
    # Per-source search helpers
    # ------------------------------------------------------------------

    async def _search_conversations(
        self,
        user_id: UUID,
        query: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[SearchResultItem]:
        try:
            convs = await self._chat.list_conversations(user_id, limit=_PER_SOURCE_LIMIT)
        except Exception as exc:
            logger.warning("Conversation search error: %s", exc)
            return []

        results = []
        for conv in convs:
            title = conv.title or ""
            score = _lexical_score(title, query)
            if score <= 0:
                continue
            if not _apply_date_filter(conv.created_at, date_from, date_to):
                continue
            results.append(SearchResultItem(
                source_type=SourceType.conversation,
                id=conv.id,
                title=title or f"Conversation {str(conv.id)[:8]}",
                snippet=_make_snippet(title, query),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                score=round(score * 0.9, 4),  # conversations are broad context
                provenance="conversation",
                navigation_path=f"/chat/{conv.id}",
                metadata={},
            ))
        return results

    async def _search_messages(
        self,
        user_id: UUID,
        query: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[SearchResultItem]:
        try:
            convs = await self._chat.list_conversations(user_id, limit=50)
        except Exception as exc:
            logger.warning("Message search (conv list) error: %s", exc)
            return []

        results = []
        for conv in convs:
            try:
                messages = await self._chat.get_messages(user_id, conv.id, limit=200)
            except Exception as exc:
                logger.debug("Message fetch error for conv %s: %s", conv.id, exc)
                continue
            for msg in messages:
                content = msg.content or ""
                score = _lexical_score(content, query)
                if score <= 0:
                    continue
                if not _apply_date_filter(msg.created_at, date_from, date_to):
                    continue
                role_label = "You" if msg.role == "user" else "AUREN"
                results.append(SearchResultItem(
                    source_type=SourceType.message,
                    id=msg.id,
                    title=f"Message in: {conv.title or str(conv.id)[:8]} ({role_label})",
                    snippet=_make_snippet(content, query),
                    created_at=msg.created_at,
                    updated_at=None,
                    score=round(score, 4),
                    provenance=f"chat message ({msg.role})",
                    navigation_path=f"/chat/{conv.id}",
                    metadata={"conversation_id": str(conv.id), "role": msg.role},
                ))
                if len(results) >= _PER_SOURCE_LIMIT:
                    break
            if len(results) >= _PER_SOURCE_LIMIT:
                break
        return results

    async def _search_memories(
        self,
        user_id: UUID,
        query: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[SearchResultItem]:
        try:
            memories, _ = await self._memory.list_memories(
                user_id=user_id,
                query=query,
                lifecycle_status="active",
                page=1,
                page_size=_PER_SOURCE_LIMIT,
            )
        except Exception as exc:
            logger.warning("Memory search error: %s", exc)
            return []

        results = []
        for mem in memories:
            if not _apply_date_filter(mem.created_at, date_from, date_to):
                continue
            score = _lexical_score(mem.content, query)
            if score <= 0:
                score = 0.3  # was returned by list filter, give base score
            # Confidence × score (confirmed memories rank higher)
            conf_boost = 1.0 if mem.confirmation_status == "confirmed" else 0.7
            final_score = round(min(1.0, score * conf_boost), 4)

            provenance_parts = [mem.confirmation_status.replace("_", " ")]
            if mem.origin == "ai_extraction":
                provenance_parts.append("ai-extracted")
            provenance = " · ".join(provenance_parts) + " memory"

            results.append(SearchResultItem(
                source_type=SourceType.memory,
                id=mem.id,
                title=f"[{mem.category}] {mem.content[:80]}",
                snippet=_make_snippet(mem.content, query),
                created_at=mem.created_at,
                updated_at=mem.updated_at,
                score=final_score,
                provenance=provenance,
                navigation_path="/memories",
                metadata={
                    "category": mem.category,
                    "memory_type": mem.memory_type,
                    "confirmation_status": mem.confirmation_status,
                    "lifecycle_status": mem.lifecycle_status,
                },
            ))
        return results

    async def _search_tasks(
        self,
        user_id: UUID,
        query: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[SearchResultItem]:
        try:
            tasks, _ = await self._prod.list_tasks(
                user_id=user_id, page=1, page_size=_PER_SOURCE_LIMIT
            )
        except Exception as exc:
            logger.warning("Task search error: %s", exc)
            return []

        results = []
        for task in tasks:
            searchable = " ".join(filter(None, [task.title, task.description or ""]))
            if task.tags:
                searchable += " " + " ".join(task.tags)
            score = _lexical_score(searchable, query)
            if score <= 0:
                continue
            if not _apply_date_filter(task.created_at, date_from, date_to):
                continue
            results.append(SearchResultItem(
                source_type=SourceType.task,
                id=task.id,
                title=task.title,
                snippet=_make_snippet(searchable, query),
                created_at=task.created_at,
                updated_at=task.updated_at,
                score=round(score, 4),
                provenance="task",
                navigation_path="/tasks",
                metadata={"status": task.status, "priority": task.priority},
            ))
        return results

    async def _search_projects(
        self,
        user_id: UUID,
        query: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[SearchResultItem]:
        try:
            projects, _ = await self._prod.list_projects(
                user_id=user_id, page=1, page_size=_PER_SOURCE_LIMIT
            )
        except Exception as exc:
            logger.warning("Project search error: %s", exc)
            return []

        results = []
        for proj in projects:
            searchable = " ".join(filter(None, [proj.name, proj.description or ""]))
            score = _lexical_score(searchable, query)
            if score <= 0:
                continue
            if not _apply_date_filter(proj.created_at, date_from, date_to):
                continue
            results.append(SearchResultItem(
                source_type=SourceType.project,
                id=proj.id,
                title=proj.name,
                snippet=_make_snippet(searchable, query),
                created_at=proj.created_at,
                updated_at=proj.updated_at,
                score=round(score, 4),
                provenance="project",
                navigation_path="/projects",
                metadata={"status": proj.status},
            ))
        return results

    async def _search_goals(
        self,
        user_id: UUID,
        query: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[SearchResultItem]:
        try:
            goals, _ = await self._prod.list_goals(
                user_id=user_id, page=1, page_size=_PER_SOURCE_LIMIT
            )
        except Exception as exc:
            logger.warning("Goal search error: %s", exc)
            return []

        results = []
        for goal in goals:
            searchable = " ".join(filter(None, [goal.title, goal.description or ""]))
            score = _lexical_score(searchable, query)
            if score <= 0:
                continue
            if not _apply_date_filter(goal.created_at, date_from, date_to):
                continue
            results.append(SearchResultItem(
                source_type=SourceType.goal,
                id=goal.id,
                title=goal.title,
                snippet=_make_snippet(searchable, query),
                created_at=goal.created_at,
                updated_at=goal.updated_at,
                score=round(score, 4),
                provenance="goal",
                navigation_path="/goals",
                metadata={"status": goal.status},
            ))
        return results
