"""Comprehensive backend tests for Smart Reminders, Alarm System, Web Push & Task Integration."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import AsyncIterator, List, Optional
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import DatabaseError
from app.core.security import get_current_user
from app.main import app
from app.models.reminders import (
    DeliveryLogStatus,
    NotificationPreferences,
    NotificationStatus,
    RecurrenceFrequency,
    RecurrenceRule,
    ReminderCreate,
    ReminderPriority,
    ReminderStatus,
    ReminderType,
)
from app.models.user import AuthenticatedUser
from app.services.chat.chat_service import chat_service
from app.services.chat.sqlite_repository import SQLiteChatRepository
from app.services.llm.base import BaseLLMProvider, ChatMessage, LLMResponse
from app.services.productivity.sqlite_repository import SQLiteProductivityRepository
from app.services.profile_service import profile_service
from app.services.reminders.conversational import ConversationalReminderService, is_reminder_intent
from app.services.reminders.repository import get_reminder_repository
from app.services.reminders.scheduler import ReminderProcessor, build_push_payload
from app.services.reminders.sqlite_repository import SQLiteReminderRepository
from app.services.reminders.supabase_repository import SupabaseReminderRepository
from app.services.reminders.time_utils import (
    compute_next_occurrence,
    format_local_datetime,
    is_within_quiet_hours,
    resolve_zoneinfo,
)
from app.services.reminders.web_push import (
    WebPushService,
    _b64url_encode,
    build_vapid_headers,
    decrypt_web_push_payload,
    encrypt_web_push_payload,
    generate_vapid_keypair,
)


USER_A = AuthenticatedUser(
    id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    email="usera@auren.ai",
    role="authenticated",
    token="test-token-user-a",
)
USER_B = AuthenticatedUser(
    id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
    email="userb@auren.ai",
    role="authenticated",
    token="test-token-user-b",
)


class _DummyChatProvider(BaseLLMProvider):
    def __init__(self, chunks: Optional[List[str]] = None):
        self.chunks = chunks or ["Reminder noted and confirmed."]

    def get_model_id(self) -> str:
        return "mock-reminder-test"

    async def generate_response(self, messages: List[ChatMessage], **kwargs) -> LLMResponse:
        return LLMResponse(content="".join(self.chunks), model=self.get_model_id())

    async def stream_response(self, messages: List[ChatMessage], **kwargs) -> AsyncIterator[str]:
        for ch in self.chunks:
            yield ch


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch):
    """Isolate reminder, productivity, chat, and profile SQLite databases per test."""
    rem_repo = SQLiteReminderRepository(db_path=tmp_path / "reminders.db")
    prod_repo = SQLiteProductivityRepository(db_path=tmp_path / "productivity.db")
    chat_repo = SQLiteChatRepository(db_path=tmp_path / "chat.db")

    monkeypatch.setattr(settings, "CHAT_REPOSITORY_TYPE", "sqlite")
    monkeypatch.setattr(settings, "REMINDER_SCHEDULER_ENABLED", False)
    monkeypatch.setattr("app.services.reminders.repository._sqlite_reminder_singleton", rem_repo)
    monkeypatch.setattr("app.services.productivity.repository._sqlite_singleton", prod_repo)
    monkeypatch.setattr("app.services.chat.repository.chat_repository", chat_repo)
    monkeypatch.setattr(profile_service, "db_path", tmp_path / "profiles.db")
    profile_service._init_sqlite()

    state = {"user": USER_A}

    async def _override_user():
        return state["user"]

    app.dependency_overrides[get_current_user] = _override_user
    with TestClient(app) as client:
        yield {
            "client": client,
            "rem_repo": rem_repo,
            "prod_repo": prod_repo,
            "chat_repo": chat_repo,
            "set_user": lambda u: state.__setitem__("user", u),
        }
    app.dependency_overrides.pop(get_current_user, None)


# ======================================================================
# 1. Timezone, Quiet Hours & Recurrence Math
# ======================================================================
def test_timezone_dst_and_quiet_hours_wrap():
    assert resolve_zoneinfo("Invalid/Nonexistent_TZ").key == "UTC"
    assert resolve_zoneinfo("Africa/Nairobi").key == "Africa/Nairobi"

    # Quiet hours overnight wrap: 22:00 to 07:00 in America/New_York (EST = UTC-5 in Jan)
    prefs = NotificationPreferences(
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
        timezone="America/New_York",
    )
    # 2026-01-15 23:30 EST == 2026-01-16 04:30 UTC
    assert is_within_quiet_hours(datetime(2026, 1, 16, 4, 30, tzinfo=timezone.utc), prefs) is True
    # 2026-01-15 06:15 EST == 2026-01-15 11:15 UTC
    assert is_within_quiet_hours(datetime(2026, 1, 15, 11, 15, tzinfo=timezone.utc), prefs) is True
    # 2026-01-15 10:00 EST == 2026-01-15 15:00 UTC
    assert is_within_quiet_hours(datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc), prefs) is False

    # DST Spring Forward in America/New_York (2026-03-08 02:00 -> 03:00): wall clock 07:00 stays 07:00 local
    rule_daily = RecurrenceRule(frequency=RecurrenceFrequency.daily, interval=1, time_of_day="07:00")
    before_dst_utc = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)  # 07:00 EST (-05:00)
    next_dst_utc = compute_next_occurrence(before_dst_utc, rule_daily, "America/New_York", now_utc=before_dst_utc)
    assert next_dst_utc == datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc)  # 07:00 EDT (-04:00)

    # Monthly 31st clamps cleanly to Feb 28 then restores Mar 31
    rule_monthly = RecurrenceRule(frequency=RecurrenceFrequency.monthly, interval=1, day_of_month=31, time_of_day="09:00")
    jan31 = datetime(2026, 1, 31, 9, 0, tzinfo=timezone.utc)
    feb_occ = compute_next_occurrence(jan31, rule_monthly, "UTC", now_utc=jan31)
    assert feb_occ == datetime(2026, 2, 28, 9, 0, tzinfo=timezone.utc)
    mar_occ = compute_next_occurrence(feb_occ, rule_monthly, "UTC", now_utc=feb_occ)
    assert mar_occ == datetime(2026, 3, 31, 9, 0, tzinfo=timezone.utc)

    # Weekdays skips Sat/Sun
    rule_wd = RecurrenceRule(frequency=RecurrenceFrequency.weekdays, interval=1, time_of_day="08:30")
    friday = datetime(2026, 11, 27, 8, 30, tzinfo=timezone.utc)  # Friday
    mon_occ = compute_next_occurrence(friday, rule_wd, "UTC", now_utc=friday)
    assert mon_occ == datetime(2026, 11, 30, 8, 30, tzinfo=timezone.utc)  # Monday

    # Missed downtime gap skips intermediate days when skip_missed=True
    long_downtime_now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    jumped = compute_next_occurrence(before_dst_utc, rule_daily, "UTC", now_utc=long_downtime_now, skip_missed=True)
    assert jumped is not None and jumped > long_downtime_now


# ======================================================================
# 2. RFC 8291 Web Push Encryption & VAPID Security
# ======================================================================
@pytest.mark.asyncio
async def test_web_push_crypto_roundtrip_and_status_handling(monkeypatch):
    keys = generate_vapid_keypair()
    assert len(keys["public_key"]) > 60
    assert len(keys["private_key"]) > 30

    # Simulate client UA P-256 ECDH keypair + 16-byte auth secret
    ua_priv = ec.generate_private_key(ec.SECP256R1())
    ua_pub_raw = ua_priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    p256dh = _b64url_encode(ua_pub_raw)
    auth_secret = _b64url_encode(b"0123456789abcdef")

    payload = {"title": "Study Session", "body": "Deep work starts now", "url": "/reminders"}
    encrypted = encrypt_web_push_payload(json.dumps(payload).encode("utf-8"), p256dh, auth_secret)
    decrypted = decrypt_web_push_payload(encrypted, ua_priv, auth_secret)
    assert json.loads(decrypted.decode("utf-8")) == payload

    # Mock transport testing 201, 410 Gone, 503 Retryable
    responses = iter([201, 410, 503])

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Content-Encoding"] == "aes128gcm"
        assert request.headers["Authorization"].startswith("vapid t=")
        assert f"k={keys['public_key']}" in request.headers["Authorization"]
        code = next(responses)
        return httpx.Response(status_code=code)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as mock_http:
        monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", keys["public_key"])
        monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", keys["private_key"])
        svc = WebPushService(settings=settings, http_client=mock_http)

        r1 = await svc.send_push("https://fcm.googleapis.com/fcm/send/sub1", p256dh, auth_secret, payload)
        assert r1.success is True and r1.status_code == 201

        r2 = await svc.send_push("https://fcm.googleapis.com/fcm/send/sub2", p256dh, auth_secret, payload)
        assert r2.success is False and r2.expired_subscription is True and r2.retryable is False

        r3 = await svc.send_push("https://fcm.googleapis.com/fcm/send/sub3", p256dh, auth_secret, payload)
        assert r3.success is False and r3.expired_subscription is False and r3.retryable is True


# ======================================================================
# 3. API CRUD, Multi-User Ownership Isolation & VAPID Key Safety
# ======================================================================
def test_reminder_api_crud_isolation_and_vapid_safety(isolated_env, monkeypatch):
    client: TestClient = isolated_env["client"]
    set_user = isolated_env["set_user"]
    keys = generate_vapid_keypair()
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", keys["public_key"])
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", keys["private_key"])

    # VAPID endpoint exposes public key ONLY and never leaks private key
    vapid_resp = client.get("/api/v1/notifications/push/vapid-public-key")
    assert vapid_resp.status_code == 200
    body_json = vapid_resp.json()
    assert body_json["configured"] is True
    assert body_json["public_key"] == keys["public_key"]
    assert keys["private_key"] not in json.dumps(body_json)

    # Create reminder as User A
    future_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    create_resp = client.post(
        "/api/v1/reminders",
        json={
            "title": "Submit project milestones",
            "description": "Attach PDF deliverable",
            "trigger_at": future_iso,
            "timezone": "Africa/Nairobi",
            "priority": "high",
            "is_alarm": True,
            "sound_key": "bell",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    rem = create_resp.json()
    rem_id = rem["id"]
    assert rem["is_alarm"] is True
    assert rem["timezone"] == "Africa/Nairobi"

    # Push subscription omits auth_secret in public response
    sub_resp = client.post(
        "/api/v1/notifications/push/subscribe",
        json={
            "endpoint": "https://push.example.com/sub/abc1234567",
            "keys": {"p256dh": "B" * 87, "auth": "A" * 22},
            "device_label": "Pixel Phone",
        },
    )
    assert sub_resp.status_code == 201, sub_resp.text
    assert "auth_secret" not in sub_resp.json()
    assert "auth" not in sub_resp.json()

    # Switch to User B -> strict isolation enforced
    set_user(USER_B)
    assert client.get("/api/v1/reminders").json()["total"] == 0
    assert client.get(f"/api/v1/reminders/{rem_id}").status_code == 404
    assert client.post(f"/api/v1/reminders/{rem_id}/complete").status_code == 404
    assert client.post(f"/api/v1/reminders/{rem_id}/snooze", json={"snooze_minutes": 15}).status_code == 404
    assert client.delete(f"/api/v1/reminders/{rem_id}").status_code == 404
    assert client.get("/api/v1/notifications/push/subscriptions").json()["total"] == 0

    # Back to User A -> snooze, reschedule, complete, cancel lifecycle
    set_user(USER_A)
    snooze_resp = client.post(f"/api/v1/reminders/{rem_id}/snooze", json={"snooze_minutes": 15})
    assert snooze_resp.status_code == 200
    assert snooze_resp.json()["status"] == "snoozed"
    assert snooze_resp.json()["snooze_count"] == 1

    reschedule_iso = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    resc_resp = client.post(
        f"/api/v1/reminders/{rem_id}/reschedule",
        json={"trigger_at": reschedule_iso, "timezone": "UTC"},
    )
    assert resc_resp.status_code == 200
    assert resc_resp.json()["status"] == "scheduled"

    # Notification Center test-push, read-all, and delivery logs
    test_push_resp = client.post("/api/v1/notifications/test-push")
    assert test_push_resp.status_code == 200
    notif_id = test_push_resp.json()["notification"]["id"]

    notif_list_resp = client.get("/api/v1/notifications?process_due=false")
    assert notif_list_resp.status_code == 200
    assert notif_list_resp.json()["unread_count"] == 1

    # User B cannot mark User A's notification read
    set_user(USER_B)
    assert client.post(f"/api/v1/notifications/{notif_id}/read").status_code == 404

    set_user(USER_A)
    assert client.post("/api/v1/notifications/read-all").json()["marked_read"] >= 1
    assert client.get("/api/v1/notifications?process_due=false").json()["unread_count"] == 0

    comp_resp = client.post(f"/api/v1/reminders/{rem_id}/complete")
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "completed"


def test_gdpr_export_includes_reminders(isolated_env):
    client: TestClient = isolated_env["client"]
    future_iso = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    client.post("/api/v1/reminders", json={"title": "GDPR Export Reminder", "trigger_at": future_iso})
    export_resp = client.post("/api/v1/auth/export")
    assert export_resp.status_code == 200, export_resp.text
    payload = export_resp.json()
    assert any(r["title"] == "GDPR Export Reminder" for r in payload.get("reminders", []))


# ======================================================================
# 4. Scheduler Execution, Deduping, Quiet Hours, Lockscreen & Retries
# ======================================================================
@pytest.mark.asyncio
async def test_scheduler_dedupe_quiet_hours_retries_and_recurrence(isolated_env, monkeypatch):
    rem_repo: SQLiteReminderRepository = isolated_env["rem_repo"]
    keys = generate_vapid_keypair()
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", keys["public_key"])
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", keys["private_key"])

    ua_priv = ec.generate_private_key(ec.SECP256R1())
    p256dh = _b64url_encode(
        ua_priv.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
    )
    auth_secret = _b64url_encode(b"secret1234567890")

    from app.models.reminders import PushSubscriptionCreate, PushSubscriptionKeys

    sub = await rem_repo.upsert_push_subscription(
        USER_A.id,
        PushSubscriptionCreate(
            endpoint="https://push.example.com/sub/expired410",
            keys=PushSubscriptionKeys(p256dh=p256dh, auth=auth_secret),
            device_label="Laptop Browser",
        ),
    )

    now = datetime(2026, 11, 25, 23, 30, tzinfo=timezone.utc)
    past_due = now - timedelta(minutes=12)  # > 5 min missed window

    rem = await rem_repo.create_reminder(
        USER_A.id,
        ReminderCreate(
            title="Private Medical Check",
            description="Sensitive clinic appointment",
            trigger_at=past_due,
            timezone="UTC",
            recurrence_rule=RecurrenceRule(frequency=RecurrenceFrequency.daily, interval=1, time_of_day="23:18"),
            recurrence_text="Daily at 23:18 UTC",
            priority=ReminderPriority.normal,
            is_alarm=False,
        ),
    )

    # A) During quiet hours (22:00-07:00), push & audio are suppressed while in-app notice is still saved with missed flag
    quiet_prefs = NotificationPreferences(
        in_app_notifications_enabled=True,
        browser_push_enabled=True,
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
        timezone="UTC",
        hide_sensitive_lockscreen=True,
    )
    processor = ReminderProcessor(settings=settings)
    notif = await processor.process_single_reminder(rem_repo, rem, quiet_prefs, [sub], now_utc=now)
    assert notif is not None
    assert notif.metadata["suppress_audio"] is True
    assert notif.metadata["missed_window"] is True
    assert "Missed schedule" in (notif.body or "")

    # Lock-screen privacy masking hides sensitive reminder details
    masked_push = build_push_payload(rem, notif.id, quiet_prefs)
    assert "Medical" not in masked_push["title"]
    assert "clinic" not in masked_push["body"]

    # Repeating processing for the same occurrence does NOT create duplicate notification
    await processor.process_single_reminder(rem_repo, rem, quiet_prefs, [sub], now_utc=now)
    notifs, total, _ = await rem_repo.list_notifications(USER_A.id)
    assert total == 1

    # Verify recurrence advanced to future date
    updated_rem = await rem_repo.get_reminder(USER_A.id, rem.id)
    assert updated_rem is not None
    assert updated_rem.status == ReminderStatus.scheduled
    assert updated_rem.trigger_at > now

    # B) Active push outside quiet hours -> 410 invalidates subscription automatically
    def _gone_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=410)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_gone_handler)) as mock_http:
        proc2 = ReminderProcessor(
            push_service=WebPushService(settings=settings, http_client=mock_http),
            settings=settings,
        )
        rem2 = await rem_repo.create_reminder(
            USER_A.id,
            ReminderCreate(title="Hydrate", trigger_at=now - timedelta(minutes=1), timezone="UTC"),
        )
        active_prefs = NotificationPreferences(browser_push_enabled=True, quiet_hours_enabled=False, timezone="UTC")
        await proc2.process_single_reminder(rem_repo, rem2, active_prefs, [sub], now_utc=now)

        subs_after = await rem_repo.list_push_subscriptions(USER_A.id, active_only=False)
        assert subs_after[0].is_active is False
        logs = await rem_repo.list_delivery_logs(USER_A.id, reminder_id=rem2.id)
        assert any(log.status == DeliveryLogStatus.expired_subscription for log in logs)

    # C) Transient 503 push failure triggers retry backoff scheduling
    sub2 = await rem_repo.upsert_push_subscription(
        USER_A.id,
        PushSubscriptionCreate(
            endpoint="https://push.example.com/sub/flaky503",
            keys=PushSubscriptionKeys(p256dh=p256dh, auth=auth_secret),
        ),
    )

    def _retry_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_retry_handler)) as retry_http:
        proc3 = ReminderProcessor(
            push_service=WebPushService(settings=settings, http_client=retry_http),
            settings=settings,
        )
        rem3 = await rem_repo.create_reminder(
            USER_A.id,
            ReminderCreate(title="Call mentor", trigger_at=now - timedelta(seconds=30), timezone="UTC"),
        )
        await proc3.process_single_reminder(rem_repo, rem3, active_prefs, [sub2], now_utc=now)
        retrying = await rem_repo.get_reminder(USER_A.id, rem3.id)
        assert retrying is not None
        assert retrying.status == ReminderStatus.due
        assert retrying.delivery_attempts == 1
        assert retrying.next_retry_at is not None and retrying.next_retry_at > now


# ======================================================================
# 5. Conversational Reminder Creation, Clarity, Failures & Chat SSE
# ======================================================================
@pytest.mark.asyncio
async def test_conversational_reminder_nlu_all_examples_and_guards(isolated_env):
    rem_repo: SQLiteReminderRepository = isolated_env["rem_repo"]
    svc = ConversationalReminderService()
    prefs = NotificationPreferences(timezone="America/New_York", default_snooze_minutes=15)
    # Wednesday Nov 25 2026 10:00 AM EST (15:00 UTC)
    ref_now = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)

    examples = [
        ("Remind me at 4 PM to continue working on AUREN.", "Continue working on AUREN", False),
        ("Remind me tomorrow morning to review my projects.", "Review my projects", False),
        ("Set a reminder for Friday at 10 AM to attend my meeting.", "Attend my meeting", False),
        ("Remind me in 30 minutes to check something.", "Check something", False),
        ("Remind me every day at 7 AM to review my priorities.", "Review my priorities", True),
        ("Remind me every Sunday evening to plan the coming week.", "Plan the coming week", True),
        ("Remind me on the 1st of every month to review my finances.", "Review my finances", True),
    ]

    for prompt_text, expected_title, expected_recurring in examples:
        assert is_reminder_intent(prompt_text) is True
        outcome = await svc.handle_user_message(USER_A.id, prompt_text, rem_repo, prefs, now_utc=ref_now)
        assert outcome.handled is True
        assert outcome.status == "created", f"Failed for prompt: {prompt_text} -> {outcome}"
        assert outcome.reminder is not None
        assert expected_title.lower() in outcome.reminder.title.lower()
        assert outcome.reminder.timezone == "America/New_York"
        if expected_recurring:
            assert outcome.reminder.recurrence_rule is not None

    # Ambiguous phrasing MUST ask for clarification and create ZERO DB rows
    before_items, before_count = await rem_repo.list_reminders(USER_A.id)
    ambig = await svc.handle_user_message(USER_A.id, "Remind me tomorrow to submit paperwork", rem_repo, prefs, now_utc=ref_now)
    assert ambig.status == "clarification_needed"
    assert ambig.reminder is None
    assert ambig.clarification_question
    _, after_count = await rem_repo.list_reminders(USER_A.id)
    assert after_count == before_count

    # DB failure honesty: never claims created when repository raises DatabaseError
    class _FailingRepo:
        async def list_reminders(self, **kwargs):
            return [], 0

        async def create_reminder(self, **kwargs):
            raise DatabaseError("simulated write outage")

    failed = await svc.handle_user_message(USER_A.id, "Remind me at 6 PM to call Dad", _FailingRepo(), prefs, now_utc=ref_now)  # type: ignore[arg-type]
    assert failed.status == "failed"
    assert failed.reminder is None
    assert "NOT saved" in (failed.system_instruction or "")

    # Natural conversation snooze -> reschedule -> complete -> cancel
    snoozed = await svc.handle_user_message(USER_A.id, "Snooze my AUREN reminder for 20 minutes", rem_repo, prefs, now_utc=ref_now)
    assert snoozed.status == "snoozed"
    rescheduled = await svc.handle_user_message(USER_A.id, "Reschedule my AUREN reminder to 5:30 PM", rem_repo, prefs, now_utc=ref_now)
    assert rescheduled.status == "rescheduled"
    completed = await svc.handle_user_message(USER_A.id, "Complete my check something reminder", rem_repo, prefs, now_utc=ref_now)
    assert completed.status == "completed"
    cancelled = await svc.handle_user_message(USER_A.id, "Cancel my finances reminder", rem_repo, prefs, now_utc=ref_now)
    assert cancelled.status == "cancelled"


def test_chat_stream_persists_conversational_reminder_and_emits_sse(isolated_env, monkeypatch):
    client: TestClient = isolated_env["client"]
    monkeypatch.setattr(chat_service, "_get_provider", lambda: _DummyChatProvider())

    conv_resp = client.post("/api/v1/chat/conversations", json={"title": "Reminders Test"})
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    with client.stream(
        "POST",
        "/api/v1/chat/completions",
        json={
            "conversation_id": conv_id,
            "message": "Remind me in 45 minutes to check deployment logs",
            "timezone": "Africa/Nairobi",
            "idempotency_key": f"rem-test-{uuid.uuid4().hex}",
        },
    ) as stream_resp:
        assert stream_resp.status_code == 200
        raw_sse = stream_resp.read().decode("utf-8")

    assert "event: reminder_action" in raw_sse
    assert '"action": "created"' in raw_sse
    rem_list = client.get("/api/v1/reminders").json()
    assert rem_list["total"] == 1
    assert "deployment logs" in rem_list["items"][0]["title"].lower()
    assert rem_list["items"][0]["timezone"] == "Africa/Nairobi"


# ======================================================================
# 6. Task Integration: Distinct Deadline vs Reminder, Dedupe & Suppression
# ======================================================================
def test_task_reminder_integration_dedupe_reschedule_and_suppress(isolated_env):
    client: TestClient = isolated_env["client"]

    due_dt = datetime.now(timezone.utc) + timedelta(days=2)
    task_resp = client.post(
        "/api/v1/tasks",
        json={
            "title": "Finish quarterly report",
            "priority": "high",
            "due_date": due_dt.isoformat(),
            "reminder_mode": "before_due",
            "reminder_offset_minutes": 60,
            "reminder_is_alarm": True,
            "reminder_timezone": "Africa/Nairobi",
        },
    )
    assert task_resp.status_code == 201, task_resp.text
    task_id = task_resp.json()["id"]

    # Reminder created 60 mins BEFORE deadline, distinct from due_date
    linked = client.get(f"/api/v1/tasks/{task_id}/reminders").json()
    assert linked["total"] == 1
    rem_item = linked["items"][0]
    assert rem_item["reminder_type"] == "task_before_due"
    assert rem_item["is_alarm"] is True
    trigger_parsed = datetime.fromisoformat(rem_item["trigger_at"].replace("Z", "+00:00"))
    assert abs((due_dt - trigger_parsed).total_seconds() - 3600) < 5

    # Updating with identical before_due mode does NOT create a duplicate reminder
    upd_same = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"reminder_mode": "before_due", "reminder_offset_minutes": 30},
    )
    assert upd_same.status_code == 200
    assert client.get(f"/api/v1/tasks/{task_id}/reminders").json()["total"] == 1

    # Changing task due_date shifts linked reminder automatically
    new_due = due_dt + timedelta(hours=5)
    client.patch(f"/api/v1/tasks/{task_id}", json={"due_date": new_due.isoformat()})
    shifted = client.get(f"/api/v1/tasks/{task_id}/reminders").json()["items"][0]
    shifted_trigger = datetime.fromisoformat(shifted["trigger_at"].replace("Z", "+00:00"))
    assert shifted_trigger > trigger_parsed

    # Completing task suppresses future task-linked reminders
    comp = client.post(f"/api/v1/tasks/{task_id}/status?new_status=completed")
    assert comp.status_code == 200
    suppressed = client.get(f"/api/v1/tasks/{task_id}/reminders").json()["items"][0]
    assert suppressed["status"] == "cancelled"


# ======================================================================
# 7. Supabase Adapter & Repository Selection Safety
# ======================================================================
@pytest.mark.asyncio
async def test_supabase_reminder_adapter_and_factory_selection(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_REPOSITORY_TYPE", "auto")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "anon-key-placeholder")

    # Non-3-part local test tokens safely fall back to SQLite instead of failing PostgREST
    assert isinstance(get_reminder_repository(user_token="local-test-token"), SQLiteReminderRepository)
    # 3-part JWT triggers RLS-backed SupabaseReminderRepository
    assert isinstance(get_reminder_repository(user_token="hdr.payload.sig"), SupabaseReminderRepository)

    rem_uuid = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    def _sb_handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Bearer hdr.payload.sig"
        assert req.headers["apikey"] == "anon-key-placeholder"
        return httpx.Response(
            status_code=201,
            json=[
                {
                    "id": rem_uuid,
                    "user_id": str(USER_A.id),
                    "task_id": None,
                    "project_id": None,
                    "goal_id": None,
                    "title": "Supabase Synced",
                    "description": None,
                    "reminder_type": "general",
                    "trigger_at": now_iso,
                    "original_trigger_at": now_iso,
                    "timezone": "UTC",
                    "recurrence_rule": None,
                    "recurrence_text": None,
                    "status": "scheduled",
                    "priority": "normal",
                    "is_alarm": False,
                    "sound_key": None,
                    "snoozed_until": None,
                    "snooze_count": 0,
                    "last_triggered_at": None,
                    "next_retry_at": None,
                    "delivery_attempts": 0,
                    "max_delivery_attempts": 5,
                    "escalation_count": 0,
                    "completed_at": None,
                    "cancelled_at": None,
                    "source": "manual",
                    "dedupe_key": None,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(_sb_handler)) as sb_http:
        repo = SupabaseReminderRepository(
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-key-placeholder",
            user_token="hdr.payload.sig",
            http_client=sb_http,
        )
        created = await repo.create_reminder(
            USER_A.id,
            ReminderCreate(title="Supabase Synced", trigger_at=datetime.now(timezone.utc)),
        )
        assert str(created.id) == rem_uuid
        assert created.title == "Supabase Synced"
