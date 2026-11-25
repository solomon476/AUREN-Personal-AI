"""API endpoints for Smart Reminders management (CRUD, Snooze, Complete, Cancel, Reschedule)."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import DatabaseError
from app.core.security import get_current_user
from app.models.reminders import (
    ReminderCreate,
    ReminderListResponse,
    ReminderModel,
    ReminderRescheduleRequest,
    ReminderSnoozeRequest,
    ReminderUpdate,
)
from app.models.user import AuthenticatedUser
from app.services.profile_service import profile_service
from app.services.reminders.base_repository import BaseReminderRepository
from app.services.reminders.repository import get_reminder_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reminders", tags=["Reminders & Alarms"])


def get_user_reminder_repo(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseReminderRepository:
    return get_reminder_repository(user_token=current_user.token)


@router.post("", response_model=ReminderModel, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    reminder_in: ReminderCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderModel:
    """Create a new persisted reminder owned by the authenticated user."""
    try:
        return await repo.create_reminder(user_id=current_user.id, reminder=reminder_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error creating reminder for %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create reminder.")


@router.get("", response_model=ReminderListResponse)
async def list_reminders(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="upcoming | due | snoozed | completed | cancelled | missed | history | all",
    ),
    recurring_only: bool = Query(False),
    task_id: Optional[UUID] = Query(None),
    query: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderListResponse:
    """List reminders belonging strictly to the authenticated user."""
    try:
        items, total = await repo.list_reminders(
            user_id=current_user.id,
            status=status_filter,
            recurring_only=recurring_only,
            task_id=task_id,
            query=query,
            page=page,
            page_size=page_size,
        )
        return ReminderListResponse(items=items, total=total, page=page, page_size=page_size)
    except DatabaseError as exc:
        logger.error("Database error listing reminders for %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list reminders.")


@router.get("/{reminder_id}", response_model=ReminderModel)
async def get_reminder(
    reminder_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderModel:
    """Retrieve a single reminder owned by the authenticated user."""
    item = await repo.get_reminder(user_id=current_user.id, reminder_id=reminder_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
    return item


@router.patch("/{reminder_id}", response_model=ReminderModel)
async def update_reminder(
    reminder_id: UUID,
    update_in: ReminderUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderModel:
    """Update reminder details, sound, recurrence, or scheduled time."""
    updated = await repo.update_reminder(user_id=current_user.id, reminder_id=reminder_id, update=update_in)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
    return updated


@router.post("/{reminder_id}/snooze", response_model=ReminderModel)
async def snooze_reminder(
    reminder_id: UUID,
    payload: Optional[ReminderSnoozeRequest] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderModel:
    """Snooze a reminder for requested minutes or user's default snooze duration."""
    minutes = payload.snooze_minutes if payload else None
    if minutes is None:
        try:
            prof = await profile_service.get_profile(current_user)
            minutes = int(prof.preferences.get("default_snooze_minutes", 10))
        except Exception:
            minutes = 10
    snooze_until = datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes))
    updated = await repo.snooze_reminder(user_id=current_user.id, reminder_id=reminder_id, snoozed_until=snooze_until)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
    return updated


@router.post("/{reminder_id}/complete", response_model=ReminderModel)
async def complete_reminder(
    reminder_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderModel:
    """Mark a reminder completed."""
    updated = await repo.complete_reminder(user_id=current_user.id, reminder_id=reminder_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
    return updated


@router.post("/{reminder_id}/cancel", response_model=ReminderModel)
async def cancel_reminder(
    reminder_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderModel:
    """Cancel a scheduled or active reminder."""
    updated = await repo.cancel_reminder(user_id=current_user.id, reminder_id=reminder_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
    return updated


@router.post("/{reminder_id}/reschedule", response_model=ReminderModel)
async def reschedule_reminder(
    reminder_id: UUID,
    payload: ReminderRescheduleRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> ReminderModel:
    """Reschedule a reminder to a new timestamp and optional timezone."""
    updated = await repo.update_reminder(
        user_id=current_user.id,
        reminder_id=reminder_id,
        update=ReminderUpdate(trigger_at=payload.trigger_at, timezone=payload.timezone),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
    return updated


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_reminder_repo),
) -> None:
    """Permanently delete a reminder owned by the authenticated user."""
    deleted = await repo.delete_reminder(user_id=current_user.id, reminder_id=reminder_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")

