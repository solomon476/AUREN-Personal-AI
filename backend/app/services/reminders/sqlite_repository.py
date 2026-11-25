"""SQLite repository for AUREN Smart Reminders, Notifications, Push Subscriptions & Delivery Logs."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.models.reminders import (
    DeliveryLogModel,
    DeliveryLogStatus,
    NotificationModel,
    NotificationStatus,
    PushSubscriptionCreate,
    PushSubscriptionModel,
    RecurrenceRule,
    ReminderCreate,
    ReminderModel,
    ReminderPriority,
    ReminderSource,
    ReminderStatus,
    ReminderType,
    ReminderUpdate,
    DeliveryChannel,
)
from app.services.reminders.base_repository import BaseReminderRepository
from app.services.reminders.time_utils import ensure_utc

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_REMINDERS_DB_PATH = DB_DIR / "auren_reminders.db"


class SQLiteReminderRepository(BaseReminderRepository):
    """Thread-safe disk-backed SQLite repository for local dev and automated tests."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_REMINDERS_DB_PATH
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_database(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    task_id TEXT,
                    project_id TEXT,
                    goal_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    reminder_type TEXT NOT NULL DEFAULT 'general',
                    trigger_at TEXT NOT NULL,
                    original_trigger_at TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    recurrence_rule TEXT,
                    recurrence_text TEXT,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    is_alarm INTEGER NOT NULL DEFAULT 0,
                    sound_key TEXT,
                    snoozed_until TEXT,
                    snooze_count INTEGER NOT NULL DEFAULT 0,
                    last_triggered_at TEXT,
                    next_retry_at TEXT,
                    delivery_attempts INTEGER NOT NULL DEFAULT 0,
                    max_delivery_attempts INTEGER NOT NULL DEFAULT 5,
                    escalation_count INTEGER NOT NULL DEFAULT 0,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    source TEXT NOT NULL DEFAULT 'manual',
                    dedupe_key TEXT,
                    claimed_by TEXT,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_reminders_user_status_trigger
                    ON reminders(user_id, status, trigger_at ASC);
                CREATE INDEX IF NOT EXISTS idx_reminders_task
                    ON reminders(task_id);
                CREATE UNIQUE INDEX IF NOT EXISTS uq_reminders_active_dedupe
                    ON reminders(user_id, dedupe_key)
                    WHERE dedupe_key IS NOT NULL AND status IN ('scheduled', 'due', 'snoozed');

                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    reminder_id TEXT,
                    task_id TEXT,
                    title TEXT NOT NULL,
                    body TEXT,
                    category TEXT NOT NULL DEFAULT 'reminder',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    is_alarm INTEGER NOT NULL DEFAULT 0,
                    action_url TEXT NOT NULL DEFAULT '/reminders',
                    delivery_channel TEXT NOT NULL DEFAULT 'in_app',
                    status TEXT NOT NULL DEFAULT 'unread',
                    occurrence_key TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    triggered_at TEXT NOT NULL,
                    read_at TEXT,
                    acted_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, occurrence_key)
                );

                CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
                    ON notifications(user_id, status, triggered_at DESC);

                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth_secret TEXT NOT NULL,
                    user_agent TEXT,
                    device_label TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    last_success_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, endpoint)
                );

                CREATE TABLE IF NOT EXISTS notification_delivery_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    reminder_id TEXT,
                    notification_id TEXT,
                    subscription_id TEXT,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL DEFAULT 1,
                    http_status INTEGER,
                    error_detail TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_delivery_logs_reminder
                    ON notification_delivery_logs(reminder_id, created_at DESC);
                """
            )

    # ------------------------------------------------------------------
    # Row Mappers
    # ------------------------------------------------------------------
    def _row_to_reminder(self, row: sqlite3.Row) -> ReminderModel:
        rec_raw = row["recurrence_rule"]
        rec_rule = None
        if rec_raw:
            try:
                rec_data = json.loads(rec_raw) if isinstance(rec_raw, str) else rec_raw
                rec_rule = RecurrenceRule(**rec_data)
            except Exception:
                rec_rule = None

        return ReminderModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            task_id=UUID(row["task_id"]) if row["task_id"] else None,
            project_id=UUID(row["project_id"]) if row["project_id"] else None,
            goal_id=UUID(row["goal_id"]) if row["goal_id"] else None,
            title=row["title"],
            description=row["description"],
            reminder_type=ReminderType(row["reminder_type"]),
            trigger_at=datetime.fromisoformat(row["trigger_at"]),
            original_trigger_at=datetime.fromisoformat(row["original_trigger_at"]),
            timezone=row["timezone"] or "UTC",
            recurrence_rule=rec_rule,
            recurrence_text=row["recurrence_text"],
            status=ReminderStatus(row["status"]),
            priority=ReminderPriority(row["priority"]),
            is_alarm=bool(row["is_alarm"]),
            sound_key=row["sound_key"],
            snoozed_until=datetime.fromisoformat(row["snoozed_until"]) if row["snoozed_until"] else None,
            snooze_count=int(row["snooze_count"] or 0),
            last_triggered_at=datetime.fromisoformat(row["last_triggered_at"]) if row["last_triggered_at"] else None,
            next_retry_at=datetime.fromisoformat(row["next_retry_at"]) if row["next_retry_at"] else None,
            delivery_attempts=int(row["delivery_attempts"] or 0),
            max_delivery_attempts=int(row["max_delivery_attempts"] or 5),
            escalation_count=int(row["escalation_count"] or 0),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            cancelled_at=datetime.fromisoformat(row["cancelled_at"]) if row["cancelled_at"] else None,
            source=ReminderSource(row["source"]),
            dedupe_key=row["dedupe_key"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_notification(self, row: sqlite3.Row) -> NotificationModel:
        meta_raw = row["metadata"]
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
        except Exception:
            meta = {}
        return NotificationModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            reminder_id=UUID(row["reminder_id"]) if row["reminder_id"] else None,
            task_id=UUID(row["task_id"]) if row["task_id"] else None,
            title=row["title"],
            body=row["body"],
            category=row["category"],
            priority=ReminderPriority(row["priority"]),
            is_alarm=bool(row["is_alarm"]),
            action_url=row["action_url"] or "/reminders",
            delivery_channel=DeliveryChannel(row["delivery_channel"]),
            status=NotificationStatus(row["status"]),
            occurrence_key=row["occurrence_key"],
            metadata=meta,
            triggered_at=datetime.fromisoformat(row["triggered_at"]),
            read_at=datetime.fromisoformat(row["read_at"]) if row["read_at"] else None,
            acted_at=datetime.fromisoformat(row["acted_at"]) if row["acted_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_subscription(self, row: sqlite3.Row) -> PushSubscriptionModel:
        return PushSubscriptionModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            endpoint=row["endpoint"],
            p256dh=row["p256dh"],
            auth_secret=row["auth_secret"],
            user_agent=row["user_agent"],
            device_label=row["device_label"],
            is_active=bool(row["is_active"]),
            failure_count=int(row["failure_count"] or 0),
            last_error=row["last_error"],
            last_success_at=datetime.fromisoformat(row["last_success_at"]) if row["last_success_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_delivery_log(self, row: sqlite3.Row) -> DeliveryLogModel:
        return DeliveryLogModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            reminder_id=UUID(row["reminder_id"]) if row["reminder_id"] else None,
            notification_id=UUID(row["notification_id"]) if row["notification_id"] else None,
            subscription_id=UUID(row["subscription_id"]) if row["subscription_id"] else None,
            channel=row["channel"],
            status=DeliveryLogStatus(row["status"]),
            attempt_number=int(row["attempt_number"] or 1),
            http_status=row["http_status"],
            error_detail=row["error_detail"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ------------------------------------------------------------------
    # Reminders CRUD
    # ------------------------------------------------------------------
    def _sync_create_reminder(self, user_id: UUID, reminder: ReminderCreate) -> ReminderModel:
        u_id = str(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        trigger_utc = ensure_utc(reminder.trigger_at, reminder.timezone).isoformat()
        rec_json = json.dumps(reminder.recurrence_rule.model_dump(mode="json")) if reminder.recurrence_rule else None

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            # Prevent duplicate active reminders with matching dedupe_key
            if reminder.dedupe_key:
                existing = conn.execute(
                    """
                    SELECT * FROM reminders
                    WHERE user_id = ? AND dedupe_key = ? AND status IN ('scheduled', 'due', 'snoozed')
                    """,
                    (u_id, reminder.dedupe_key),
                ).fetchone()
                if existing:
                    conn.commit()
                    return self._row_to_reminder(existing)

            rem_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO reminders (
                    id, user_id, task_id, project_id, goal_id, title, description,
                    reminder_type, trigger_at, original_trigger_at, timezone,
                    recurrence_rule, recurrence_text, status, priority, is_alarm,
                    sound_key, max_delivery_attempts, source, dedupe_key,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rem_id,
                    u_id,
                    str(reminder.task_id) if reminder.task_id else None,
                    str(reminder.project_id) if reminder.project_id else None,
                    str(reminder.goal_id) if reminder.goal_id else None,
                    reminder.title,
                    reminder.description,
                    reminder.reminder_type.value,
                    trigger_utc,
                    trigger_utc,
                    reminder.timezone,
                    rec_json,
                    reminder.recurrence_text,
                    reminder.priority.value,
                    1 if (reminder.is_alarm or reminder.priority == ReminderPriority.alarm) else 0,
                    reminder.sound_key,
                    reminder.max_delivery_attempts,
                    reminder.source.value,
                    reminder.dedupe_key,
                    now_iso,
                    now_iso,
                ),
            )
            row = conn.execute("SELECT * FROM reminders WHERE id = ?", (rem_id,)).fetchone()
            conn.commit()
            return self._row_to_reminder(row)

    async def create_reminder(self, user_id: UUID, reminder: ReminderCreate) -> ReminderModel:
        return await asyncio.to_thread(self._sync_create_reminder, user_id, reminder)

    def _sync_get_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
                (str(reminder_id), str(user_id)),
            ).fetchone()
            return self._row_to_reminder(row) if row else None

    async def get_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        return await asyncio.to_thread(self._sync_get_reminder, user_id, reminder_id)

    def _sync_list_reminders(
        self,
        user_id: UUID,
        status: Optional[str],
        recurring_only: bool,
        task_id: Optional[UUID],
        query: Optional[str],
        page: int,
        page_size: int,
    ) -> Tuple[List[ReminderModel], int]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        conds = ["user_id = ?"]
        params: List[Any] = [str(user_id)]

        if status and status != "all":
            if status == "upcoming":
                conds.append("status = 'scheduled'")
            elif status == "due":
                conds.append("status IN ('due', 'snoozed')")
            elif status == "history":
                conds.append("status IN ('completed', 'cancelled', 'missed')")
            else:
                conds.append("status = ?")
                params.append(status)

        if recurring_only:
            conds.append("recurrence_rule IS NOT NULL")

        if task_id:
            conds.append("task_id = ?")
            params.append(str(task_id))

        if query:
            conds.append("(title LIKE ? OR description LIKE ?)")
            q = f"%{query.strip()}%"
            params.extend([q, q])

        where_sql = " AND ".join(conds)
        with self._get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM reminders WHERE {where_sql}", params).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT * FROM reminders
                WHERE {where_sql}
                ORDER BY
                    CASE status
                        WHEN 'due' THEN 0
                        WHEN 'snoozed' THEN 1
                        WHEN 'scheduled' THEN 2
                        WHEN 'missed' THEN 3
                        WHEN 'completed' THEN 4
                        ELSE 5
                    END,
                    trigger_at ASC
                LIMIT ? OFFSET ?
                """,
                params + [page_size, offset],
            ).fetchall()
            return [self._row_to_reminder(r) for r in rows], total

    async def list_reminders(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        recurring_only: bool = False,
        task_id: Optional[UUID] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[ReminderModel], int]:
        return await asyncio.to_thread(
            self._sync_list_reminders, user_id, status, recurring_only, task_id, query, page, page_size
        )

    def _sync_update_reminder(
        self, user_id: UUID, reminder_id: UUID, update: ReminderUpdate
    ) -> Optional[ReminderModel]:
        u_id = str(user_id)
        r_id = str(reminder_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM reminders WHERE id = ? AND user_id = ?", (r_id, u_id)
            ).fetchone()
            if not existing:
                return None

            sets = ["updated_at = ?"]
            params: List[Any] = [now_iso]
            tz_name = update.timezone or existing["timezone"] or "UTC"

            if update.title is not None:
                sets.append("title = ?")
                params.append(update.title)
            if update.description is not None:
                sets.append("description = ?")
                params.append(update.description)
            if update.reminder_type is not None:
                sets.append("reminder_type = ?")
                params.append(update.reminder_type.value)
            if update.timezone is not None:
                sets.append("timezone = ?")
                params.append(update.timezone)
            if update.trigger_at is not None:
                trig_utc = ensure_utc(update.trigger_at, tz_name).isoformat()
                sets.extend(["trigger_at = ?", "snoozed_until = NULL", "next_retry_at = NULL", "claimed_by = NULL", "lease_expires_at = NULL"])
                params.append(trig_utc)
                if update.status is None and existing["status"] in ("due", "snoozed", "missed", "completed", "cancelled"):
                    sets.append("status = 'scheduled'")
            if update.clear_recurrence:
                sets.extend(["recurrence_rule = NULL", "recurrence_text = NULL"])
            elif update.recurrence_rule is not None:
                sets.append("recurrence_rule = ?")
                params.append(json.dumps(update.recurrence_rule.model_dump(mode="json")))
            if update.recurrence_text is not None and not update.clear_recurrence:
                sets.append("recurrence_text = ?")
                params.append(update.recurrence_text)
            if update.priority is not None:
                sets.append("priority = ?")
                params.append(update.priority.value)
            if update.is_alarm is not None:
                sets.append("is_alarm = ?")
                params.append(1 if update.is_alarm else 0)
            if update.sound_key is not None:
                sets.append("sound_key = ?")
                params.append(update.sound_key)
            if update.task_id is not None:
                sets.append("task_id = ?")
                params.append(str(update.task_id))
            if update.project_id is not None:
                sets.append("project_id = ?")
                params.append(str(update.project_id))
            if update.goal_id is not None:
                sets.append("goal_id = ?")
                params.append(str(update.goal_id))
            if update.status is not None:
                sets.append("status = ?")
                params.append(update.status.value)
                if update.status == ReminderStatus.completed:
                    sets.append("completed_at = ?")
                    params.append(now_iso)
                elif update.status == ReminderStatus.cancelled:
                    sets.append("cancelled_at = ?")
                    params.append(now_iso)

            params.extend([r_id, u_id])
            conn.execute(f"UPDATE reminders SET {', '.join(sets)} WHERE id = ? AND user_id = ?", params)
            row = conn.execute("SELECT * FROM reminders WHERE id = ? AND user_id = ?", (r_id, u_id)).fetchone()
            conn.commit()
            return self._row_to_reminder(row)

    async def update_reminder(
        self, user_id: UUID, reminder_id: UUID, update: ReminderUpdate
    ) -> Optional[ReminderModel]:
        return await asyncio.to_thread(self._sync_update_reminder, user_id, reminder_id, update)

    def _sync_delete_reminder(self, user_id: UUID, reminder_id: UUID) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                (str(reminder_id), str(user_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    async def delete_reminder(self, user_id: UUID, reminder_id: UUID) -> bool:
        return await asyncio.to_thread(self._sync_delete_reminder, user_id, reminder_id)

    def _sync_snooze(self, user_id: UUID, reminder_id: UUID, snoozed_until: datetime) -> Optional[ReminderModel]:
        now_iso = datetime.now(timezone.utc).isoformat()
        snooze_iso = ensure_utc(snoozed_until).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE reminders
                SET status = 'snoozed',
                    trigger_at = ?,
                    snoozed_until = ?,
                    snooze_count = snooze_count + 1,
                    next_retry_at = NULL,
                    claimed_by = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (snooze_iso, snooze_iso, now_iso, str(reminder_id), str(user_id)),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ? AND user_id = ?", (str(reminder_id), str(user_id))
            ).fetchone()
            conn.commit()
            return self._row_to_reminder(row)

    async def snooze_reminder(
        self, user_id: UUID, reminder_id: UUID, snoozed_until: datetime
    ) -> Optional[ReminderModel]:
        return await asyncio.to_thread(self._sync_snooze, user_id, reminder_id, snoozed_until)

    def _sync_mark_status(
        self, user_id: UUID, reminder_id: UUID, target_status: ReminderStatus
    ) -> Optional[ReminderModel]:
        now_iso = datetime.now(timezone.utc).isoformat()
        extra_col = "completed_at = ?" if target_status == ReminderStatus.completed else "cancelled_at = ?"
        with self._get_connection() as conn:
            cur = conn.execute(
                f"""
                UPDATE reminders
                SET status = ?,
                    {extra_col},
                    snoozed_until = NULL,
                    next_retry_at = NULL,
                    claimed_by = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (target_status.value, now_iso, now_iso, str(reminder_id), str(user_id)),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ? AND user_id = ?", (str(reminder_id), str(user_id))
            ).fetchone()
            conn.commit()
            return self._row_to_reminder(row)

    async def complete_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        return await asyncio.to_thread(self._sync_mark_status, user_id, reminder_id, ReminderStatus.completed)

    async def cancel_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        return await asyncio.to_thread(self._sync_mark_status, user_id, reminder_id, ReminderStatus.cancelled)

    # ------------------------------------------------------------------
    # Task Integration Helpers
    # ------------------------------------------------------------------
    def _sync_find_active_by_dedupe(self, user_id: UUID, dedupe_key: str) -> Optional[ReminderModel]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM reminders
                WHERE user_id = ? AND dedupe_key = ? AND status IN ('scheduled', 'due', 'snoozed')
                """,
                (str(user_id), dedupe_key),
            ).fetchone()
            return self._row_to_reminder(row) if row else None

    async def find_active_by_dedupe_key(self, user_id: UUID, dedupe_key: str) -> Optional[ReminderModel]:
        return await asyncio.to_thread(self._sync_find_active_by_dedupe, user_id, dedupe_key)

    def _sync_suppress_task_reminders(self, user_id: UUID, task_id: UUID) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE reminders
                SET status = 'cancelled',
                    cancelled_at = ?,
                    next_retry_at = NULL,
                    claimed_by = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE user_id = ? AND task_id = ? AND status IN ('scheduled', 'due', 'snoozed')
                """,
                (now_iso, now_iso, str(user_id), str(task_id)),
            )
            conn.commit()
            return cur.rowcount

    async def suppress_task_reminders(self, user_id: UUID, task_id: UUID) -> int:
        return await asyncio.to_thread(self._sync_suppress_task_reminders, user_id, task_id)

    def _sync_reschedule_task_reminders(
        self,
        user_id: UUID,
        task_id: UUID,
        new_due_date: datetime,
        default_lead_minutes: int,
    ) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        due_utc = ensure_utc(new_due_date)
        updated = 0
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE user_id = ? AND task_id = ? AND status IN ('scheduled', 'snoozed')
                """,
                (str(user_id), str(task_id)),
            ).fetchall()
            for r in rows:
                rtype = r["reminder_type"]
                if rtype == ReminderType.task_due.value:
                    target_utc = due_utc.isoformat()
                elif rtype == ReminderType.task_before_due.value:
                    target_utc = (due_utc - timedelta(minutes=max(0, default_lead_minutes))).isoformat()
                else:
                    continue
                conn.execute(
                    """
                    UPDATE reminders
                    SET trigger_at = ?, original_trigger_at = ?, status = 'scheduled',
                        snoozed_until = NULL, next_retry_at = NULL, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (target_utc, target_utc, now_iso, r["id"], str(user_id)),
                )
                updated += 1
            conn.commit()
        return updated

    async def reschedule_task_reminders(
        self,
        user_id: UUID,
        task_id: UUID,
        new_due_date: datetime,
        default_lead_minutes: int = 30,
    ) -> int:
        return await asyncio.to_thread(
            self._sync_reschedule_task_reminders, user_id, task_id, new_due_date, default_lead_minutes
        )

    # ------------------------------------------------------------------
    # Notifications & Delivery Logs
    # ------------------------------------------------------------------
    def _sync_create_notification(
        self,
        user_id: UUID,
        title: str,
        body: Optional[str],
        occurrence_key: str,
        reminder_id: Optional[UUID],
        task_id: Optional[UUID],
        category: str,
        priority: str,
        is_alarm: bool,
        action_url: str,
        delivery_channel: str,
        status: NotificationStatus,
        metadata: Optional[dict],
        triggered_at: Optional[datetime],
    ) -> Tuple[NotificationModel, bool]:
        u_id = str(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        trig_iso = ensure_utc(triggered_at).isoformat() if triggered_at else now_iso

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute(
                "SELECT * FROM notifications WHERE user_id = ? AND occurrence_key = ?",
                (u_id, occurrence_key),
            ).fetchone()
            if existing:
                conn.commit()
                return self._row_to_notification(existing), False

            notif_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO notifications (
                    id, user_id, reminder_id, task_id, title, body, category,
                    priority, is_alarm, action_url, delivery_channel, status,
                    occurrence_key, metadata, triggered_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notif_id,
                    u_id,
                    str(reminder_id) if reminder_id else None,
                    str(task_id) if task_id else None,
                    title,
                    body,
                    category,
                    priority,
                    1 if is_alarm else 0,
                    action_url,
                    delivery_channel,
                    status.value,
                    occurrence_key,
                    json.dumps(metadata or {}),
                    trig_iso,
                    now_iso,
                ),
            )
            row = conn.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,)).fetchone()
            conn.commit()
            return self._row_to_notification(row), True

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
    ) -> Tuple[NotificationModel, bool]:
        return await asyncio.to_thread(
            self._sync_create_notification,
            user_id,
            title,
            body,
            occurrence_key,
            reminder_id,
            task_id,
            category,
            priority,
            is_alarm,
            action_url,
            delivery_channel,
            status,
            metadata,
            triggered_at,
        )

    def _sync_list_notifications(
        self, user_id: UUID, unread_only: bool, limit: int
    ) -> Tuple[List[NotificationModel], int, int]:
        u_id = str(user_id)
        limit = max(1, min(100, limit))
        conds = ["user_id = ?"]
        params: List[Any] = [u_id]
        if unread_only:
            conds.append("status = 'unread'")
        where_sql = " AND ".join(conds)

        with self._get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM notifications WHERE {where_sql}", params).fetchone()[0]
            unread_count = conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND status = 'unread'", (u_id,)
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT * FROM notifications
                WHERE {where_sql}
                ORDER BY triggered_at DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()
            return [self._row_to_notification(r) for r in rows], total, unread_count

    async def list_notifications(
        self, user_id: UUID, unread_only: bool = False, limit: int = 50
    ) -> Tuple[List[NotificationModel], int, int]:
        return await asyncio.to_thread(self._sync_list_notifications, user_id, unread_only, limit)

    def _sync_update_notif_status(
        self, user_id: UUID, notification_id: UUID, new_status: NotificationStatus
    ) -> Optional[NotificationModel]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            read_at = now_iso if new_status in (NotificationStatus.read, NotificationStatus.acted, NotificationStatus.dismissed) else None
            acted_at = now_iso if new_status in (NotificationStatus.acted, NotificationStatus.dismissed) else None
            cur = conn.execute(
                """
                UPDATE notifications
                SET status = ?,
                    read_at = COALESCE(read_at, ?),
                    acted_at = COALESCE(?, acted_at)
                WHERE id = ? AND user_id = ?
                """,
                (new_status.value, read_at, acted_at, str(notification_id), str(user_id)),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
                (str(notification_id), str(user_id)),
            ).fetchone()
            conn.commit()
            return self._row_to_notification(row)

    async def update_notification_status(
        self, user_id: UUID, notification_id: UUID, new_status: NotificationStatus
    ) -> Optional[NotificationModel]:
        return await asyncio.to_thread(self._sync_update_notif_status, user_id, notification_id, new_status)

    def _sync_mark_all_read(self, user_id: UUID) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE notifications
                SET status = 'read', read_at = COALESCE(read_at, ?)
                WHERE user_id = ? AND status = 'unread'
                """,
                (now_iso, str(user_id)),
            )
            conn.commit()
            return cur.rowcount

    async def mark_all_notifications_read(self, user_id: UUID) -> int:
        return await asyncio.to_thread(self._sync_mark_all_read, user_id)

    def _sync_log_delivery(
        self,
        user_id: UUID,
        channel: str,
        status: DeliveryLogStatus,
        reminder_id: Optional[UUID],
        notification_id: Optional[UUID],
        subscription_id: Optional[UUID],
        attempt_number: int,
        http_status: Optional[int],
        error_detail: Optional[str],
    ) -> DeliveryLogModel:
        log_id = str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO notification_delivery_logs (
                    id, user_id, reminder_id, notification_id, subscription_id,
                    channel, status, attempt_number, http_status, error_detail, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    str(user_id),
                    str(reminder_id) if reminder_id else None,
                    str(notification_id) if notification_id else None,
                    str(subscription_id) if subscription_id else None,
                    channel,
                    status.value,
                    attempt_number,
                    http_status,
                    error_detail,
                    now_iso,
                ),
            )
            row = conn.execute("SELECT * FROM notification_delivery_logs WHERE id = ?", (log_id,)).fetchone()
            conn.commit()
            return self._row_to_delivery_log(row)

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
    ) -> DeliveryLogModel:
        return await asyncio.to_thread(
            self._sync_log_delivery,
            user_id,
            channel,
            status,
            reminder_id,
            notification_id,
            subscription_id,
            attempt_number,
            http_status,
            error_detail,
        )

    def _sync_list_delivery_logs(
        self, user_id: UUID, reminder_id: Optional[UUID], limit: int
    ) -> List[DeliveryLogModel]:
        conds = ["user_id = ?"]
        params: List[Any] = [str(user_id)]
        if reminder_id:
            conds.append("reminder_id = ?")
            params.append(str(reminder_id))
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM notification_delivery_logs
                WHERE {' AND '.join(conds)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params + [max(1, min(100, limit))],
            ).fetchall()
            return [self._row_to_delivery_log(r) for r in rows]

    async def list_delivery_logs(
        self, user_id: UUID, reminder_id: Optional[UUID] = None, limit: int = 50
    ) -> List[DeliveryLogModel]:
        return await asyncio.to_thread(self._sync_list_delivery_logs, user_id, reminder_id, limit)

    # ------------------------------------------------------------------
    # Push Subscriptions
    # ------------------------------------------------------------------
    def _sync_upsert_push_subscription(
        self, user_id: UUID, sub: PushSubscriptionCreate
    ) -> PushSubscriptionModel:
        u_id = str(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM push_subscriptions WHERE user_id = ? AND endpoint = ?",
                (u_id, sub.endpoint),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE push_subscriptions
                    SET p256dh = ?, auth_secret = ?, user_agent = ?, device_label = ?,
                        is_active = 1, failure_count = 0, last_error = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (sub.keys.p256dh, sub.keys.auth, sub.user_agent, sub.device_label, now_iso, existing["id"]),
                )
                row = conn.execute("SELECT * FROM push_subscriptions WHERE id = ?", (existing["id"],)).fetchone()
            else:
                sub_id = str(uuid4())
                conn.execute(
                    """
                    INSERT INTO push_subscriptions (
                        id, user_id, endpoint, p256dh, auth_secret,
                        user_agent, device_label, is_active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        sub_id,
                        u_id,
                        sub.endpoint,
                        sub.keys.p256dh,
                        sub.keys.auth,
                        sub.user_agent,
                        sub.device_label,
                        now_iso,
                        now_iso,
                    ),
                )
                row = conn.execute("SELECT * FROM push_subscriptions WHERE id = ?", (sub_id,)).fetchone()
            conn.commit()
            return self._row_to_subscription(row)

    async def upsert_push_subscription(
        self, user_id: UUID, sub: PushSubscriptionCreate
    ) -> PushSubscriptionModel:
        return await asyncio.to_thread(self._sync_upsert_push_subscription, user_id, sub)

    def _sync_list_push_subscriptions(self, user_id: UUID, active_only: bool) -> List[PushSubscriptionModel]:
        conds = ["user_id = ?"]
        if active_only:
            conds.append("is_active = 1")
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM push_subscriptions WHERE {' AND '.join(conds)} ORDER BY created_at DESC",
                (str(user_id),),
            ).fetchall()
            return [self._row_to_subscription(r) for r in rows]

    async def list_push_subscriptions(
        self, user_id: UUID, active_only: bool = False
    ) -> List[PushSubscriptionModel]:
        return await asyncio.to_thread(self._sync_list_push_subscriptions, user_id, active_only)

    def _sync_delete_push_subscription(self, user_id: UUID, subscription_id: UUID) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM push_subscriptions WHERE id = ? AND user_id = ?",
                (str(subscription_id), str(user_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    async def delete_push_subscription(self, user_id: UUID, subscription_id: UUID) -> bool:
        return await asyncio.to_thread(self._sync_delete_push_subscription, user_id, subscription_id)

    def _sync_update_subscription_health(
        self,
        subscription_id: UUID,
        is_active: bool,
        failure_count: int,
        last_error: Optional[str],
        last_success_at: Optional[datetime],
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        succ_iso = ensure_utc(last_success_at).isoformat() if last_success_at else None
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE push_subscriptions
                SET is_active = ?,
                    failure_count = ?,
                    last_error = ?,
                    last_success_at = COALESCE(?, last_success_at),
                    updated_at = ?
                WHERE id = ?
                """,
                (1 if is_active else 0, failure_count, last_error, succ_iso, now_iso, str(subscription_id)),
            )
            conn.commit()

    async def update_push_subscription_health(
        self,
        subscription_id: UUID,
        is_active: bool,
        failure_count: int,
        last_error: Optional[str] = None,
        last_success_at: Optional[datetime] = None,
    ) -> None:
        await asyncio.to_thread(
            self._sync_update_subscription_health,
            subscription_id,
            is_active,
            failure_count,
            last_error,
            last_success_at,
        )

    # ------------------------------------------------------------------
    # Scheduler Operations (Atomic SQLite Claims)
    # ------------------------------------------------------------------
    def _sync_claim_due_reminders(
        self,
        worker_id: str,
        batch_size: int,
        lease_seconds: int,
        now_utc: datetime,
    ) -> List[ReminderModel]:
        now_iso = ensure_utc(now_utc).isoformat()
        lease_exp_iso = (ensure_utc(now_utc) + timedelta(seconds=lease_seconds)).isoformat()
        claimed: List[ReminderModel] = []

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE (
                    (status = 'scheduled' AND trigger_at <= ?)
                    OR (status = 'snoozed' AND COALESCE(snoozed_until, trigger_at) <= ?)
                    OR (status = 'due' AND next_retry_at IS NOT NULL AND next_retry_at <= ? AND delivery_attempts < max_delivery_attempts)
                )
                AND (lease_expires_at IS NULL OR lease_expires_at < ?)
                ORDER BY trigger_at ASC
                LIMIT ?
                """,
                (now_iso, now_iso, now_iso, now_iso, max(1, min(100, batch_size))),
            ).fetchall()

            for r in rows:
                conn.execute(
                    """
                    UPDATE reminders
                    SET claimed_by = ?, lease_expires_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (worker_id, lease_exp_iso, now_iso, r["id"]),
                )
                updated_row = conn.execute("SELECT * FROM reminders WHERE id = ?", (r["id"],)).fetchone()
                if updated_row:
                    claimed.append(self._row_to_reminder(updated_row))

            conn.commit()
        return claimed

    async def claim_due_reminders(
        self,
        worker_id: str,
        batch_size: int = 20,
        lease_seconds: int = 120,
        now_utc: Optional[datetime] = None,
    ) -> List[ReminderModel]:
        return await asyncio.to_thread(
            self._sync_claim_due_reminders,
            worker_id,
            batch_size,
            lease_seconds,
            now_utc or datetime.now(timezone.utc),
        )

    def _sync_list_due_for_user(self, user_id: UUID, now_utc: datetime, limit: int) -> List[ReminderModel]:
        now_iso = ensure_utc(now_utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE user_id = ?
                AND (
                    (status = 'scheduled' AND trigger_at <= ?)
                    OR (status = 'snoozed' AND COALESCE(snoozed_until, trigger_at) <= ?)
                )
                AND (lease_expires_at IS NULL OR lease_expires_at < ?)
                ORDER BY trigger_at ASC
                LIMIT ?
                """,
                (str(user_id), now_iso, now_iso, now_iso, max(1, min(50, limit))),
            ).fetchall()
            lease_exp_iso = (ensure_utc(now_utc) + timedelta(seconds=60)).isoformat()
            claimed = []
            for r in rows:
                conn.execute(
                    "UPDATE reminders SET claimed_by = 'user-poll', lease_expires_at = ? WHERE id = ?",
                    (lease_exp_iso, r["id"]),
                )
                claimed.append(self._row_to_reminder(r))
            conn.commit()
            return claimed

    async def list_due_for_user(
        self, user_id: UUID, now_utc: datetime, limit: int = 20
    ) -> List[ReminderModel]:
        return await asyncio.to_thread(self._sync_list_due_for_user, user_id, now_utc, limit)

    def _sync_finalize_reminder_trigger(
        self,
        reminder_id: UUID,
        new_status: ReminderStatus,
        next_trigger_at: Optional[datetime],
        last_triggered_at: Optional[datetime],
        delivery_attempts: int,
        next_retry_at: Optional[datetime],
        escalation_count: Optional[int],
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            existing = conn.execute("SELECT * FROM reminders WHERE id = ?", (str(reminder_id),)).fetchone()
            if not existing:
                return
            sets = [
                "status = ?",
                "delivery_attempts = ?",
                "next_retry_at = ?",
                "claimed_by = NULL",
                "lease_expires_at = NULL",
                "updated_at = ?",
            ]
            params: List[Any] = [
                new_status.value,
                delivery_attempts,
                ensure_utc(next_retry_at).isoformat() if next_retry_at else None,
                now_iso,
            ]
            if next_trigger_at is not None:
                sets.append("trigger_at = ?")
                params.append(ensure_utc(next_trigger_at).isoformat())
            if new_status == ReminderStatus.scheduled:
                sets.append("snoozed_until = NULL")
            if last_triggered_at is not None:
                sets.append("last_triggered_at = ?")
                params.append(ensure_utc(last_triggered_at).isoformat())
            if escalation_count is not None:
                sets.append("escalation_count = ?")
                params.append(escalation_count)

            params.append(str(reminder_id))
            conn.execute(f"UPDATE reminders SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()

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
        await asyncio.to_thread(
            self._sync_finalize_reminder_trigger,
            reminder_id,
            new_status,
            next_trigger_at,
            last_triggered_at,
            delivery_attempts,
            next_retry_at,
            escalation_count,
        )

