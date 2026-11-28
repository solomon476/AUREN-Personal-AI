"""API endpoints for Tasks Management in AUREN Phase 3C.4 Productivity Core with Smart Reminder integration."""

from datetime import datetime
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import DatabaseError
from app.core.security import get_current_user
from app.models.productivity import (
    TaskCreate,
    TaskListResponse,
    TaskModel,
    TaskStatus,
    TaskUpdate,
)
from app.models.reminders import ReminderListResponse
from app.models.user import AuthenticatedUser
from app.services.productivity.base_repository import BaseProductivityRepository
from app.services.productivity.repository import get_productivity_repository
from app.services.productivity.task_reminder_sync import (
    apply_task_create_reminder_sync,
    apply_task_update_reminder_sync,
    load_user_notif_prefs,
)
from app.services.reminders.repository import get_reminder_repository

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
    """Create a new task owned by the authenticated user (and optional distinct reminder)."""
    try:
        created = await repo.create_task(user_id=current_user.id, task=task_in)
        try:
            await apply_task_create_reminder_sync(
                user=current_user,
                task_in=task_in,
                created=created,
            )
        except Exception as rem_err:
            logger.warning("Task created but reminder creation warning for task %s: %s", created.id, rem_err)
        return created
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
    """Update a task and synchronize linked reminders according to user preferences."""
    try:
        existing = await repo.get_task(user_id=current_user.id, task_id=task_id)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

        task = await repo.update_task(user_id=current_user.id, task_id=task_id, update=update_in)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

        try:
            await apply_task_update_reminder_sync(
                user=current_user,
                existing=existing,
                updated=task,
                update_in=update_in,
            )
        except Exception as rem_err:
            logger.warning("Task updated reminder-sync warning for %s: %s", task.id, rem_err)

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
    """Change the lifecycle status of a task and suppress future reminders if completed."""
    try:
        task = await repo.update_task(
            user_id=current_user.id,
            task_id=task_id,
            update=TaskUpdate(status=new_status),
        )
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        if new_status in (TaskStatus.completed, TaskStatus.cancelled):
            try:
                prefs = await load_user_notif_prefs(current_user)
                if prefs.suppress_reminders_on_task_complete:
                    rem_repo = get_reminder_repository(user_token=current_user.token)
                    await rem_repo.suppress_task_reminders(user_id=current_user.id, task_id=task.id)
            except Exception as rem_err:
                logger.warning("Reminder suppression warning on task status change %s: %s", task.id, rem_err)
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
    """Delete a task owned by the authenticated user and suppress its future scheduled reminders."""
    try:
        deleted = await repo.delete_task(user_id=current_user.id, task_id=task_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        try:
            rem_repo = get_reminder_repository(user_token=current_user.token)
            await rem_repo.suppress_task_reminders(user_id=current_user.id, task_id=task_id)
        except Exception:
            pass
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error deleting task %s: %s", task_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete task.")


@router.get("/{task_id}/reminders", response_model=ReminderListResponse)
async def list_task_reminders(
    task_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ReminderListResponse:
    """List reminders linked to a specific task."""
    task = await repo.get_task(user_id=current_user.id, task_id=task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    rem_repo = get_reminder_repository(user_token=current_user.token)
    items, total = await rem_repo.list_reminders(user_id=current_user.id, task_id=task_id, page=1, page_size=50)
    return ReminderListResponse(items=items, total=total, page=1, page_size=50)
