"""Persistent Reminder Scheduler & Delivery Engine (SQLite + PostgreSQL Worker RPCs)."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

from app.core.config import Settings, settings as default_settings
from app.models.reminders import (
    DeliveryLogStatus,
    NotificationModel,
    NotificationPreferences,
    NotificationStatus,
    PushSubscriptionModel,
    RecurrenceRule,
    ReminderModel,
    ReminderPriority,
    ReminderSource,
    ReminderStatus,
    ReminderType,
)
from app.services.reminders.base_repository import BaseReminderRepository
from app.services.reminders.sqlite_repository import SQLiteReminderRepository
from app.services.reminders.time_utils import compute_next_occurrence, ensure_utc, format_local_datetime, is_within_quiet_hours
from app.services.reminders.web_push import WebPushService

logger = logging.getLogger(__name__)


def build_push_payload(
    reminder: ReminderModel,
    notification_id: Optional[UUID],
    prefs: NotificationPreferences,
) -> Dict[str, Any]:
    """Build privacy-aware Web Push payload respecting lock-screen privacy preferences."""
    action_url = "/reminders"
    if reminder.task_id:
        action_url = "/tasks"

    if prefs.hide_sensitive_lockscreen:
        title = "AUREN Alarm" if reminder.is_alarm else "AUREN Reminder"
        body = "You have a scheduled item due. Tap to open safely."
    else:
        local_time = format_local_datetime(reminder.trigger_at, reminder.timezone)
        is_alarm = bool(reminder.is_alarm or reminder.priority == ReminderPriority.alarm)
        title = f"Alarm: {reminder.title}" if is_alarm else reminder.title
        if reminder.description:
            body = f"{reminder.description} • {local_time}"
        elif reminder.task_id:
            body = f"Task due ({local_time}) — Tap Complete or open AUREN"
        elif reminder.recurrence_text:
            body = f"{reminder.recurrence_text} • {local_time}"
        else:
            body = f"Due {local_time} — Tap Complete or open AUREN"

    return {
        "title": title,
        "body": body,
        "tag": f"auren-rem-{reminder.id}",
        "is_alarm": bool(reminder.is_alarm or reminder.priority == ReminderPriority.alarm),
        "priority": reminder.priority.value,
        "reminder_id": str(reminder.id),
        "notification_id": str(notification_id) if notification_id else None,
        "task_id": str(reminder.task_id) if reminder.task_id else None,
        "url": action_url,
        "sound_key": reminder.sound_key or prefs.reminder_sound,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _compute_retry_backoff(attempt: int) -> timedelta:
    """Bounded exponential backoff: 60s, 120s, 240s, 480s, capped at 900s."""
    seconds = min(900, 60 * (2 ** max(0, attempt - 1)))
    return timedelta(seconds=seconds)


class ReminderProcessor:
    """Stateless-safe processor executing due-reminder delivery, deduplication, retries, & recurrence."""

    def __init__(
        self,
        push_service: Optional[WebPushService] = None,
        settings: Settings = default_settings,
    ):
        self.push_service = push_service or WebPushService(settings=settings)
        self.settings = settings

    async def process_sqlite_due_batch(
        self,
        repo: SQLiteReminderRepository,
        worker_id: str,
        batch_size: int = 20,
        lease_seconds: int = 120,
        now_utc: Optional[datetime] = None,
    ) -> int:
        now = ensure_utc(now_utc) if now_utc else datetime.now(timezone.utc)
        claimed = await repo.claim_due_reminders(
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            now_utc=now,
        )
        processed = 0
        for reminder in claimed:
            prefs = await self._load_user_prefs_sqlite(reminder.user_id)
            subs = await repo.list_push_subscriptions(reminder.user_id, active_only=True)
            await self.process_single_reminder(repo=repo, reminder=reminder, prefs=prefs, subscriptions=subs, now_utc=now)
            processed += 1
        return processed

    async def process_user_due_on_demand(
        self,
        user_id: UUID,
        repo: BaseReminderRepository,
        user_preferences_dict: Optional[Dict[str, Any]] = None,
        now_utc: Optional[datetime] = None,
    ) -> int:
        """Catch-up execution triggered on user API poll when running without direct DB worker pool."""
        now = ensure_utc(now_utc) if now_utc else datetime.now(timezone.utc)
        due_list = await repo.list_due_for_user(user_id=user_id, now_utc=now, limit=20)
        if not due_list:
            return 0
        prefs = NotificationPreferences.from_user_prefs(user_preferences_dict)
        subs = await repo.list_push_subscriptions(user_id, active_only=True)
        if subs and (not user_preferences_dict or "browser_push_enabled" not in user_preferences_dict):
            prefs.browser_push_enabled = True
        for reminder in due_list:
            await self.process_single_reminder(repo=repo, reminder=reminder, prefs=prefs, subscriptions=subs, now_utc=now)
        return len(due_list)

    async def _load_user_prefs_sqlite(self, user_id: UUID) -> NotificationPreferences:
        try:
            from app.services.profile_service import profile_service
            import sqlite3
            with sqlite3.connect(str(profile_service.db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT preferences FROM user_profiles WHERE id = ?", (str(user_id),)).fetchone()
                if row and row["preferences"]:
                    return NotificationPreferences.from_user_prefs(json.loads(row["preferences"]))
        except Exception as exc:
            logger.debug("Fallback default notification prefs for %s: %s", user_id, exc)
        return NotificationPreferences()

    async def process_single_reminder(
        self,
        repo: BaseReminderRepository,
        reminder: ReminderModel,
        prefs: NotificationPreferences,
        subscriptions: List[PushSubscriptionModel],
        now_utc: Optional[datetime] = None,
    ) -> Optional[NotificationModel]:
        now = ensure_utc(now_utc) if now_utc else datetime.now(timezone.utc)
        scheduled_ts = ensure_utc(reminder.snoozed_until or reminder.trigger_at)
        is_retry_pass = reminder.status == ReminderStatus.due and reminder.delivery_attempts > 0

        # Canonical deterministic occurrence key prevents duplicate notifications per firing cycle
        occurrence_key = f"rem:{reminder.id}:{scheduled_ts.isoformat()}:s{reminder.snooze_count}"
        in_quiet_hours = is_within_quiet_hours(now, prefs)
        is_critical_alarm = bool(reminder.is_alarm or reminder.priority == ReminderPriority.alarm)
        suppress_audible = in_quiet_hours and not (is_critical_alarm and prefs.quiet_hours_allow_alarms)
        missed_window = (now - scheduled_ts) > timedelta(minutes=5)

        action_url = "/tasks" if reminder.task_id else "/reminders"
        category = "alarm" if is_critical_alarm else ("task" if reminder.task_id else "reminder")

        # 1. Create deduplicated In-App Notification record
        notif_model: Optional[NotificationModel] = None
        if prefs.in_app_notifications_enabled:
            metadata = {
                "scheduled_at": scheduled_ts.isoformat(),
                "timezone": reminder.timezone,
                "missed_window": missed_window,
                "suppress_audio": suppress_audible,
                "quiet_hours_suppressed": suppress_audible,
                "sound_key": "silent" if suppress_audible else (reminder.sound_key or prefs.reminder_sound),
                "recurrence_text": reminder.recurrence_text,
            }
            notif_body = reminder.description or format_local_datetime(scheduled_ts, reminder.timezone)
            if missed_window:
                notif_body = f"Missed schedule ({format_local_datetime(scheduled_ts, reminder.timezone)})" + (
                    f" — {reminder.description}" if reminder.description else ""
                )

            notif_model, was_inserted = await repo.create_notification(
                user_id=reminder.user_id,
                title=reminder.title,
                body=notif_body,
                occurrence_key=occurrence_key,
                reminder_id=reminder.id,
                task_id=reminder.task_id,
                category=category,
                priority=reminder.priority.value,
                is_alarm=is_critical_alarm,
                action_url=action_url,
                delivery_channel="both" if (prefs.browser_push_enabled and subscriptions) else "in_app",
                status=NotificationStatus.unread,
                metadata=metadata,
                triggered_at=now,
            )
            if was_inserted:
                await repo.log_delivery(
                    user_id=reminder.user_id,
                    channel="in_app",
                    status=(
                        DeliveryLogStatus.suppressed_quiet_hours
                        if suppress_audible
                        else DeliveryLogStatus.sent
                    ),
                    reminder_id=reminder.id,
                    notification_id=notif_model.id,
                    attempt_number=reminder.delivery_attempts + 1,
                )
        elif not is_retry_pass:
            await repo.log_delivery(
                user_id=reminder.user_id,
                channel="in_app",
                status=DeliveryLogStatus.skipped_disabled,
                reminder_id=reminder.id,
                attempt_number=reminder.delivery_attempts + 1,
            )

        # 2. Dispatch Web Push notifications if permitted & outside quiet-hour suppression
        any_retryable_failure = False
        attempt_num = reminder.delivery_attempts + 1

        if subscriptions and not prefs.browser_push_enabled:
            await repo.log_delivery(
                user_id=reminder.user_id,
                channel="web_push",
                status=DeliveryLogStatus.skipped_disabled,
                reminder_id=reminder.id,
                notification_id=notif_model.id if notif_model else None,
                attempt_number=attempt_num,
                error_detail="Browser push disabled in user notification preferences",
            )
        elif prefs.browser_push_enabled and subscriptions:
            if suppress_audible:
                await repo.log_delivery(
                    user_id=reminder.user_id,
                    channel="web_push",
                    status=DeliveryLogStatus.suppressed_quiet_hours,
                    reminder_id=reminder.id,
                    notification_id=notif_model.id if notif_model else None,
                    attempt_number=attempt_num,
                    error_detail="Suppressed external push audio/banner during quiet hours",
                )
            elif not self.push_service.is_configured():
                await repo.log_delivery(
                    user_id=reminder.user_id,
                    channel="web_push",
                    status=DeliveryLogStatus.skipped_disabled,
                    reminder_id=reminder.id,
                    notification_id=notif_model.id if notif_model else None,
                    attempt_number=attempt_num,
                    error_detail="VAPID keys not configured",
                )
            else:
                push_payload = build_push_payload(
                    reminder=reminder,
                    notification_id=notif_model.id if notif_model else None,
                    prefs=prefs,
                )
                urgency = "low" if reminder.priority == ReminderPriority.low else "high"
                for sub in subscriptions:
                    res = await self.push_service.send_push(
                        endpoint=sub.endpoint,
                        p256dh=sub.p256dh,
                        auth_secret=sub.auth_secret,
                        payload=push_payload,
                        urgency=urgency,
                    )
                    if res.success:
                        await repo.update_push_subscription_health(
                            subscription_id=sub.id,
                            is_active=True,
                            failure_count=0,
                            last_error=None,
                            last_success_at=now,
                        )
                        await repo.log_delivery(
                            user_id=reminder.user_id,
                            channel="web_push",
                            status=DeliveryLogStatus.sent,
                            reminder_id=reminder.id,
                            notification_id=notif_model.id if notif_model else None,
                            subscription_id=sub.id,
                            attempt_number=attempt_num,
                            http_status=res.status_code,
                        )
                    elif res.expired_subscription:
                        # Automatically deactivate expired 404/410 endpoint
                        await repo.update_push_subscription_health(
                            subscription_id=sub.id,
                            is_active=False,
                            failure_count=sub.failure_count + 1,
                            last_error=res.error_detail,
                        )
                        await repo.log_delivery(
                            user_id=reminder.user_id,
                            channel="web_push",
                            status=DeliveryLogStatus.expired_subscription,
                            reminder_id=reminder.id,
                            notification_id=notif_model.id if notif_model else None,
                            subscription_id=sub.id,
                            attempt_number=attempt_num,
                            http_status=res.status_code,
                            error_detail=res.error_detail,
                        )
                    else:
                        new_fail_count = sub.failure_count + 1
                        still_active = new_fail_count < 10
                        await repo.update_push_subscription_health(
                            subscription_id=sub.id,
                            is_active=still_active,
                            failure_count=new_fail_count,
                            last_error=res.error_detail,
                        )
                        if res.retryable and attempt_num < reminder.max_delivery_attempts:
                            any_retryable_failure = True
                            log_status = DeliveryLogStatus.retrying
                        else:
                            log_status = DeliveryLogStatus.failed
                        await repo.log_delivery(
                            user_id=reminder.user_id,
                            channel="web_push",
                            status=log_status,
                            reminder_id=reminder.id,
                            notification_id=notif_model.id if notif_model else None,
                            subscription_id=sub.id,
                            attempt_number=attempt_num,
                            http_status=res.status_code,
                            error_detail=res.error_detail,
                        )

        # 3. Advance Recurring Rule or Finalize One-Time / Retry State
        if any_retryable_failure:
            next_retry = now + _compute_retry_backoff(attempt_num)
            await repo.finalize_reminder_trigger(
                reminder_id=reminder.id,
                new_status=ReminderStatus.due,
                next_trigger_at=None,
                last_triggered_at=now,
                delivery_attempts=attempt_num,
                next_retry_at=next_retry,
            )
        elif reminder.recurrence_rule and prefs.recurring_auto_advance:
            skip_missed = prefs.recurring_missed_policy != "preserve"
            next_occ = compute_next_occurrence(
                current_trigger_utc=scheduled_ts,
                rule=reminder.recurrence_rule,
                tz_name=reminder.timezone,
                now_utc=now,
                skip_missed=skip_missed,
            )
            if next_occ:
                await repo.finalize_reminder_trigger(
                    reminder_id=reminder.id,
                    new_status=ReminderStatus.scheduled,
                    next_trigger_at=next_occ,
                    last_triggered_at=now,
                    delivery_attempts=0,
                    next_retry_at=None,
                )
            else:
                await repo.finalize_reminder_trigger(
                    reminder_id=reminder.id,
                    new_status=ReminderStatus.due,
                    next_trigger_at=None,
                    last_triggered_at=now,
                    delivery_attempts=attempt_num,
                    next_retry_at=None,
                )
        else:
            await repo.finalize_reminder_trigger(
                reminder_id=reminder.id,
                new_status=ReminderStatus.due,
                next_trigger_at=None,
                last_triggered_at=now,
                delivery_attempts=attempt_num,
                next_retry_at=None,
            )

        return notif_model

    async def process_postgres_due_batch(
        self,
        db_pool: asyncpg.Pool,
        worker_id: str,
        batch_size: int = 20,
        lease_seconds: int = 120,
    ) -> int:
        """Process due reminders directly against PostgreSQL using fenced auren_worker RPCs."""
        now = datetime.now(timezone.utc)
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM public.claim_due_reminders_rpc($1, $2, $3)",
                worker_id,
                batch_size,
                lease_seconds,
            )
            if not rows:
                return 0

            processed = 0
            for r in rows:
                rec_rule = None
                if r["recurrence_rule"]:
                    raw_rule = r["recurrence_rule"]
                    rec_data = json.loads(raw_rule) if isinstance(raw_rule, str) else raw_rule
                    rec_rule = RecurrenceRule(**rec_data)

                reminder = ReminderModel(
                    id=r["id"],
                    user_id=r["user_id"],
                    task_id=r["task_id"],
                    project_id=r["project_id"],
                    goal_id=r["goal_id"],
                    title=r["title"],
                    description=r["description"],
                    reminder_type=ReminderType(r["reminder_type"]),
                    trigger_at=r["trigger_at"],
                    original_trigger_at=r["original_trigger_at"],
                    timezone=r["timezone"],
                    recurrence_rule=rec_rule,
                    recurrence_text=r["recurrence_text"],
                    status=ReminderStatus(r["status"]),
                    priority=ReminderPriority(r["priority"]),
                    is_alarm=bool(r["is_alarm"]),
                    sound_key=r["sound_key"],
                    snoozed_until=r["snoozed_until"],
                    snooze_count=r["snooze_count"],
                    last_triggered_at=r["last_triggered_at"],
                    next_retry_at=r["next_retry_at"],
                    delivery_attempts=r["delivery_attempts"],
                    max_delivery_attempts=r["max_delivery_attempts"],
                    escalation_count=r["escalation_count"],
                    completed_at=r["completed_at"],
                    cancelled_at=r["cancelled_at"],
                    source=ReminderSource(r["source"]),
                    dedupe_key=r["dedupe_key"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )

                # Load user preferences via worker RPC
                raw_prefs: Dict[str, Any] = {}
                try:
                    pref_val = await conn.fetchval(
                        "SELECT public.get_user_extraction_preferences_rpc($1, $2)",
                        reminder.user_id,
                        worker_id,
                    )
                    if isinstance(pref_val, str):
                        raw_prefs = json.loads(pref_val)
                    elif isinstance(pref_val, dict):
                        raw_prefs = pref_val
                except Exception as exc:
                    logger.debug("Postgres worker preference lookup fallback: %s", exc)

                prefs = NotificationPreferences.from_user_prefs(raw_prefs)
                sub_rows = await conn.fetch(
                    "SELECT * FROM public.get_user_push_subscriptions_rpc($1)", reminder.user_id
                )
                if sub_rows and "browser_push_enabled" not in raw_prefs:
                    prefs.browser_push_enabled = True
                subs = [
                    PushSubscriptionModel(
                        id=s["id"],
                        user_id=s["user_id"],
                        endpoint=s["endpoint"],
                        p256dh=s["p256dh"],
                        auth_secret=s["auth_secret"],
                        user_agent=s["user_agent"],
                        device_label=s["device_label"],
                        is_active=s["is_active"],
                        failure_count=s["failure_count"],
                        last_error=s["last_error"],
                        last_success_at=s["last_success_at"],
                        created_at=s["created_at"],
                        updated_at=s["updated_at"],
                    )
                    for s in sub_rows
                ]

                pg_adapter = _PostgresWorkerReminderAdapter(conn)
                await self.process_single_reminder(
                    repo=pg_adapter,
                    reminder=reminder,
                    prefs=prefs,
                    subscriptions=subs,
                    now_utc=now,
                )
                processed += 1
            return processed


class _PostgresWorkerReminderAdapter(BaseReminderRepository):
    """Minimal repository bridge executing worker-side RPC calls on an open asyncpg connection."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def create_notification(
        self,
        user_id: UUID,
        title: str,
        body: Optional[str],
        occurrence_key: str,
        reminder_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
        category: str = "reminder",
        priority: str = "normal",
        is_alarm: bool = False,
        action_url: str = "/reminders",
        delivery_channel: str = "in_app",
        status: NotificationStatus = NotificationStatus.unread,
        metadata: Optional[dict] = None,
        triggered_at: Optional[datetime] = None,
    ):
        row = await self.conn.fetchrow(
            """
            SELECT notification_id, inserted
            FROM public.record_worker_notification_rpc(
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb
            )
            """,
            user_id,
            reminder_id,
            task_id,
            title,
            body,
            category,
            priority,
            is_alarm,
            action_url,
            delivery_channel,
            status.value,
            occurrence_key,
            json.dumps(metadata or {}),
        )
        now_dt = triggered_at or datetime.now(timezone.utc)
        model = NotificationModel(
            id=row["notification_id"],
            user_id=user_id,
            reminder_id=reminder_id,
            task_id=task_id,
            title=title,
            body=body,
            category=category,
            priority=ReminderPriority(priority),
            is_alarm=is_alarm,
            action_url=action_url,
            delivery_channel=delivery_channel,  # type: ignore[arg-type]
            status=status,
            occurrence_key=occurrence_key,
            metadata=metadata or {},
            triggered_at=now_dt,
            created_at=now_dt,
        )
        return model, bool(row["inserted"])

    async def log_delivery(
        self,
        user_id: UUID,
        channel: str,
        status: DeliveryLogStatus,
        reminder_id: Optional[UUID] = None,
        notification_id: Optional[UUID] = None,
        subscription_id: Optional[UUID] = None,
        attempt_number: int = 1,
        http_status: Optional[int] = None,
        error_detail: Optional[str] = None,
    ):
        await self.conn.execute(
            "SELECT public.log_worker_delivery_rpc($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            user_id,
            reminder_id,
            notification_id,
            subscription_id,
            channel,
            status.value,
            attempt_number,
            http_status,
            error_detail,
        )
        return None  # type: ignore[return-value]

    async def update_push_subscription_health(
        self,
        subscription_id: UUID,
        is_active: bool,
        failure_count: int,
        last_error: Optional[str] = None,
        last_success_at: Optional[datetime] = None,
    ) -> None:
        await self.conn.execute(
            "SELECT public.update_push_subscription_health_rpc($1, $2, $3, $4, $5)",
            subscription_id,
            is_active,
            failure_count,
            last_error,
            last_success_at,
        )

    async def finalize_reminder_trigger(
        self,
        reminder_id: UUID,
        new_status: ReminderStatus,
        next_trigger_at: Optional[datetime],
        last_triggered_at: Optional[datetime],
        delivery_attempts: int,
        next_retry_at: Optional[datetime],
        escalation_count: Optional[int] = None,
    ) -> None:
        await self.conn.execute(
            "SELECT public.finalize_reminder_trigger_rpc($1, $2, $3, $4, $5, $6)",
            reminder_id,
            new_status.value,
            next_trigger_at,
            last_triggered_at,
            delivery_attempts,
            next_retry_at,
        )

    # Unused interface stubs on worker adapter
    async def create_reminder(self, *args, **kwargs): raise NotImplementedError
    async def get_reminder(self, *args, **kwargs): raise NotImplementedError
    async def list_reminders(self, *args, **kwargs): raise NotImplementedError
    async def update_reminder(self, *args, **kwargs): raise NotImplementedError
    async def delete_reminder(self, *args, **kwargs): raise NotImplementedError
    async def snooze_reminder(self, *args, **kwargs): raise NotImplementedError
    async def complete_reminder(self, *args, **kwargs): raise NotImplementedError
    async def cancel_reminder(self, *args, **kwargs): raise NotImplementedError
    async def find_active_by_dedupe_key(self, *args, **kwargs): raise NotImplementedError
    async def suppress_task_reminders(self, *args, **kwargs): raise NotImplementedError
    async def reschedule_task_reminders(self, *args, **kwargs): raise NotImplementedError
    async def list_notifications(self, *args, **kwargs): raise NotImplementedError
    async def update_notification_status(self, *args, **kwargs): raise NotImplementedError
    async def mark_all_notifications_read(self, *args, **kwargs): raise NotImplementedError
    async def list_delivery_logs(self, *args, **kwargs): raise NotImplementedError
    async def upsert_push_subscription(self, *args, **kwargs): raise NotImplementedError
    async def list_push_subscriptions(self, *args, **kwargs): raise NotImplementedError
    async def delete_push_subscription(self, *args, **kwargs): raise NotImplementedError
    async def list_due_for_user(self, *args, **kwargs): raise NotImplementedError


