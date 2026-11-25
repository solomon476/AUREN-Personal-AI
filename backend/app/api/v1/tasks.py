"""API endpoints for Tasks Management in AUREN Phase 3C.4 Productivity Core with Smart Reminder integration."""

from datetime import datetime, timedelta, timezone
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
from app.models.reminders import (
    NotificationPreferences,
    ReminderCreate,
    ReminderListResponse,
    ReminderModel,
    ReminderPriority,
    ReminderSource,
    ReminderType,
)
from app.models.user import AuthenticatedUser
from app.services.profile_service import profile_service
from app.services.productivity.base_repository import BaseProductivityRepository
from app.services.productivity.repository import get_productivity_repository
from app.services.reminders.repository import get_reminder_repository
from app.services.reminders.time_utils import ensure_utc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def get_user_productivity_repo(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseProductivityRepository:
    return get_productivity_repository(user_token=current_user.token)


async def _load_user_notif_prefs(user: AuthenticatedUser) -> NotificationPreferences:
    try:
        profile = await profile_service.get_profile(user)
        return NotificationPreferences.from_user_prefs(profile.preferences)
    except Exception:
        return NotificationPreferences()


async def _sync_task_reminder(
    user: AuthenticatedUser,
    task: TaskModel,
    reminder_mode: Optional[str],
    reminder_offset_minutes: Optional[int],
    reminder_at: Optional[datetime],
    reminder_is_alarm: Optional[bool],
    reminder_timezone: Optional[str],
) -> Optional[ReminderModel]:
    """Create or update a deduplicated task-linked reminder without confusing deadline vs trigger time."""
    if not reminder_mode or reminder_mode == "none":
        if reminder_at is None:
            return None
        reminder_mode = "custom"

    prefs = await _load_user_notif_prefs(user)
    tz_name = reminder_timezone or prefs.timezone or "UTC"
    rem_repo = get_reminder_repository(user_token=user.token)

    if reminder_mode == "at_due":
        if not task.due_date:
            return None
        trig_utc = ensure_utc(task.due_date, tz_name)
        r_type = ReminderType.task_due
        dedupe = f"task:{task.id}:due"
    elif reminder_mode == "before_due":
        if not task.due_date:
            return None
        offset = reminder_offset_minutes if reminder_offset_minutes is not None else prefs.task_default_lead_minutes
        trig_utc = ensure_utc(task.due_date, tz_name) - timedelta(minutes=max(1, offset))
        r_type = ReminderType.task_before_due
        dedupe = f"task:{task.id}:before_due"
    else:  # custom explicit reminder timestamp independent of task due_date
        if not reminder_at:
            return None
        trig_utc = ensure_utc(reminder_at, tz_name)
        r_type = ReminderType.alarm if reminder_is_alarm else ReminderType.general
        dedupe = f"task:{task.id}:custom:{trig_utc.isoformat()}"

    is_alarm = bool(reminder_is_alarm)
    prio = ReminderPriority.alarm if is_alarm else (
        ReminderPriority.high if task.priority.value in ("urgent", "high") else ReminderPriority.normal
    )
    return await rem_repo.create_reminder(
        user_id=user.id,
        reminder=ReminderCreate(
            title=task.title,
            description=task.description or (f"Deadline: {task.due_date.isoformat()}" if task.due_date else None),
            reminder_type=r_type,
            trigger_at=trig_utc,
            timezone=tz_name,
            priority=prio,
            is_alarm=is_alarm,
            task_id=task.id,
            project_id=task.project_id,
            goal_id=task.goal_id,
            source=ReminderSource.task_sync,
            dedupe_key=dedupe,
        ),
    )


@router.post("", response_model=TaskModel, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> TaskModel:
    """Create a new task owned by the authenticated user (and optional distinct reminder)."""
    try:
        created = await repo.create_task(user_id=current_user.id, task=task_in)
        if task_in.reminder_mode or task_in.reminder_at:
            try:
                await _sync_task_reminder(
                    user=current_user,
                    task=created,
                    reminder_mode=task_in.reminder_mode,
                    reminder_offset_minutes=task_in.reminder_offset_minutes,
                    reminder_at=task_in.reminder_at,
                    reminder_is_alarm=task_in.reminder_is_alarm,
                    reminder_timezone=task_in.reminder_timezone,
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
            prefs = await _load_user_notif_prefs(current_user)
            rem_repo = get_reminder_repository(user_token=current_user.token)
            # Suppress future task reminders on completion/cancellation if configured
            if task.status in (TaskStatus.completed, TaskStatus.cancelled) and prefs.suppress_reminders_on_task_complete:
                await rem_repo.suppress_task_reminders(user_id=current_user.id, task_id=task.id)
            else:
                # Reschedule task-linked reminders when task due_date changes
                if update_in.due_date is not None and update_in.due_date != existing.due_date and prefs.auto_reschedule_task_reminders:
                    await rem_repo.reschedule_task_reminders(
                        user_id=current_user.id,
                        task_id=task.id,
                        new_due_date=update_in.due_date,
                        default_lead_minutes=prefs.task_default_lead_minutes,
                    )
                if update_in.reminder_mode or update_in.reminder_at:
                    await _sync_task_reminder(
                        user=current_user,
                        task=task,
                        reminder_mode=update_in.reminder_mode,
                        reminder_offset_minutes=update_in.reminder_offset_minutes,
                        reminder_at=update_in.reminder_at,
                        reminder_is_alarm=update_in.reminder_is_alarm,
                        reminder_timezone=update_in.reminder_timezone,
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
                prefs = await _load_user_notif_prefs(current_user)
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
