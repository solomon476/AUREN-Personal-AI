"""Domain models, enums, preferences, and API schemas for AUREN Smart Reminders & Notifications."""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


HH_MM_REGEX = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ReminderType(str, Enum):
    general = "general"
    task_before_due = "task_before_due"
    task_due = "task_due"
    task_overdue = "task_overdue"
    briefing = "briefing"
    review = "review"
    alarm = "alarm"
    appointment = "appointment"
    goal = "goal"


class ReminderStatus(str, Enum):
    scheduled = "scheduled"
    due = "due"
    snoozed = "snoozed"
    completed = "completed"
    cancelled = "cancelled"
    missed = "missed"


class ReminderPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    alarm = "alarm"


class ReminderSource(str, Enum):
    manual = "manual"
    chat = "chat"
    task_sync = "task_sync"
    system_briefing = "system_briefing"


class RecurrenceFrequency(str, Enum):
    daily = "daily"
    weekdays = "weekdays"
    weekly = "weekly"
    monthly = "monthly"
    interval_minutes = "interval_minutes"
    interval_hours = "interval_hours"
    interval_days = "interval_days"


class NotificationStatus(str, Enum):
    unread = "unread"
    read = "read"
    dismissed = "dismissed"
    acted = "acted"
    suppressed_quiet_hours = "suppressed_quiet_hours"


class DeliveryChannel(str, Enum):
    in_app = "in_app"
    web_push = "web_push"
    both = "both"


class DeliveryLogStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    retrying = "retrying"
    failed = "failed"
    expired_subscription = "expired_subscription"
    suppressed_quiet_hours = "suppressed_quiet_hours"
    skipped_disabled = "skipped_disabled"


class RecurrenceRule(BaseModel):
    """Structured recurrence specification for recurring reminders."""

    frequency: RecurrenceFrequency
    interval: int = Field(default=1, ge=1, le=365)
    days_of_week: Optional[List[int]] = Field(
        default=None,
        description="0=Monday .. 6=Sunday (Python weekday convention)",
    )
    day_of_month: Optional[int] = Field(default=None, ge=1, le=31)
    time_of_day: Optional[str] = Field(default=None, description="Local wall-clock time HH:MM (24h)")
    end_at: Optional[datetime] = None

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return None
        cleaned = sorted(set(v))
        for d in cleaned:
            if d < 0 or d > 6:
                raise ValueError("days_of_week values must be integers between 0 (Mon) and 6 (Sun).")
        return cleaned

    @field_validator("time_of_day")
    @classmethod
    def validate_time_of_day(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if not HH_MM_REGEX.match(s):
            raise ValueError("time_of_day must be formatted as HH:MM (24-hour clock).")
        return s


class NotificationPreferences(BaseModel):
    """Typed view of reminder/notification preferences stored in user profiles.preferences."""

    in_app_notifications_enabled: bool = True
    browser_push_enabled: bool = False
    audible_alerts_enabled: bool = True
    reminder_sound: str = "chime"
    default_reminder_behavior: str = "notification"  # 'notification' | 'alarm' | 'silent'
    default_snooze_minutes: int = Field(default=10, ge=1, le=1440)
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    quiet_hours_allow_alarms: bool = False
    timezone: str = "UTC"
    daily_briefing_enabled: bool = False
    daily_briefing_time: str = "08:00"
    evening_review_enabled: bool = False
    evening_review_time: str = "19:00"
    notification_priority_default: ReminderPriority = ReminderPriority.normal
    recurring_auto_advance: bool = True
    recurring_missed_policy: str = "trigger_once_then_advance"  # 'trigger_once_then_advance' | 'skip_missed'
    task_default_lead_minutes: int = Field(default=30, ge=0, le=10080)
    auto_remind_new_tasks: bool = True
    overdue_task_reminders_enabled: bool = False
    auto_reschedule_task_reminders: bool = True
    suppress_reminders_on_task_complete: bool = True
    max_escalation_count: int = Field(default=2, ge=0, le=5)
    escalation_interval_minutes: int = Field(default=15, ge=5, le=180)
    hide_sensitive_lockscreen: bool = False

    @classmethod
    def from_user_prefs(cls, raw_prefs: Optional[Dict[str, Any]]) -> "NotificationPreferences":
        if not raw_prefs or not isinstance(raw_prefs, dict):
            return cls()
        allowed_keys = set(cls.model_fields.keys())
        filtered: Dict[str, Any] = {}
        for k in allowed_keys:
            if k in raw_prefs and raw_prefs[k] is not None:
                filtered[k] = raw_prefs[k]
        # Validate timezone gracefully
        tz = filtered.get("timezone")
        if tz:
            try:
                ZoneInfo(str(tz))
            except (ZoneInfoNotFoundError, Exception):
                filtered["timezone"] = "UTC"
        try:
            return cls(**filtered)
        except Exception:
            return cls()


def _validate_tz_str(tz_val: str) -> str:
    cleaned = (tz_val or "UTC").strip()
    try:
        ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, Exception) as exc:
        raise ValueError(f"Invalid IANA timezone '{tz_val}'.") from exc
    return cleaned


