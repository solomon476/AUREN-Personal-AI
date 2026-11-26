"""API endpoints for In-App Notification Center, Delivery Audit Logs, and Web Push Subscriptions."""

from datetime import datetime, timezone
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import settings
from app.core.security import get_current_user
from app.models.reminders import (
    DeliveryLogModel,
    NotificationListResponse,
    NotificationModel,
    NotificationPreferences,
    NotificationStatus,
    PushSubscriptionCreate,
    PushSubscriptionListResponse,
    PushSubscriptionPublicView,
    VapidPublicKeyResponse,
)
from app.models.user import AuthenticatedUser, UserProfileUpdate
from app.services.profile_service import profile_service
from app.services.reminders.base_repository import BaseReminderRepository
from app.services.reminders.repository import get_reminder_repository
from app.services.reminders.scheduler import ReminderProcessor
from app.services.reminders.web_push import WebPushService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications & Web Push"])

_processor = ReminderProcessor()
_web_push = WebPushService(settings=settings)


def get_user_notif_repo(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseReminderRepository:
    return get_reminder_repository(user_token=current_user.token)


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False),
    process_due: bool = Query(True, description="Evaluate due reminders for this user if not yet processed"),
    limit: int = Query(50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
) -> NotificationListResponse:
    """List in-app notifications & unread badge counts for the authenticated user."""
    if process_due:
        try:
            profile = await profile_service.get_profile(current_user)
            prefs_dict = profile.preferences
        except Exception:
            prefs_dict = {}
        try:
            await _processor.process_user_due_on_demand(
                user_id=current_user.id,
                repo=repo,
                user_preferences_dict=prefs_dict,
            )
        except Exception as exc:
            logger.debug("On-demand reminder due processing warning: %s", exc)

    items, total, unread_count = await repo.list_notifications(
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit,
    )
    due_alerts = [n for n in items if n.status == NotificationStatus.unread]
    return NotificationListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        due_alerts=due_alerts[:5],
    )


