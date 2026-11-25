"""Abstract repository contract for Reminders, Notifications, Push Subscriptions, and Delivery Logs."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from app.models.reminders import (
    DeliveryLogModel,
    DeliveryLogStatus,
    NotificationModel,
    NotificationStatus,
    PushSubscriptionCreate,
    PushSubscriptionModel,
    ReminderCreate,
    ReminderModel,
    ReminderStatus,
    ReminderType,
    ReminderUpdate,
)


class BaseReminderRepository(ABC):
    """Interface defining all reminder & notification storage operations."""

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------
    @abstractmethod
    async def create_reminder(self, user_id: UUID, reminder: ReminderCreate) -> ReminderModel:
        pass

    @abstractmethod
    async def get_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def update_reminder(
        self,
        user_id: UUID,
        reminder_id: UUID,
        update: ReminderUpdate,
    ) -> Optional[ReminderModel]:
        pass

    @abstractmethod
    async def delete_reminder(self, user_id: UUID, reminder_id: UUID) -> bool:
        pass

    @abstractmethod
    async def snooze_reminder(
        self,
        user_id: UUID,
        reminder_id: UUID,
        snoozed_until: datetime,
    ) -> Optional[ReminderModel]:
        pass

    @abstractmethod
    async def complete_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        pass

    @abstractmethod
    async def cancel_reminder(self, user_id: UUID, reminder_id: UUID) -> Optional[ReminderModel]:
        pass

    # ------------------------------------------------------------------
    # Task-Integration Helpers
    # ------------------------------------------------------------------
    @abstractmethod
    async def find_active_by_dedupe_key(self, user_id: UUID, dedupe_key: str) -> Optional[ReminderModel]:
        pass

    @abstractmethod
    async def suppress_task_reminders(self, user_id: UUID, task_id: UUID) -> int:
        pass

    @abstractmethod
    async def reschedule_task_reminders(
        self,
        user_id: UUID,
        task_id: UUID,
        new_due_date: datetime,
        default_lead_minutes: int = 30,
    ) -> int:
        pass

    # ------------------------------------------------------------------
    # Notifications & Delivery Logs
    # ------------------------------------------------------------------
    @abstractmethod
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
        """Insert notification deduplicated by (user_id, occurrence_key). Returns (notification, was_inserted)."""
        pass

    @abstractmethod
    async def list_notifications(
        self,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
    ) -> Tuple[List[NotificationModel], int, int]:
        """Returns (items, total, unread_count)."""
        pass

    @abstractmethod
    async def update_notification_status(
        self,
        user_id: UUID,
        notification_id: UUID,
        new_status: NotificationStatus,
    ) -> Optional[NotificationModel]:
        pass

    @abstractmethod
    async def mark_all_notifications_read(self, user_id: UUID) -> int:
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def list_delivery_logs(
        self,
        user_id: UUID,
        reminder_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> List[DeliveryLogModel]:
        pass

    # ------------------------------------------------------------------
    # Push Subscriptions
    # ------------------------------------------------------------------
    @abstractmethod
    async def upsert_push_subscription(
        self,
        user_id: UUID,
        sub: PushSubscriptionCreate,
    ) -> PushSubscriptionModel:
        pass

    @abstractmethod
    async def list_push_subscriptions(
        self,
        user_id: UUID,
        active_only: bool = False,
    ) -> List[PushSubscriptionModel]:
        pass

    @abstractmethod
    async def delete_push_subscription(self, user_id: UUID, subscription_id: UUID) -> bool:
        pass

    @abstractmethod
    async def update_push_subscription_health(
        self,
        subscription_id: UUID,
        is_active: bool,
        failure_count: int,
        last_error: Optional[str] = None,
        last_success_at: Optional[datetime] = None,
    ) -> None:
        pass

    # ------------------------------------------------------------------
    # Scheduler Operations (Atomic Claim & State Finalization)
    # ------------------------------------------------------------------
    @abstractmethod
    async def list_due_for_user(
        self,
        user_id: UUID,
        now_utc: datetime,
        limit: int = 20,
    ) -> List[ReminderModel]:
        pass

    @abstractmethod
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
        pass