class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    reminder_type: ReminderType = ReminderType.general
    trigger_at: datetime
    timezone: str = "UTC"
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_text: Optional[str] = Field(default=None, max_length=255)
    priority: ReminderPriority = ReminderPriority.normal
    is_alarm: bool = False
    sound_key: Optional[str] = Field(default=None, max_length=64)
    task_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    goal_id: Optional[UUID] = None
    source: ReminderSource = ReminderSource.manual
    dedupe_key: Optional[str] = Field(default=None, max_length=255)
    max_delivery_attempts: int = Field(default=5, ge=1, le=20)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Reminder title cannot be empty.")
        return s

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: str) -> str:
        return _validate_tz_str(v)


class ReminderUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    reminder_type: Optional[ReminderType] = None
    trigger_at: Optional[datetime] = None
    timezone: Optional[str] = None
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_text: Optional[str] = Field(default=None, max_length=255)
    status: Optional[ReminderStatus] = None
    priority: Optional[ReminderPriority] = None
    is_alarm: Optional[bool] = None
    sound_key: Optional[str] = Field(default=None, max_length=64)
    task_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    goal_id: Optional[UUID] = None
    clear_recurrence: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Reminder title cannot be empty.")
            return s
        return v

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_tz_str(v)
        return v


class ReminderSnoozeRequest(BaseModel):
    snooze_minutes: int = Field(default=10, ge=1, le=10080)


class ReminderRescheduleRequest(BaseModel):
    trigger_at: datetime
    timezone: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_tz_str(v)
        return v


class ReminderModel(BaseModel):
    id: UUID
    user_id: UUID
    task_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    goal_id: Optional[UUID] = None
    task_title: Optional[str] = None
    project_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    reminder_type: ReminderType = ReminderType.general
    trigger_at: datetime
    original_trigger_at: datetime
    timezone: str = "UTC"
    recurrence_rule: Optional[RecurrenceRule] = None
    recurrence_text: Optional[str] = None
    status: ReminderStatus = ReminderStatus.scheduled
    priority: ReminderPriority = ReminderPriority.normal
    is_alarm: bool = False
    sound_key: Optional[str] = None
    snoozed_until: Optional[datetime] = None
    snooze_count: int = 0
    last_triggered_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    delivery_attempts: int = 0
    max_delivery_attempts: int = 5
    escalation_count: int = 0
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    source: ReminderSource = ReminderSource.manual
    dedupe_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ReminderListResponse(BaseModel):
    items: List[ReminderModel]
    total: int
    page: int
    page_size: int


class NotificationModel(BaseModel):
    id: UUID
    user_id: UUID
    reminder_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    title: str
    body: Optional[str] = None
    category: str = "reminder"
    priority: ReminderPriority = ReminderPriority.normal
    is_alarm: bool = False
    action_url: str = "/reminders"
    delivery_channel: DeliveryChannel = DeliveryChannel.in_app
    status: NotificationStatus = NotificationStatus.unread
    occurrence_key: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    triggered_at: datetime
    read_at: Optional[datetime] = None
    acted_at: Optional[datetime] = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: List[NotificationModel]
    total: int
    unread_count: int
    due_alerts: List[NotificationModel] = Field(default_factory=list)


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(..., min_length=16, max_length=512)
    auth: str = Field(..., min_length=8, max_length=256)


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2048)
    keys: PushSubscriptionKeys
    user_agent: Optional[str] = Field(default=None, max_length=512)
    device_label: Optional[str] = Field(default=None, max_length=120)

    @field_validator("endpoint")
    @classmethod
    def validate_https_endpoint(cls, v: str) -> str:
        s = v.strip()
        if not (s.startswith("https://") or s.startswith("http://localhost")):
            raise ValueError("Push subscription endpoint must use HTTPS.")
        return s


class PushSubscriptionModel(BaseModel):
    id: UUID
    user_id: UUID
    endpoint: str
    p256dh: str
    auth_secret: str
    user_agent: Optional[str] = None
    device_label: Optional[str] = None
    is_active: bool = True
    failure_count: int = 0
    last_error: Optional[str] = None
    last_success_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PushSubscriptionPublicView(BaseModel):
    """Client-safe subscription view omitting cryptographic auth_secret."""

    id: UUID
    endpoint: str
    device_label: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True
    failure_count: int = 0
    last_error: Optional[str] = None
    last_success_at: Optional[datetime] = None
    created_at: datetime


class PushSubscriptionListResponse(BaseModel):
    items: List[PushSubscriptionPublicView]
    total: int


class DeliveryLogModel(BaseModel):
    id: UUID
    user_id: UUID
    reminder_id: Optional[UUID] = None
    notification_id: Optional[UUID] = None
    subscription_id: Optional[UUID] = None
    channel: str
    status: DeliveryLogStatus
    attempt_number: int = 1
    http_status: Optional[int] = None
    error_detail: Optional[str] = None
    created_at: datetime


class VapidPublicKeyResponse(BaseModel):
    configured: bool
    public_key: Optional[str] = None
    subject: str

