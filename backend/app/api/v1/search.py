"""Phase 3C.5: Omnisearch REST API endpoint.

Provides unified search across AUREN personal data entities.
All queries are strictly scoped to the authenticated user; no cross-tenant
data exposure is possible.

Journal entries are excluded from all search results by design.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.security import get_current_user
from app.models.search import OmnisearchResponse, SourceType
from app.models.user import AuthenticatedUser
from app.services.chat.repository import get_chat_repository
from app.services.memory.repository import get_memory_repository
from app.services.productivity.repository import get_productivity_repository
from app.services.search.omnisearch_service import OmnisearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


def _get_omnisearch_service(user: AuthenticatedUser = Depends(get_current_user)) -> OmnisearchService:
    """Dependency: build OmnisearchService with the appropriate backend repositories."""
    token = user.token
    return OmnisearchService(
        chat_repo=get_chat_repository(user_token=token),
        memory_repo=get_memory_repository(user_token=token),
        productivity_repo=get_productivity_repository(user_token=token),
    )


@router.get(
    "",
    response_model=OmnisearchResponse,
    summary="Unified lexical search across all personal data entities",
    description=(
        "Search conversations, messages, memories, tasks, projects, and goals "
        "in a single request. Omnisearch performs lexical keyword matching across "
        "all entity records and ranks results by token coverage and recency. "
        "(For semantic vector retrieval, see chat context memory injection.) "
        "Journal entries are excluded. All results belong exclusively to the "
        "authenticated user."
    ),
)
async def omnisearch(
    q: str = Query(..., min_length=1, max_length=500, description="Search query string"),
    sources: Optional[List[SourceType]] = Query(
        default=None,
        description="Filter to specific source types. Omit for all sources."
    ),
    date_from: Optional[datetime] = Query(default=None, description="Earliest created_at (ISO 8601)"),
    date_to: Optional[datetime] = Query(default=None, description="Latest created_at (ISO 8601)"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    user: AuthenticatedUser = Depends(get_current_user),
    service: OmnisearchService = Depends(_get_omnisearch_service),
) -> OmnisearchResponse:
    return await service.search(
        user_id=user.user_id,
        query=q,
        sources=sources,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
