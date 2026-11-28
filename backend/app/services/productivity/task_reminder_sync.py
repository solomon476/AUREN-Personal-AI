"""Shared Task-to-Reminder synchronization helpers used by both REST endpoints and Chat commands."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional

from app.models.productivity import TaskCreate, TaskModel, TaskStatus, TaskUpdate
from app.models.reminders import (
    NotificationPreferences,
    ReminderCreate,
    ReminderModel,
    ReminderPriority,
    ReminderSource,
    ReminderType,
)
from app.models.user import AuthenticatedUser
from app.services.profile_service import profile_service
from app.services.reminders.base_repository import BaseReminderRepository
from app.services.reminders.repository import get_reminder_repository
from app.services.reminders.time_utils import ensure_utc

logger = logging.getLogger(__name__)


async def load_user_notif_prefs(user: AuthenticatedUser) -> NotificationPreferences:
    """Load notification preferences safely for task-reminder auto-scheduling."""
    try:
        profile = await profile_service.get_profile(user)
        return NotificationPreferences.from_user_prefs(profile.preferences)
    except Exception:
        return NotificationPreferences()


async def sync_task_reminder(
    user: AuthenticatedUser,
    task: TaskModel,
    reminder_mode: Optional[str],
    reminder_offset_minutes: Optional[int],
    reminder_at: Optional[datetime],
    reminder_is_alarm: Optional[bool],
    reminder_timezone: Optional[str],
    rem_repo: Optional[BaseReminderRepository] = None,
) -> Optional[ReminderModel]:
    """Create or update a deduplicated task-linked reminder without confusing deadline vs trigger time."""
    if not reminder_mode or reminder_mode == "none":
        if reminder_at is None:
            return None
        reminder_mode = "custom"

    prefs = await load_user_notif_prefs(user)
    tz_name = reminder_timezone or prefs.timezone or "UTC"
    repo = rem_repo or get_reminder_repository(user_token=user.token)

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
    else:
        if not reminder_at:
            return None
        trig_utc = ensure_utc(reminder_at, tz_name)
        r_type = ReminderType.alarm if reminder_is_alarm else ReminderType.general
        dedupe = f"task:{task.id}:custom:{trig_utc.isoformat()}"

    is_alarm = bool(reminder_is_alarm)
    prio = ReminderPriority.alarm if is_alarm else (
        ReminderPriority.high if task.priority.value in ("urgent", "high") else ReminderPriority.normal
    )
    return await repo.create_reminder(
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


async def apply_task_create_reminder_sync(
    user: AuthenticatedUser,
    task_in: TaskCreate,
    created: TaskModel,
    rem_repo: Optional[BaseReminderRepository] = None,
) -> Optional[ReminderModel]:
    """Apply explicit or automatic due-date reminder scheduling after creating a task."""
    prefs = await load_user_notif_prefs(user)
    if task_in.reminder_mode == "none":
        return None
    if task_in.reminder_mode or task_in.reminder_at:
        return await sync_task_reminder(
            user=user,
            task=created,
            reminder_mode=task_in.reminder_mode,
            reminder_offset_minutes=task_in.reminder_offset_minutes,
            reminder_at=task_in.reminder_at,
            reminder_is_alarm=task_in.reminder_is_alarm,
            reminder_timezone=task_in.reminder_timezone,
            rem_repo=rem_repo,
        )
    if (
        prefs.auto_remind_new_tasks
        and created.due_date is not None
        and created.status not in (TaskStatus.completed, TaskStatus.cancelled)
    ):
        now_utc = datetime.now(timezone.utc)
        due_utc = ensure_utc(created.due_date, prefs.timezone or "UTC")
        if due_utc > now_utc:
            lead = max(0, int(prefs.task_default_lead_minutes))
            auto_mode = "before_due" if lead > 0 and (due_utc - timedelta(minutes=lead)) > now_utc else "at_due"
            return await sync_task_reminder(
                user=user,
                task=created,
                reminder_mode=auto_mode,
                reminder_offset_minutes=lead if auto_mode == "before_due" else None,
                reminder_at=None,
                reminder_is_alarm=(prefs.default_reminder_behavior == "alarm"),
                reminder_timezone=task_in.reminder_timezone or prefs.timezone,
                rem_repo=rem_repo,
            )
    return None


async def apply_task_update_reminder_sync(
    user: AuthenticatedUser,
    existing: TaskModel,
    updated: TaskModel,
    update_in: TaskUpdate,
    rem_repo: Optional[BaseReminderRepository] = None,
) -> None:
    """Suppress, reschedule, or create task-linked reminders when updating a task."""
    prefs = await load_user_notif_prefs(user)
    repo = rem_repo or get_reminder_repository(user_token=user.token)
    if updated.status in (TaskStatus.completed, TaskStatus.cancelled) and prefs.suppress_reminders_on_task_complete:
        await repo.suppress_task_reminders(user_id=user.id, task_id=updated.id)
        return

    if update_in.due_date is not None and update_in.due_date != existing.due_date and prefs.auto_reschedule_task_reminders:
        await repo.reschedule_task_reminders(
            user_id=user.id,
            task_id=updated.id,
            new_due_date=update_in.due_date,
            default_lead_minutes=prefs.task_default_lead_minutes,
        )

    if update_in.reminder_mode or update_in.reminder_at:
        await sync_task_reminder(
            user=user,
            task=updated,
            reminder_mode=update_in.reminder_mode,
            reminder_offset_minutes=update_in.reminder_offset_minutes,
            reminder_at=update_in.reminder_at,
            reminder_is_alarm=update_in.reminder_is_alarm,
            reminder_timezone=update_in.reminder_timezone,
            rem_repo=repo,
        )
    elif (
        existing.due_date is None
        and update_in.due_date is not None
        and update_in.reminder_mode is None
        and update_in.reminder_at is None
        and prefs.auto_remind_new_tasks
    ):
        now_utc = datetime.now(timezone.utc)
        due_utc = ensure_utc(update_in.due_date, prefs.timezone or "UTC")
        if due_utc > now_utc:
            lead = max(0, int(prefs.task_default_lead_minutes))
            auto_mode = "before_due" if lead > 0 and (due_utc - timedelta(minutes=lead)) > now_utc else "at_due"
            await sync_task_reminder(
                user=user,
                task=updated,
                reminder_mode=auto_mode,
                reminder_offset_minutes=lead if auto_mode == "before_due" else None,
                reminder_at=None,
                reminder_is_alarm=(prefs.default_reminder_behavior == "alarm"),
                reminder_timezone=update_in.reminder_timezone or prefs.timezone,
                rem_repo=repo,
            )

