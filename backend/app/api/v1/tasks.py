"""API endpoints for Tasks Management in AUREN Phase 3C.4 Productivity Core."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import DatabaseAuthError, DatabaseConnectionError, DatabaseError
from app.core.security import get_current_user
from app.models.productivity import (
    TaskCreate,
    TaskListResponse,
    TaskModel,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
)
from app.models.user import AuthenticatedUser
from app.services.productivity.base_repository import BaseProductivityRepository
from app.services.productivity.repository import get_productivity_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def get_user_productivity_repo(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseProductivityRepository:
    return get_productivity_repository(user_token=current_user.token)


@router.post("", response_model=TaskModel, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> TaskModel:
    """Create a new task owned by the authenticated user."""
    try:
        return await repo.create_task(user_id=current_user.id, task=task_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error creating task for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create task.")


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    goal_id: Optional[UUID] = Query(None, description="Filter by goal ID"),
    status: Optional[str] = Query(None, description="Filter by status (todo, in_progress, blocked, completed, cancelled)"),
    priority: Optional[str] = Query(None, description="Filter by priority (low, medium, high, urgent)"),
    query: Optional[str] = Query(None, description="Search query matching title or description"),
    parent_task_id: Optional[UUID] = Query(None, description="Filter subtasks by parent task ID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> TaskListResponse:
    """List tasks owned by authenticated user with filtering and pagination."""
    try:
        items, total = await repo.list_tasks(
            user_id=current_user.id,
            project_id=project_id,
            goal_id=goal_id,
            status=status,
            priority=priority,
            query=query,
            parent_task_id=parent_task_id,
            page=page,
            page_size=page_size,
        )
        return TaskListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except DatabaseError as exc:
        logger.error("Database error listing tasks for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list tasks.")


@router.get("/{task_id}", response_model=TaskModel)
async def get_task(
    task_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> TaskModel:
    """Retrieve a single task owned by the authenticated user."""
    try:
        task = await repo.get_task(user_id=current_user.id, task_id=task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return task
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error getting task %s: %s", task_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve task.")


@router.patch("/{task_id}", response_model=TaskModel)
async def update_task(
    task_id: UUID,
    update_in: TaskUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> TaskModel:
    """Update a task owned by the authenticated user."""
    try:
        task = await repo.update_task(user_id=current_user.id, task_id=task_id, update=update_in)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return task
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error updating task %s: %s", task_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update task.")


@router.post("/{task_id}/status", response_model=TaskModel)
async def change_task_status(
    task_id: UUID,
    new_status: TaskStatus = Query(..., description="Target task status"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> TaskModel:
    """Change the lifecycle status of a task."""
    try:
        task = await repo.update_task(
            user_id=current_user.id,
            task_id=task_id,
            update=TaskUpdate(status=new_status),
        )
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return task
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error changing status for task %s: %s", task_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update task status.")


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
):
    """Delete a task owned by the authenticated user."""
    try:
        deleted = await repo.delete_task(user_id=current_user.id, task_id=task_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error deleting task %s: %s", task_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete task.")

