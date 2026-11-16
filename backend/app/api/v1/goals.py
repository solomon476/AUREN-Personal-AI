"""API endpoints for Strategic Goals Management in AUREN Phase 3C.4 Productivity Core."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import DatabaseAuthError, DatabaseConnectionError, DatabaseError
from app.core.security import get_current_user
from app.models.productivity import (
    GoalCreate,
    GoalDetailModel,
    GoalListResponse,
    GoalModel,
    GoalStatus,
    GoalUpdate,
)
from app.models.user import AuthenticatedUser
from app.services.productivity.base_repository import BaseProductivityRepository
from app.services.productivity.repository import get_productivity_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goals", tags=["Goals"])


def get_user_productivity_repo(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseProductivityRepository:
    return get_productivity_repository(user_token=current_user.token)


@router.post("", response_model=GoalModel, status_code=status.HTTP_201_CREATED)
async def create_goal(
    goal_in: GoalCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> GoalModel:
    """Create a new strategic goal owned by the authenticated user."""
    try:
        return await repo.create_goal(user_id=current_user.id, goal=goal_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error creating goal for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create goal.")


@router.get("", response_model=GoalListResponse)
async def list_goals(
    status: Optional[str] = Query(None, description="Filter by status (not_started, in_progress, achieved, paused, abandoned)"),
    query: Optional[str] = Query(None, description="Search query matching goal title or description"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> GoalListResponse:
    """List goals owned by authenticated user with progress metrics and linked counts."""
    try:
        items, total = await repo.list_goals(
            user_id=current_user.id,
            status=status,
            query=query,
            page=page,
            page_size=page_size,
        )
        return GoalListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except DatabaseError as exc:
        logger.error("Database error listing goals for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list goals.")


@router.get("/{goal_id}", response_model=GoalDetailModel)
async def get_goal(
    goal_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> GoalDetailModel:
    """Retrieve a single goal with its associated projects and tasks."""
    try:
        goal = await repo.get_goal(user_id=current_user.id, goal_id=goal_id)
        if not goal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
        return goal
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error getting goal %s: %s", goal_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve goal.")


@router.patch("/{goal_id}", response_model=GoalModel)
async def update_goal(
    goal_id: UUID,
    update_in: GoalUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> GoalModel:
    """Update a goal owned by the authenticated user."""
    try:
        goal = await repo.update_goal(user_id=current_user.id, goal_id=goal_id, update=update_in)
        if not goal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
        return goal
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error updating goal %s: %s", goal_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update goal.")


@router.post("/{goal_id}/status", response_model=GoalModel)
async def change_goal_status(
    goal_id: UUID,
    new_status: GoalStatus = Query(..., description="Target goal status"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> GoalModel:
    """Change the lifecycle status of a goal."""
    try:
        goal = await repo.update_goal(
            user_id=current_user.id,
            goal_id=goal_id,
            update=GoalUpdate(status=new_status),
        )
        if not goal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
        return goal
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error changing status for goal %s: %s", goal_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update goal status.")


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
):
    """Delete a goal. Linked projects and tasks have goal_id set to NULL."""
    try:
        deleted = await repo.delete_goal(user_id=current_user.id, goal_id=goal_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error deleting goal %s: %s", goal_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete goal.")

