"""API endpoints for Productivity Dashboard and Conversational AI Context."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import DatabaseError
from app.core.security import get_current_user
from app.models.productivity import (
    ProductivityContextSummary,
    ProductivityDashboardResponse,
)
from app.models.user import AuthenticatedUser
from app.services.productivity.base_repository import BaseProductivityRepository
from app.services.productivity.repository import get_productivity_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/productivity", tags=["Productivity Dashboard & Context"])


def get_user_productivity_repo(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseProductivityRepository:
    return get_productivity_repository(user_token=current_user.token)


@router.get("/dashboard", response_model=ProductivityDashboardResponse)
async def get_dashboard(
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ProductivityDashboardResponse:
    """Retrieve aggregated productivity metrics and urgent/active commitments."""
    try:
        return await repo.get_dashboard(user_id=current_user.id)
    except DatabaseError as exc:
        logger.error("Database error retrieving dashboard for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve productivity dashboard.")


@router.get("/context", response_model=ProductivityContextSummary)
async def get_productivity_context(
    max_items: int = Query(10, ge=1, le=50, description="Max items per commitment section"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ProductivityContextSummary:
    """Retrieve bounded, read-only productivity context summary for AI conversational assistance."""
    try:
        return await repo.get_productivity_context(user_id=current_user.id, max_items=max_items)
    except DatabaseError as exc:
        logger.error("Database error retrieving productivity context for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve productivity context.")