class ReminderScheduler:
    """Continuous asyncio scheduler loop processing due reminders safely in web/worker processes."""

    def __init__(
        self,
        sqlite_repo: Optional[SQLiteReminderRepository] = None,
        db_pool: Optional[asyncpg.Pool] = None,
        poll_interval: Optional[float] = None,
        settings: Settings = default_settings,
    ):
        self.settings = settings
        self.sqlite_repo = sqlite_repo
        self.db_pool = db_pool
        self.poll_interval = poll_interval or getattr(settings, "REMINDER_SCHEDULER_POLL_INTERVAL_SECONDS", 5.0)
        self.batch_size = getattr(settings, "REMINDER_SCHEDULER_BATCH_SIZE", 20)
        self.lease_seconds = getattr(settings, "REMINDER_SCHEDULER_LEASE_SECONDS", 120)
        self.processor = ReminderProcessor(settings=settings)
        self.worker_id = f"rem_sched_{id(self)}"
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    async def run_once(self) -> int:
        if self.db_pool is not None:
            return await self.processor.process_postgres_due_batch(
                db_pool=self.db_pool,
                worker_id=self.worker_id,
                batch_size=self.batch_size,
                lease_seconds=self.lease_seconds,
            )
        if self.sqlite_repo is not None:
            return await self.processor.process_sqlite_due_batch(
                repo=self.sqlite_repo,
                worker_id=self.worker_id,
                batch_size=self.batch_size,
                lease_seconds=self.lease_seconds,
            )
        return 0

    async def run(self) -> None:
        logger.info("ReminderScheduler started [worker_id=%s, interval=%.1fs]", self.worker_id, self.poll_interval)
        while not self._stop_event.is_set():
            try:
                count = await self.run_once()
                if count > 0:
                    logger.info("ReminderScheduler processed %d due reminders.", count)
            except Exception as exc:
                logger.warning("ReminderScheduler cycle error: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass
        logger.info("ReminderScheduler stopped cleanly.")

