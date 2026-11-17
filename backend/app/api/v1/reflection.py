"""Phase 3C.5: Reflective Intelligence REST API endpoints.

Provides:
  - GET /api/v1/reflection/insights   — combined contradiction + staleness overview.
  - GET /api/v1/reflection/contradictions — contradiction analysis only.
  - GET /api/v1/reflection/staleness      — staleness review items only.
  - GET /api/v1/reflection/relationships  — cross-entity relationships for a record.
  - POST /api/v1/reflection/links         — create a user-confirmed record link (SQLite only).

Design constraints:
  - READ-ONLY analysis: no records are modified through this API.
  - Strictly user-scoped: auth.uid() ownership enforced at every level.
  - Journal entries are never examined or returned.
  - All suggestions are framed as review recommendations, not facts.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response

from app.core.security import get_current_user
from app.models.search import (
    RecordLinkCreate,
    RecordLinkItem,
    ReflectionInsightsResponse,
    RelationshipType,
    RelationshipsResponse,
    SourceType,
)
from app.models.user import AuthenticatedUser
from app.services.memory.repository import get_memory_repository
from app.services.productivity.repository import get_productivity_repository
from app.services.reflection.reflection_service import ReflectionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reflection", tags=["Reflection"])


def _get_reflection_service(user: AuthenticatedUser = Depends(get_current_user)) -> ReflectionService:
    token = user.token
    return ReflectionService(
        memory_repo=get_memory_repository(user_token=token),
        productivity_repo=get_productivity_repository(user_token=token),
    )


@router.get(
    "/insights",
    response_model=ReflectionInsightsResponse,
    summary="Combined reflective intelligence overview",
    description=(
        "Returns a combined summary of potential contradictions, staleness items, "
        "and inferred relationship counts. All findings are suggestions for user review — "
        "no records are modified. Journal entries are excluded."
    ),
)
async def get_insights(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ReflectionService = Depends(_get_reflection_service),
) -> ReflectionInsightsResponse:
    return await service.get_insights(user.user_id)


@router.get(
    "/contradictions",
    summary="Potential contradiction analysis",
    description="Detects memory records with potentially conflicting or superseded facts.",
)
async def get_contradictions(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ReflectionService = Depends(_get_reflection_service),
):
    contradictions = await service.get_contradictions(user.user_id)
    return {"contradictions": [c.model_dump() for c in contradictions], "count": len(contradictions)}


@router.get(
    "/staleness",
    summary="Potentially outdated records review",
    description="Identifies overdue tasks, lapsed projects/goals, and unreviewed memories.",
)
async def get_staleness(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ReflectionService = Depends(_get_reflection_service),
):
    items = await service.get_staleness(user.user_id)
    return {"items": [i.model_dump() for i in items], "count": len(items)}


@router.get(
    "/relationships",
    response_model=RelationshipsResponse,
    summary="Cross-entity relationships for a record",
    description=(
        "Returns all known structural and inferred relationships for the specified entity. "
        "Structural relationships come from FK schema (task→project, project→goal, etc.). "
        "Inferred relationships are labelled with is_inferred=true in results."
    ),
)
async def get_relationships(
    source_type: SourceType = Query(..., description="Entity type (task, project, goal, memory, conversation, message)"),
    source_id: UUID = Query(..., description="Entity UUID"),
    user: AuthenticatedUser = Depends(get_current_user),
    service: ReflectionService = Depends(_get_reflection_service),
) -> RelationshipsResponse:
    return await service.get_relationships(user.user_id, source_type, source_id)


# ---------------------------------------------------------------------------
# Record Links (Phase 3C.5.2 / API-01)
# ---------------------------------------------------------------------------

@router.post(
    "/links",
    response_model=RecordLinkItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user-confirmed cross-entity relationship link",
    description=(
        "Persists a relationship link between two entities owned by the authenticated user. "
        "Validates that both source and target exist and belong to the user."
    ),
)
async def create_link(
    link: RecordLinkCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ReflectionService = Depends(_get_reflection_service),
) -> RecordLinkItem:
    try:
        return await service.create_link(user.user_id, link)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error creating record link: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create record link",
        )


@router.get(
    "/links",
    response_model=List[RecordLinkItem],
    summary="List record links for an entity",
    description="Returns all record links where source_id matches and the record is owned by the user.",
)
async def list_links(
    source_type: SourceType = Query(..., description="Entity type of the source record"),
    source_id: UUID = Query(..., description="UUID of the source record"),
    user: AuthenticatedUser = Depends(get_current_user),
    service: ReflectionService = Depends(_get_reflection_service),
) -> List[RecordLinkItem]:
    return await service.list_links(user.user_id, source_type, source_id)


@router.delete(
    "/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user-confirmed record link",
    description="Deletes a record link owned by the authenticated user.",
)
async def delete_link(
    link_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ReflectionService = Depends(_get_reflection_service),
):
    deleted = await service.delete_link(user.user_id, link_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record link not found or not owned by user",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