@router.post("/{notification_id}/read", response_model=NotificationModel)
async def mark_notification_read(
    notification_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
) -> NotificationModel:
    updated = await repo.update_notification_status(
        user_id=current_user.id,
        notification_id=notification_id,
        new_status=NotificationStatus.read,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return updated


@router.post("/{notification_id}/dismiss", response_model=NotificationModel)
async def dismiss_notification(
    notification_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
) -> NotificationModel:
    updated = await repo.update_notification_status(
        user_id=current_user.id,
        notification_id=notification_id,
        new_status=NotificationStatus.dismissed,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return updated


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
):
    count = await repo.mark_all_notifications_read(user_id=current_user.id)
    return {"marked_read": count}


@router.get("/delivery-logs", response_model=List[DeliveryLogModel])
async def list_delivery_logs(
    reminder_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
) -> List[DeliveryLogModel]:
    """Audit trail of notification delivery attempts, push retries, and quiet-hour suppressions."""
    return await repo.list_delivery_logs(user_id=current_user.id, reminder_id=reminder_id, limit=limit)


# ----------------------------------------------------------------------
# Web Push Configuration & Subscription Management
# ----------------------------------------------------------------------
@router.get("/push/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_public_key(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> VapidPublicKeyResponse:
    """Return ONLY the public VAPID key needed by browser PushManager. Never exposes private key."""
    return VapidPublicKeyResponse(
        configured=_web_push.is_configured(),
        public_key=_web_push.get_public_key(),
        subject=settings.VAPID_SUBJECT,
    )


@router.get("/push/subscriptions", response_model=PushSubscriptionListResponse)
async def list_push_subscriptions(
    active_only: bool = Query(False),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
) -> PushSubscriptionListResponse:
    subs = await repo.list_push_subscriptions(user_id=current_user.id, active_only=active_only)
    public_items = [
        PushSubscriptionPublicView(
            id=s.id,
            endpoint=s.endpoint,
            device_label=s.device_label,
            user_agent=s.user_agent,
            is_active=s.is_active,
            failure_count=s.failure_count,
            last_error=s.last_error,
            last_success_at=s.last_success_at,
            created_at=s.created_at,
        )
        for s in subs
    ]
    return PushSubscriptionListResponse(items=public_items, total=len(public_items))


@router.post("/push/subscribe", response_model=PushSubscriptionPublicView, status_code=status.HTTP_201_CREATED)
async def subscribe_web_push(
    payload: PushSubscriptionCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
) -> PushSubscriptionPublicView:
    saved = await repo.upsert_push_subscription(user_id=current_user.id, sub=payload)
    try:
        await profile_service.update_profile(
            current_user,
            UserProfileUpdate(preferences={"browser_push_enabled": True}),
        )
    except Exception as exc:
        logger.debug("Non-blocking profile push flag sync warning: %s", exc)
    return PushSubscriptionPublicView(
        id=saved.id,
        endpoint=saved.endpoint,
        device_label=saved.device_label,
        user_agent=saved.user_agent,
        is_active=saved.is_active,
        failure_count=saved.failure_count,
        last_error=saved.last_error,
        last_success_at=saved.last_success_at,
        created_at=saved.created_at,
    )


@router.delete("/push/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_push_subscription(
    subscription_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
) -> None:
    deleted = await repo.delete_push_subscription(user_id=current_user.id, subscription_id=subscription_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Push subscription not found.")


@router.post("/test-push")
async def send_test_notification(
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseReminderRepository = Depends(get_user_notif_repo),
):
    """Trigger an immediate test notification across in-app Notification Center & registered Web Push devices."""
    now = datetime.now(timezone.utc)
    try:
        profile = await profile_service.get_profile(current_user)
        prefs = NotificationPreferences.from_user_prefs(profile.preferences)
    except Exception:
        prefs = NotificationPreferences()

    notif, _ = await repo.create_notification(
        user_id=current_user.id,
        title="AUREN Notification Test",
        body="Your alerts, chime sound, and reminder pipeline are working properly.",
        occurrence_key=f"test:{current_user.id}:{int(now.timestamp())}",
        category="system",
        priority="normal",
        is_alarm=False,
        action_url="/reminders",
        delivery_channel="both" if prefs.browser_push_enabled else "in_app",
        status=NotificationStatus.unread,
        metadata={"sound_key": prefs.reminder_sound, "is_test": True},
        triggered_at=now,
    )

    push_results = []
    subs = await repo.list_push_subscriptions(user_id=current_user.id, active_only=True)
    if subs and _web_push.is_configured():
        for sub in subs:
            res = await _web_push.send_push(
                endpoint=sub.endpoint,
                p256dh=sub.p256dh,
                auth_secret=sub.auth_secret,
                payload={
                    "title": "AUREN Test Notification",
                    "body": "Push notifications are active for this device.",
                    "tag": "auren-test-push",
                    "url": "/reminders",
                    "notification_id": str(notif.id),
                },
            )
            if res.success:
                await repo.update_push_subscription_health(
                    subscription_id=sub.id,
                    is_active=True,
                    failure_count=0,
                    last_error=None,
                    last_success_at=now,
                )
            elif res.expired_subscription:
                await repo.update_push_subscription_health(
                    subscription_id=sub.id,
                    is_active=False,
                    failure_count=sub.failure_count + 1,
                    last_error=res.error_detail,
                )
            push_results.append(
                {
                    "subscription_id": str(sub.id),
                    "device_label": sub.device_label,
                    "success": res.success,
                    "status_code": res.status_code,
                    "error": res.error_detail,
                }
            )

    return {
        "notification": notif.model_dump(mode="json"),
        "registered_devices_count": len(subs),
        "push_configured": _web_push.is_configured(),
        "push_deliveries": push_results,
    }

