"""Supabase PostgREST repository adapter for Smart Reminders, Notifications & Web Push (RLS-enforced)."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from app.core.exceptions import DatabaseAuthError, DatabaseConnectionError, DatabaseError
from app.models.reminders import (
    DeliveryChannel,
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
)
from app.services.reminders.base_repository import BaseReminderRepository
from app.services.reminders.time_utils import ensure_utc

logger = logging.getLogger(__name__)


class SupabaseReminderRepository(BaseReminderRepository):
    """Supabase PostgREST adapter communicating strictly with the authenticated user's JWT."""

    def __init__(
        self,
        supabase_url: str,
        supabase_anon_key: str,
        user_token: str,
        timeout: float = 10.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.rest_url = f"{self.supabase_url}/rest/v1"
        self.supabase_anon_key = supabase_anon_key
        self.user_token = user_token
        self.timeout = timeout
        self._client = http_client

    def _get_headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.supabase_anon_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.user_token}",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> httpx.Response:
        url = f"{self.rest_url}/{endpoint.lstrip('/')}"
        headers = self._get_headers(prefer=prefer)
        try:
            if self._client:
                response = await self._client.request(
                    method, url, params=params, json=json_data, headers=headers, timeout=self.timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method, url, params=params, json=json_data, headers=headers
                    )
        except httpx.ConnectError as err:
            raise DatabaseConnectionError(f"Failed to connect to Supabase: {err}") from err
        except httpx.TimeoutException as err:
            raise DatabaseConnectionError(f"Supabase request timed out: {err}") from err
        except httpx.RequestError as err:
            raise DatabaseError(f"Network error interacting with Supabase: {err}") from err

        if response.status_code in (401, 403):
            raise DatabaseAuthError(f"Supabase authentication failed ({response.status_code}): {response.text}")

        return response

    # ------------------------------------------------------------------
    # Row Mappers
    # ------------------------------------------------------------------
    def _map_reminder(self, r: Dict[str, Any]) -> ReminderModel:
        rec_rule = None
        if r.get("recurrence_rule"):
            try:
                rec_rule = RecurrenceRule(**r["recurrence_rule"])
            except Exception:
                rec_rule = None
        task_title = r.get("tasks", {}).get("title") if isinstance(r.get("tasks"), dict) else None
        proj_name = r.get("projects", {}).get("name") if isinstance(r.get("projects"), dict) else None

        return ReminderModel(
            id=UUID(r["id"]),
            user_id=UUID(r["user_id"]),
            task_id=UUID(r["task_id"]) if r.get("task_id") else None,
            project_id=UUID(r["project_id"]) if r.get("project_id") else None,
            goal_id=UUID(r["goal_id"]) if r.get("goal_id") else None,
            task_title=task_title,
            project_name=proj_name,
            title=r["title"],
            description=r.get("description"),
            reminder_type=ReminderType(r.get("reminder_type", "general")),
            trigger_at=datetime.fromisoformat(r["trigger_at"]),
            original_trigger_at=datetime.fromisoformat(r["original_trigger_at"]),
            timezone=r.get("timezone", "UTC"),
            recurrence_rule=rec_rule,
            recurrence_text=r.get("recurrence_text"),
            status=ReminderStatus(r.get("status", "scheduled")),
            priority=ReminderPriority(r.get("priority", "normal")),
            is_alarm=bool(r.get("is_alarm", False)),
            sound_key=r.get("sound_key"),
            snoozed_until=datetime.fromisoformat(r["snoozed_until"]) if r.get("snoozed_until") else None,
            snooze_count=int(r.get("snooze_count", 0) or 0),
            last_triggered_at=datetime.fromisoformat(r["last_triggered_at"]) if r.get("last_triggered_at") else None,
            next_retry_at=datetime.fromisoformat(r["next_retry_at"]) if r.get("next_retry_at") else None,
            delivery_attempts=int(r.get("delivery_attempts", 0) or 0),
            max_delivery_attempts=int(r.get("max_delivery_attempts", 5) or 5),
            escalation_count=int(r.get("escalation_count", 0) or 0),
            completed_at=datetime.fromisoformat(r["completed_at"]) if r.get("completed_at") else None,
            cancelled_at=datetime.fromisoformat(r["cancelled_at"]) if r.get("cancelled_at") else None,
            source=ReminderSource(r.get("source", "manual")),
            dedupe_key=r.get("dedupe_key"),
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    def _map_notification(self, n: Dict[str, Any]) -> NotificationModel:
        return NotificationModel(
            id=UUID(n["id"]),
            user_id=UUID(n["user_id"]),
            reminder_id=UUID(n["reminder_id"]) if n.get("reminder_id") else None,
            task_id=UUID(n["task_id"]) if n.get("task_id") else None,
            title=n["title"],
            body=n.get("body"),
            category=n.get("category", "reminder"),
            priority=ReminderPriority(n.get("priority", "normal")),
            is_alarm=bool(n.get("is_alarm", False)),
            action_url=n.get("action_url", "/reminders"),
            delivery_channel=DeliveryChannel(n.get("delivery_channel", "in_app")),
            status=NotificationStatus(n.get("status", "unread")),
            occurrence_key=n["occurrence_key"],
            metadata=n.get("metadata") or {},
            triggered_at=datetime.fromisoformat(n["triggered_at"]),
            read_at=datetime.fromisoformat(n["read_at"]) if n.get("read_at") else None,
            acted_at=datetime.fromisoformat(n["acted_at"]) if n.get("acted_at") else None,
            created_at=datetime.fromisoformat(n["created_at"]),
        )

    def _map_subscription(self, s: Dict[str, Any]) -> PushSubscriptionModel:
        return PushSubscriptionModel(
            id=UUID(s["id"]),
            user_id=UUID(s["user_id"]),
            endpoint=s["endpoint"],
            p256dh=s["p256dh"],
            auth_secret=s["auth_secret"],
            user_agent=s.get("user_agent"),
            device_label=s.get("device_label"),
            is_active=bool(s.get("is_active", True)),
            failure_count=int(s.get("failure_count", 0) or 0),
            last_error=s.get("last_error"),
            last_success_at=datetime.fromisoformat(s["last_success_at"]) if s.get("last_success_at") else None,
            created_at=datetime.fromisoformat(s["created_at"]),
            updated_at=datetime.fromisoformat(s["updated_at"]),
        )

    def _map_delivery_log(self, d: Dict[str, Any]) -> DeliveryLogModel:
        return DeliveryLogModel(
            id=UUID(d["id"]),
            user_id=UUID(d["user_id"]),
            reminder_id=UUID(d["reminder_id"]) if d.get("reminder_id") else None,
            notification_id=UUID(d["notification_id"]) if d.get("notification_id") else None,
            subscription_id=UUID(d["subscription_id"]) if d.get("subscription_id") else None,
            channel=d["channel"],
            status=DeliveryLogStatus(d["status"]),
            attempt_number=int(d.get("attempt_number", 1) or 1),
            http_status=d.get("http_status"),
            error_detail=d.get("error_detail"),
            created_at=datetime.fromisoformat(d["created_at"]),
        )

    # ------------------------------------------------------------------
    # Reminders CRUD
    # ------------------------------------------------------------------
    async def create_reminder(self, user_id: UUID, reminder: ReminderCreate) -> ReminderModel:
        if reminder.dedupe_key:
            existing = await self.find_active_by_dedupe_key(user_id, reminder.dedupe_key)
            if existing:
                return existing

        trig_utc = ensure_utc(reminder.trigger_at, reminder.timezone).isoformat()
        payload = {
            "user_id": str(user_id),
            "title": reminder.title,
            "description": reminder.description,
            "reminder_type": reminder.reminder_type.value,
            "trigger_at": trig_utc,
            "original_trigger_at": trig_utc,
            "timezone": reminder.timezone,
            "recurrence_rule": reminder.recurrence_rule.model_dump(mode="json") if reminder.recurrence_rule else None,
            "recurrence_text": reminder.recurrence_text,
            "status": "scheduled",
            "priority": reminder.priority.value,
            "is_alarm": bool(reminder.is_alarm or reminder.priority == ReminderPriority.alarm),
            "sound_key": reminder.sound_key,
            "task_id": str(reminder.task_id) if reminder.task_id else None,
            "project_id": str(reminder.project_id) if reminder.project_id else None,
            "goal_id": str(reminder.goal_id) if reminder.goal_id else None,
            "source": reminder.source.value,
            "dedupe_key": reminder.dedupe_key,
            "max_delivery_attempts": reminder.max_delivery_attempts,
        }
        resp = await self._request("POST", "/reminders", json_data=payload, prefer="return=representation")
        if resp.status_code not in (200, 201):
            raise DatabaseError(f"Failed creating reminder: {resp.text}")
        items = resp.json()
        if not items:
            raise DatabaseError("Reminder created but no representation returned")
        return self._map_reminder(items[0])

    async def get_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        resp = await self._request(
            "GET",
            "/reminders",
            params={"id": f"eq.{reminder_id}", "select": "*,tasks(title),projects(name)"},
        )
        if resp.status_code != 200 or not resp.json():
            return None
        return self._map_reminder(resp.json()[0])

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
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        params: Dict[str, Any] = {
            "select": "*,tasks(title),projects(name)",
            "order": "trigger_at.asc",
            "limit": str(page_size),
            "offset": str(offset),
        }
        if status and status != "all":
            if status == "upcoming":
                params["status"] = "eq.scheduled"
            elif status == "due":
                params["status"] = "in.(due,snoozed)"
            elif status == "history":
                params["status"] = "in.(completed,cancelled,missed)"
            else:
                params["status"] = f"eq.{status}"

        if recurring_only:
            params["recurrence_rule"] = "not.is.null"
        if task_id:
            params["task_id"] = f"eq.{task_id}"
        if query:
            params["title"] = f"ilike.*{query.strip()}*"

        resp = await self._request("GET", "/reminders", params=params, prefer="count=exact")
        if resp.status_code != 200:
            return [], 0

        data = resp.json()
        total = len(data)
        cr = resp.headers.get("content-range", "")
        if "/" in cr:
            try:
                total = int(cr.split("/")[1])
            except Exception:
                pass
        return [self._map_reminder(r) for r in data], total

    async def update_reminder(
        self, user_id: UUID, reminder_id: UUID, update: ReminderUpdate
    ) -> Optional[ReminderModel]:
        existing = await self.get_reminder(user_id, reminder_id)
        if not existing:
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {"updated_at": now_iso}
        tz_name = update.timezone or existing.timezone

        if update.title is not None:
            payload["title"] = update.title
        if update.description is not None:
            payload["description"] = update.description
        if update.reminder_type is not None:
            payload["reminder_type"] = update.reminder_type.value
        if update.timezone is not None:
            payload["timezone"] = update.timezone
        if update.trigger_at is not None:
            payload["trigger_at"] = ensure_utc(update.trigger_at, tz_name).isoformat()
            payload["snoozed_until"] = None
            payload["next_retry_at"] = None
            if update.status is None and existing.status in (
                ReminderStatus.due,
                ReminderStatus.snoozed,
                ReminderStatus.missed,
                ReminderStatus.completed,
                ReminderStatus.cancelled,
            ):
                payload["status"] = "scheduled"
        if update.clear_recurrence:
            payload["recurrence_rule"] = None
            payload["recurrence_text"] = None
        elif update.recurrence_rule is not None:
            payload["recurrence_rule"] = update.recurrence_rule.model_dump(mode="json")
        if update.recurrence_text is not None and not update.clear_recurrence:
            payload["recurrence_text"] = update.recurrence_text
        if update.priority is not None:
            payload["priority"] = update.priority.value
        if update.is_alarm is not None:
            payload["is_alarm"] = update.is_alarm
        if update.sound_key is not None:
            payload["sound_key"] = update.sound_key
        if update.task_id is not None:
            payload["task_id"] = str(update.task_id)
        if update.project_id is not None:
            payload["project_id"] = str(update.project_id)
        if update.goal_id is not None:
            payload["goal_id"] = str(update.goal_id)
        if update.status is not None:
            payload["status"] = update.status.value
            if update.status == ReminderStatus.completed:
                payload["completed_at"] = now_iso
            elif update.status == ReminderStatus.cancelled:
                payload["cancelled_at"] = now_iso

        resp = await self._request(
            "PATCH",
            f"/reminders?id=eq.{reminder_id}",
            json_data=payload,
            prefer="return=representation",
        )
        if resp.status_code != 200 or not resp.json():
            return None
        return await self.get_reminder(user_id, reminder_id)

    async def delete_reminder(self, user_id: UUID, reminder_id: UUID) -> bool:
        resp = await self._request("DELETE", f"/reminders?id=eq.{reminder_id}")
        return resp.status_code in (200, 204)

    async def snooze_reminder(
        self, user_id: UUID, reminder_id: UUID, snoozed_until: datetime
    ) -> Optional[ReminderModel]:
        existing = await self.get_reminder(user_id, reminder_id)
        if not existing:
            return None
        now_iso = datetime.now(timezone.utc).isoformat()
        snooze_iso = ensure_utc(snoozed_until).isoformat()
        payload = {
            "status": "snoozed",
            "trigger_at": snooze_iso,
            "snoozed_until": snooze_iso,
            "snooze_count": existing.snooze_count + 1,
            "next_retry_at": None,
            "claimed_by": None,
            "lease_expires_at": None,
            "updated_at": now_iso,
        }
        resp = await self._request(
            "PATCH",
            f"/reminders?id=eq.{reminder_id}",
            json_data=payload,
            prefer="return=representation",
        )
        if resp.status_code != 200 or not resp.json():
            return None
        return await self.get_reminder(user_id, reminder_id)

    async def complete_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        now_iso = datetime.now(timezone.utc).isoformat()
        resp = await self._request(
            "PATCH",
            f"/reminders?id=eq.{reminder_id}",
            json_data={
                "status": "completed",
                "completed_at": now_iso,
                "snoozed_until": None,
                "next_retry_at": None,
                "updated_at": now_iso,
            },
            prefer="return=representation",
        )
        if resp.status_code != 200 or not resp.json():
            return None
        return await self.get_reminder(user_id, reminder_id)

    async def cancel_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        now_iso = datetime.now(timezone.utc).isoformat()
        resp = await self._request(
            "PATCH",
            f"/reminders?id=eq.{reminder_id}",
            json_data={
                "status": "cancelled",
                "cancelled_at": now_iso,
                "snoozed_until": None,
                "next_retry_at": None,
                "updated_at": now_iso,
            },
            prefer="return=representation",
        )
        if resp.status_code != 200 or not resp.json():
            return None
        return await self.get_reminder(user_id, reminder_id)

    # ------------------------------------------------------------------
    # Task Integration Helpers
    # ------------------------------------------------------------------
    async def find_active_by_dedupe_key(self, user_id: UUID, dedupe_key: str) -> Optional[ReminderModel]:
        resp = await self._request(
            "GET",
            "/reminders",
            params={
                "dedupe_key": f"eq.{dedupe_key}",
                "status": "in.(scheduled,due,snoozed)",
                "limit": "1",
            },
        )
        if resp.status_code != 200 or not resp.json():
            return None
        return self._map_reminder(resp.json()[0])

    async def suppress_task_reminders(self, user_id: UUID, task_id: UUID) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        resp = await self._request(
            "PATCH",
            f"/reminders?task_id=eq.{task_id}&status=in.(scheduled,due,snoozed)",
            json_data={"status": "cancelled", "cancelled_at": now_iso, "updated_at": now_iso},
            prefer="return=representation",
        )
        if resp.status_code != 200:
            return 0
        return len(resp.json())

    async def reschedule_task_reminders(
        self,
        user_id: UUID,
        task_id: UUID,
        new_due_date: datetime,
        default_lead_minutes: int = 30,
    ) -> int:
        items, _ = await self.list_reminders(user_id=user_id, task_id=task_id, page=1, page_size=50)
        due_utc = ensure_utc(new_due_date)
        now_iso = datetime.now(timezone.utc).isoformat()
        updated = 0
        for r in items:
            if r.status not in (ReminderStatus.scheduled, ReminderStatus.snoozed):
                continue
            if r.reminder_type == ReminderType.task_due:
                target = due_utc.isoformat()
            elif r.reminder_type == ReminderType.task_before_due:
                target = (due_utc - timedelta(minutes=max(0, default_lead_minutes))).isoformat()
            else:
                continue
            resp = await self._request(
                "PATCH",
                f"/reminders?id=eq.{r.id}",
                json_data={
                    "trigger_at": target,
                    "original_trigger_at": target,
                    "status": "scheduled",
                    "snoozed_until": None,
                    "next_retry_at": None,
                    "updated_at": now_iso,
                },
            )
            if resp.status_code in (200, 204):
                updated += 1
        return updated

    # ------------------------------------------------------------------
    # Notifications & Delivery Logs
    # ------------------------------------------------------------------
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
        # Check if notification with occurrence_key already exists first
        existing_resp = await self._request(
            "GET",
            "/notifications",
            params={"occurrence_key": f"eq.{occurrence_key}", "limit": "1"},
        )
        if existing_resp.status_code == 200 and existing_resp.json():
            return self._map_notification(existing_resp.json()[0]), False

        trig_iso = ensure_utc(triggered_at).isoformat() if triggered_at else datetime.now(timezone.utc).isoformat()
        payload = {
            "user_id": str(user_id),
            "reminder_id": str(reminder_id) if reminder_id else None,
            "task_id": str(task_id) if task_id else None,
            "title": title,
            "body": body,
            "category": category,
            "priority": priority,
            "is_alarm": is_alarm,
            "action_url": action_url,
            "delivery_channel": delivery_channel,
            "status": status.value,
            "occurrence_key": occurrence_key,
            "metadata": metadata or {},
            "triggered_at": trig_iso,
        }
        resp = await self._request(
            "POST",
            "/notifications",
            json_data=payload,
            prefer="return=representation,resolution=ignore-duplicates",
        )
        if resp.status_code in (200, 201) and resp.json():
            return self._map_notification(resp.json()[0]), True

        # Re-read in case of concurrent insert race
        retry_resp = await self._request(
            "GET",
            "/notifications",
            params={"occurrence_key": f"eq.{occurrence_key}", "limit": "1"},
        )
        if retry_resp.status_code == 200 and retry_resp.json():
            return self._map_notification(retry_resp.json()[0]), False
        raise DatabaseError(f"Failed creating notification: {resp.text}")

    async def list_notifications(
        self, user_id: UUID, unread_only: bool = False, limit: int = 50
    ) -> Tuple[List[NotificationModel], int, int]:
        params: Dict[str, Any] = {
            "select": "*",
            "order": "triggered_at.desc",
            "limit": str(max(1, min(100, limit))),
        }
        if unread_only:
            params["status"] = "eq.unread"

        resp = await self._request("GET", "/notifications", params=params, prefer="count=exact")
        if resp.status_code != 200:
            return [], 0, 0

        data = resp.json()
        total = len(data)
        cr = resp.headers.get("content-range", "")
        if "/" in cr:
            try:
                total = int(cr.split("/")[1])
            except Exception:
                pass

        unread_resp = await self._request(
            "GET",
            "/notifications",
            params={"select": "id", "status": "eq.unread", "limit": "1"},
            prefer="count=exact",
        )
        unread_count = 0
        if unread_resp.status_code == 200:
            ucr = unread_resp.headers.get("content-range", "")
            if "/" in ucr:
                try:
                    unread_count = int(ucr.split("/")[1])
                except Exception:
                    unread_count = len(unread_resp.json())

        return [self._map_notification(n) for n in data], total, unread_count

    async def update_notification_status(
        self, user_id: UUID, notification_id: UUID, new_status: NotificationStatus
    ) -> Optional[NotificationModel]:
        now_iso = datetime.now(timezone.utc).isoformat()
        patch: Dict[str, Any] = {"status": new_status.value}
        if new_status in (NotificationStatus.read, NotificationStatus.acted, NotificationStatus.dismissed):
            patch["read_at"] = now_iso
        if new_status in (NotificationStatus.acted, NotificationStatus.dismissed):
            patch["acted_at"] = now_iso

        resp = await self._request(
            "PATCH",
            f"/notifications?id=eq.{notification_id}",
            json_data=patch,
            prefer="return=representation",
        )
        if resp.status_code != 200 or not resp.json():
            return None
        return self._map_notification(resp.json()[0])

    async def mark_all_notifications_read(self, user_id: UUID) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        resp = await self._request(
            "PATCH",
            "/notifications?status=eq.unread",
            json_data={"status": "read", "read_at": now_iso},
            prefer="return=representation",
        )
        if resp.status_code != 200:
            return 0
        return len(resp.json())

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
        payload = {
            "user_id": str(user_id),
            "reminder_id": str(reminder_id) if reminder_id else None,
            "notification_id": str(notification_id) if notification_id else None,
            "subscription_id": str(subscription_id) if subscription_id else None,
            "channel": channel,
            "status": status.value,
            "attempt_number": attempt_number,
            "http_status": http_status,
            "error_detail": error_detail,
        }
        resp = await self._request(
            "POST",
            "/notification_delivery_logs",
            json_data=payload,
            prefer="return=representation",
        )
        if resp.status_code not in (200, 201) or not resp.json():
            raise DatabaseError(f"Failed creating delivery log: {resp.text}")
        return self._map_delivery_log(resp.json()[0])

    async def list_delivery_logs(
        self, user_id: UUID, reminder_id: Optional[UUID] = None, limit: int = 50
    ) -> List[DeliveryLogModel]:
        params: Dict[str, Any] = {
            "select": "*",
            "order": "created_at.desc",
            "limit": str(max(1, min(100, limit))),
        }
        if reminder_id:
            params["reminder_id"] = f"eq.{reminder_id}"
        resp = await self._request("GET", "/notification_delivery_logs", params=params)
        if resp.status_code != 200:
            return []
        return [self._map_delivery_log(d) for d in resp.json()]

    # ------------------------------------------------------------------
    # Push Subscriptions
    # ------------------------------------------------------------------
    async def upsert_push_subscription(
        self, user_id: UUID, sub: PushSubscriptionCreate
    ) -> PushSubscriptionModel:
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "user_id": str(user_id),
            "endpoint": sub.endpoint,
            "p256dh": sub.keys.p256dh,
            "auth_secret": sub.keys.auth,
            "user_agent": sub.user_agent,
            "device_label": sub.device_label,
            "is_active": True,
            "failure_count": 0,
            "last_error": None,
            "updated_at": now_iso,
        }
        resp = await self._request(
            "POST",
            "/push_subscriptions?on_conflict=user_id,endpoint",
            json_data=payload,
            prefer="return=representation,resolution=merge-duplicates",
        )
        if resp.status_code not in (200, 201) or not resp.json():
            raise DatabaseError(f"Failed saving push subscription: {resp.text}")
        return self._map_subscription(resp.json()[0])

    async def list_push_subscriptions(
        self, user_id: UUID, active_only: bool = False
    ) -> List[PushSubscriptionModel]:
        params: Dict[str, Any] = {"select": "*", "order": "created_at.desc"}
        if active_only:
            params["is_active"] = "eq.true"
        resp = await self._request("GET", "/push_subscriptions", params=params)
        if resp.status_code != 200:
            return []
        return [self._map_subscription(s) for s in resp.json()]

    async def delete_push_subscription(self, user_id: UUID, subscription_id: UUID) -> bool:
        resp = await self._request("DELETE", f"/push_subscriptions?id=eq.{subscription_id}")
        return resp.status_code in (200, 204)

    async def update_push_subscription_health(
        self,
        subscription_id: UUID,
        is_active: bool,
        failure_count: int,
        last_error: Optional[str] = None,
        last_success_at: Optional[datetime] = None,
    ) -> None:
        patch: Dict[str, Any] = {
            "is_active": is_active,
            "failure_count": failure_count,
            "last_error": last_error,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if last_success_at:
            patch["last_success_at"] = ensure_utc(last_success_at).isoformat()
        await self._request("PATCH", f"/push_subscriptions?id=eq.{subscription_id}", json_data=patch)

    # ------------------------------------------------------------------
    # Due Evaluation (User Session Catch-up)
    # ------------------------------------------------------------------
    async def list_due_for_user(
        self, user_id: UUID, now_utc: datetime, limit: int = 20
    ) -> List[ReminderModel]:
        now_iso = ensure_utc(now_utc).isoformat()
        resp = await self._request(
            "GET",
            "/reminders",
            params={
                "select": "*",
                "status": "in.(scheduled,snoozed)",
                "trigger_at": f"lte.{now_iso}",
                "order": "trigger_at.asc",
                "limit": str(max(1, min(50, limit))),
            },
        )
        if resp.status_code != 200:
            return []
        return [self._map_reminder(r) for r in resp.json()]

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
        patch: Dict[str, Any] = {
            "status": new_status.value,
            "delivery_attempts": delivery_attempts,
            "next_retry_at": ensure_utc(next_retry_at).isoformat() if next_retry_at else None,
            "claimed_by": None,
            "lease_expires_at": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if next_trigger_at is not None:
            patch["trigger_at"] = ensure_utc(next_trigger_at).isoformat()
        if new_status == ReminderStatus.scheduled:
            patch["snoozed_until"] = None
        if last_triggered_at is not None:
            patch["last_triggered_at"] = ensure_utc(last_triggered_at).isoformat()
        if escalation_count is not None:
            patch["escalation_count"] = escalation_count

        await self._request("PATCH", f"/reminders?id=eq.{reminder_id}", json_data=patch)

