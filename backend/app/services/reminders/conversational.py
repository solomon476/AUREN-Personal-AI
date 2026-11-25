"""Conversational Natural-Language Reminder Engine for AUREN Personal AI.

Extracts reminder intent, title/description, date, time, timezone, and recurrence from natural language.
Handles:
- One-time times ("at 4 PM", "tomorrow morning", "Friday at 10 AM", "in 30 minutes")
- Recurring schedules ("every day at 7 AM", "every Sunday evening", "on the 1st of every month")
- Alarm intents ("set an alarm for 6:30 AM")
- Conversational management ("snooze ... for 15 minutes", "cancel ...", "complete ...", "reschedule ...")
- Explicit ambiguity detection BEFORE scheduling so AUREN clarifies vague times instead of guessing.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.models.reminders import (
    NotificationPreferences,
    RecurrenceFrequency,
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
from app.services.reminders.time_utils import ensure_utc, format_local_datetime, resolve_zoneinfo

logger = logging.getLogger(__name__)

WEEKDAY_MAP: Dict[str, int] = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

REMINDER_TRIGGER_KEYWORDS = (
    "remind me",
    "set a reminder",
    "set reminder",
    "create a reminder",
    "add a reminder",
    "schedule a reminder",
    "set an alarm",
    "set alarm",
    "wake me up",
    "alarm for",
    "snooze",
    "reschedule my reminder",
    "reschedule the reminder",
    "cancel my reminder",
    "cancel the reminder",
    "delete my reminder",
    "delete the reminder",
    "complete my reminder",
    "complete the reminder",
    "edit my reminder",
    "edit the reminder",
    "change my reminder",
    "update my reminder",
    "my reminders",
    "what reminders",
)


def is_reminder_intent(message: str) -> bool:
    lower = (message or "").lower()
    if any(kw in lower for kw in REMINDER_TRIGGER_KEYWORDS):
        return True
    # Also catch phrases like "remind me in ...", "move my ... reminder", "mark ... reminder done"
    if "reminder" in lower and any(
        verb in lower for verb in ("snooze", "cancel", "reschedule", "move", "complete", "done", "finish", "edit", "change", "update", "list", "show")
    ):
        return True
    return False


@dataclass
class ConversationalReminderOutcome:
    """Result of evaluating and (when valid & unambiguous) executing a reminder turn."""

    handled: bool = False
    status: str = "none"  # 'created' | 'updated' | 'snoozed' | 'completed' | 'cancelled' | 'rescheduled' | 'clarification_needed' | 'failed' | 'listed'
    reminder: Optional[ReminderModel] = None
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    error_detail: Optional[str] = None
    system_instruction: Optional[str] = None
    summary_text: Optional[str] = None


def _parse_hhmm_tuple(hhmm: str, default: Tuple[int, int] = (9, 0)) -> Tuple[int, int]:
    try:
        parts = hhmm.strip().split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return default


def _parse_time_expression(text_lower: str, prefs: NotificationPreferences) -> Tuple[Optional[Tuple[int, int]], bool, Optional[str]]:
    """Extract (hour, minute) 24-hour time if explicit or period-qualified.

    Returns (time_tuple, is_ambiguous_ampm, ambiguity_reason).
    """
    # 1. Explicit HH:MM am/pm or H am/pm (e.g. "4 PM", "10 AM", "7:30 pm", "12:15am")
    ampm_match = re.search(r"\b(?:at|for|@)?\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", text_lower)
    if ampm_match:
        hr = int(ampm_match.group(1))
        mn = int(ampm_match.group(2) or "0")
        mer = ampm_match.group(3).replace(".", "").lower()
        if 1 <= hr <= 12 and 0 <= mn <= 59:
            if mer == "am":
                hr_24 = 0 if hr == 12 else hr
            else:
                hr_24 = 12 if hr == 12 else hr + 12
            return (hr_24, mn), False, None

    # 2. Explicit 24h HH:MM (e.g. "at 16:00", "at 07:30")
    t24_match = re.search(r"\b(?:at|for|@)\s*([01]?\d|2[0-3]):([0-5]\d)\b", text_lower)
    if t24_match:
        hr = int(t24_match.group(1))
        mn = int(t24_match.group(2))
        if 1 <= hr <= 12 and hr < 13 and "0" not in t24_match.group(1)[:1] and hr != 0:
            # e.g. "at 7:30" without am/pm is slightly ambiguous unless >= 13 or leading zero "07:30"
            if any(p in text_lower for p in ("morning", "evening", "night", "afternoon")):
                if any(p in text_lower for p in ("evening", "night", "afternoon")) and hr < 12:
                    hr += 12
                return (hr, mn), False, None
            return None, True, f"Time {hr}:{mn:02d} is missing AM or PM."
        return (hr, mn), False, None

    # 3. Bare hour without AM/PM (e.g. "at 7" -> ambiguous unless "morning"/"evening"/"night" is stated)
    bare_hr_match = re.search(r"\b(?:at|for|@)\s*(\d{1,2})\b(?!(?:\s*(?:min|minute|minutes|hr|hour|hours|day|days|st|nd|rd|th)))", text_lower)
    if bare_hr_match:
        hr = int(bare_hr_match.group(1))
        if 0 <= hr <= 23:
            if hr >= 13 or hr == 0:
                return (hr, 0), False, None
            if "morning" in text_lower:
                return (0 if hr == 12 else hr, 0), False, None
            if any(p in text_lower for p in ("afternoon", "evening", "night")):
                return (12 if hr == 12 else hr + 12, 0), False, None
            return None, True, f"'{bare_hr_match.group(0).strip()}' could be {hr}:00 AM or {hr}:00 PM."

    # 4. Named periods of day
    if re.search(r"\bnoon\b|\bmidday\b", text_lower):
        return (12, 0), False, None
    if re.search(r"\bmidnight\b", text_lower):
        return (0, 0), False, None
    if re.search(r"\bmorning\b", text_lower):
        # Default morning reminder hour (09:00 or configured daily_briefing_time if in morning)
        bh, bm = _parse_hhmm_tuple(prefs.daily_briefing_time, (9, 0))
        if 5 <= bh <= 11:
            return (max(bh, 8) if prefs.daily_briefing_time == "08:00" else bh, bm), False, None
        return (9, 0), False, None
    if re.search(r"\bafternoon\b", text_lower):
        return (14, 0), False, None
    if re.search(r"\b(evening|tonight)\b", text_lower):
        eh, em = _parse_hhmm_tuple(prefs.evening_review_time, (19, 0))
        return (eh, em), False, None
    if re.search(r"\bnight\b", text_lower):
        return (21, 0), False, None

    return None, False, None


def _extract_clean_title(raw_message: str) -> str:
    """Extract clean reminder action title from conversational phrasing."""
    text = raw_message.strip()

    # Prefer capturing everything after "to <action>" when pattern matches reminder framing
    to_match = re.search(
        r"(?:remind\s+me|set\s+(?:a|an)\s+(?:reminder|alarm)|wake\s+me\s+up|alarm\s+me)\b.*?\b(?:to|about|that)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if to_match:
        candidate = to_match.group(1).strip().rstrip(".")
        if candidate:
            return candidate[0].upper() + candidate[1:]

    # Also support "Remind me to <action> at <time> / tomorrow / in X minutes"
    to_first = re.search(
        r"(?:remind\s+me|set\s+(?:a|an)\s+(?:reminder|alarm))\s+(?:to|about)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if to_first:
        candidate = to_first.group(1).strip()
        # Strip trailing temporal expressions
        candidate = re.sub(
            r"\s+(?:in\s+\d+\s+(?:minutes?|mins?|hours?|hrs?|days?)|every\s+.+|on\s+the\s+\d+(?:st|nd|rd|th).+|tomorrow.*|today.*|tonight.*|(?:this|next)\s+(?:mon|tue|wed|thu|fri|sat|sun)\w*.*|(?:at|for)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*\.?$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip().rstrip(".")
        if candidate:
            return candidate[0].upper() + candidate[1:]

    # Fallback: strip boilerplate prefixes
    stripped = re.sub(
        r"^(?:please\s+)?(?:remind\s+me|set\s+(?:a|an)\s+(?:reminder|alarm)(?:\s+for)?)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip().rstrip(".")
    if stripped:
        return stripped[0].upper() + stripped[1:250]
    return "Personal Reminder"


def _find_matching_reminder(query_text: str, reminders: List[ReminderModel]) -> Optional[ReminderModel]:
    """Find best matching active reminder from user's text by keyword overlap or fallback if unambiguous."""
    lower = query_text.lower()
    active = [r for r in reminders if r.status in (ReminderStatus.scheduled, ReminderStatus.due, ReminderStatus.snoozed)]
    if not active:
        return None

    # Exact / substring match against title
    best: Optional[ReminderModel] = None
    best_score = 0
    stop_words = {
        "the", "my", "a", "an", "reminder", "reminders", "alarm", "to", "for", "at",
        "in", "on", "of", "and", "snooze", "cancel", "delete", "complete", "done",
        "mark", "reschedule", "move", "edit", "change", "update", "by", "minutes",
        "minute", "mins", "min", "hours", "hour", "pm", "am", "tomorrow", "today",
    }
    query_tokens = {w for w in re.findall(r"[a-z0-9]+", lower) if w not in stop_words and len(w) > 1}

    for rem in active:
        title_lower = rem.title.lower()
        if title_lower in lower:
            return rem
        title_tokens = {w for w in re.findall(r"[a-z0-9]+", title_lower) if w not in stop_words and len(w) > 1}
        overlap = len(query_tokens & title_tokens)
        if overlap > best_score:
            best_score = overlap
            best = rem

    if best and best_score > 0:
        return best

    # If user says "snooze that" / "snooze my reminder" with due/snoozed reminder active
    if len(active) == 1:
        return active[0]
    due_or_snoozed = [r for r in active if r.status in (ReminderStatus.due, ReminderStatus.snoozed)]
    if len(due_or_snoozed) == 1:
        return due_or_snoozed[0]

    return None


class ConversationalReminderService:
    """Parses, resolves ambiguity, persists, and confirms natural-language reminder interactions."""

    async def handle_user_message(
        self,
        user_id: UUID,
        message: str,
        repo: BaseReminderRepository,
        prefs: NotificationPreferences,
        now_utc: Optional[datetime] = None,
    ) -> ConversationalReminderOutcome:
        if not is_reminder_intent(message):
            return ConversationalReminderOutcome(handled=False)

        now = ensure_utc(now_utc) if now_utc else datetime.now(timezone.utc)
        tz = resolve_zoneinfo(prefs.timezone)
        local_now = now.astimezone(tz)
        text = message.strip()
        lower = text.lower()

        # Load active reminders for management commands
        existing_reminders, _ = await repo.list_reminders(user_id=user_id, page=1, page_size=100)

        # 1. Management Intents (Snooze, Cancel/Delete, Complete, Reschedule/Edit)
        if re.search(r"\bsnooze\b", lower):
            return await self._handle_snooze(user_id, text, lower, repo, prefs, now, existing_reminders)

        if re.search(r"\b(cancel|delete|remove)\b", lower) and "reminder" in lower:
            return await self._handle_cancel(user_id, text, repo, existing_reminders)

        if re.search(r"\b(complete|finish|finished|done|dismiss)\b", lower) and "reminder" in lower:
            return await self._handle_complete(user_id, text, repo, existing_reminders)

        if re.search(r"\b(reschedule|move|postpone|edit|change|update)\b", lower) and "reminder" in lower:
            return await self._handle_reschedule_or_edit(user_id, text, lower, repo, prefs, now, local_now, existing_reminders)

        if re.search(r"\b(what reminders|my reminders|list reminders|show .*reminders)\b", lower):
            active = [r for r in existing_reminders if r.status in (ReminderStatus.scheduled, ReminderStatus.due, ReminderStatus.snoozed)]
            lines = [
                f"- {r.title} | Status: {r.status.value} | Scheduled: {format_local_datetime(r.trigger_at, r.timezone)}"
                + (f" ({r.recurrence_text})" if r.recurrence_text else "")
                for r in active[:15]
            ]
            ctx = (
                "Active persisted reminders for user:\n" + ("\n".join(lines) if lines else "(No active reminders currently scheduled)")
            )
            return ConversationalReminderOutcome(
                handled=True,
                status="listed",
                system_instruction=ctx,
            )

        # 2. Creation Intent ("Remind me ...", "Set a reminder ...", "Set an alarm ...")
        if re.search(r"\b(remind\s+me|set\s+(?:a|an)\s+(?:reminder|alarm)|wake\s+me\s+up|alarm\s+(?:me|for))\b", lower):
            return await self._handle_create(user_id, text, lower, repo, prefs, now, local_now, tz)

        return ConversationalReminderOutcome(handled=False)

    async def _handle_snooze(
        self,
        user_id: UUID,
        text: str,
        lower: str,
        repo: BaseReminderRepository,
        prefs: NotificationPreferences,
        now_utc: datetime,
        reminders: List[ReminderModel],
    ) -> ConversationalReminderOutcome:
        target = _find_matching_reminder(text, reminders)
        if not target:
            return ConversationalReminderOutcome(
                handled=True,
                status="clarification_needed",
                clarification_question="Which reminder would you like to snooze? Please mention its title.",
                system_instruction="[REMINDER LOOKUP]: Could not identify a single active reminder to snooze. Ask user which reminder they mean without claiming any change succeeded.",
            )

        # Extract snooze duration
        dur_match = re.search(r"\b(\d+)\s*(minutes?|mins?|hours?|hrs?)\b", lower)
        snooze_mins = prefs.default_snooze_minutes
        if dur_match:
            val = int(dur_match.group(1))
            unit = dur_match.group(2)
            snooze_mins = val * 60 if unit.startswith("h") else val
        snooze_mins = max(1, min(10080, snooze_mins))
        target_utc = now_utc + timedelta(minutes=snooze_mins)

        try:
            updated = await repo.snooze_reminder(user_id=user_id, reminder_id=target.id, snoozed_until=target_utc)
            if not updated:
                raise RuntimeError("Reminder not found or update failed.")
        except Exception as exc:
            return ConversationalReminderOutcome(
                handled=True,
                status="failed",
                error_detail=str(exc),
                system_instruction=f"[VERIFIED REMINDER DATABASE RESULT: FAILED] Snoozing '{target.title}' failed ({exc}). Do NOT claim it was snoozed; tell the user clearly.",
            )

        local_str = format_local_datetime(updated.trigger_at, updated.timezone)
        return ConversationalReminderOutcome(
            handled=True,
            status="snoozed",
            reminder=updated,
            summary_text=f"Snoozed '{updated.title}' for {snooze_mins} minute(s) until {local_str}.",
            system_instruction=(
                f"[VERIFIED REMINDER DATABASE RESULT: SUCCEEDED]\n"
                f"Action: SNOOZED\nReminder ID: {updated.id}\nTitle: {updated.title}\n"
                f"Next Trigger: {local_str}\nSnooze Count: {updated.snooze_count}\n"
                f"Confirm accurately to the user using only these saved facts."
            ),
        )

    async def _handle_cancel(
        self,
        user_id: UUID,
        text: str,
        repo: BaseReminderRepository,
        reminders: List[ReminderModel],
    ) -> ConversationalReminderOutcome:
        target = _find_matching_reminder(text, reminders)
        if not target:
            return ConversationalReminderOutcome(
                handled=True,
                status="clarification_needed",
                clarification_question="Which reminder would you like to cancel? Please specify its name or time.",
                system_instruction="[REMINDER LOOKUP]: Ambiguous or missing reminder target for cancellation. Ask the user to clarify which reminder.",
            )

        try:
            cancelled = await repo.cancel_reminder(user_id=user_id, reminder_id=target.id)
            if not cancelled:
                raise RuntimeError("Cancellation update returned no record.")
        except Exception as exc:
            return ConversationalReminderOutcome(
                handled=True,
                status="failed",
                error_detail=str(exc),
                system_instruction=f"[VERIFIED REMINDER DATABASE RESULT: FAILED] Cancelling '{target.title}' failed ({exc}). Do NOT claim it was cancelled.",
            )

        return ConversationalReminderOutcome(
            handled=True,
            status="cancelled",
            reminder=cancelled,
            summary_text=f"Cancelled reminder '{cancelled.title}'.",
            system_instruction=(
                f"[VERIFIED REMINDER DATABASE RESULT: SUCCEEDED]\n"
                f"Action: CANCELLED\nReminder ID: {cancelled.id}\nTitle: {cancelled.title}\n"
                f"Confirm the reminder has been cancelled."
            ),
        )

    async def _handle_complete(
        self,
        user_id: UUID,
        text: str,
        repo: BaseReminderRepository,
        reminders: List[ReminderModel],
    ) -> ConversationalReminderOutcome:
        target = _find_matching_reminder(text, reminders)
        if not target:
            return ConversationalReminderOutcome(
                handled=True,
                status="clarification_needed",
                clarification_question="Which reminder did you complete?",
                system_instruction="[REMINDER LOOKUP]: Could not match an active reminder to mark completed. Ask the user to clarify.",
            )

        try:
            completed = await repo.complete_reminder(user_id=user_id, reminder_id=target.id)
            if not completed:
                raise RuntimeError("Completion failed.")
        except Exception as exc:
            return ConversationalReminderOutcome(
                handled=True,
                status="failed",
                error_detail=str(exc),
                system_instruction=f"[VERIFIED REMINDER DATABASE RESULT: FAILED] Marking '{target.title}' completed failed ({exc}). Do NOT claim it succeeded.",
            )

        return ConversationalReminderOutcome(
            handled=True,
            status="completed",
            reminder=completed,
            summary_text=f"Completed reminder '{completed.title}'.",
            system_instruction=(
                f"[VERIFIED REMINDER DATABASE RESULT: SUCCEEDED]\n"
                f"Action: COMPLETED\nReminder ID: {completed.id}\nTitle: {completed.title}\n"
                f"Confirm cleanly."
            ),
        )

    async def _handle_reschedule_or_edit(
        self,
        user_id: UUID,
        text: str,
        lower: str,
        repo: BaseReminderRepository,
        prefs: NotificationPreferences,
        now_utc: datetime,
        local_now: datetime,
        reminders: List[ReminderModel],
    ) -> ConversationalReminderOutcome:
        target = _find_matching_reminder(text, reminders)
        if not target:
            return ConversationalReminderOutcome(
                handled=True,
                status="clarification_needed",
                clarification_question="Which reminder would you like to edit or reschedule?",
                system_instruction="[REMINDER LOOKUP]: Ask the user which reminder they want to edit or reschedule.",
            )

        # Check for title edit e.g. "rename ... reminder to X" / "title to X"
        rename_match = re.search(r"\b(?:title|text|name)\s+to\s+[\"']?(.+?)[\"']?$", text, flags=re.IGNORECASE)
        new_title = rename_match.group(1).strip() if rename_match else None

        # Parse new time / date if provided
        parsed_trigger, _, _, _, clarification = self._resolve_schedule_from_text(
            lower=lower, prefs=prefs, now_utc=now_utc, local_now=local_now, default_date_from=target.trigger_at
        )

        if clarification and not new_title:
            return ConversationalReminderOutcome(
                handled=True,
                status="clarification_needed",
                clarification_question=clarification,
                system_instruction=f"[REMINDER CLARIFICATION REQUIRED]: {clarification} Ask the user before modifying '{target.title}'.",
            )

        update_payload = ReminderUpdate(
            title=new_title,
            trigger_at=parsed_trigger,
            timezone=prefs.timezone,
        )
        try:
            updated = await repo.update_reminder(user_id=user_id, reminder_id=target.id, update=update_payload)
            if not updated:
                raise RuntimeError("Reminder update failed.")
        except Exception as exc:
            return ConversationalReminderOutcome(
                handled=True,
                status="failed",
                error_detail=str(exc),
                system_instruction=f"[VERIFIED REMINDER DATABASE RESULT: FAILED] Updating '{target.title}' failed ({exc}). Do NOT claim it succeeded.",
            )

        local_str = format_local_datetime(updated.trigger_at, updated.timezone)
        return ConversationalReminderOutcome(
            handled=True,
            status="rescheduled",
            reminder=updated,
            summary_text=f"Updated '{updated.title}' for {local_str}.",
            system_instruction=(
                f"[VERIFIED REMINDER DATABASE RESULT: SUCCEEDED]\n"
                f"Action: UPDATED/RESCHEDULED\nReminder ID: {updated.id}\nTitle: {updated.title}\n"
                f"Scheduled Time: {local_str}\nConfirm accurately."
            ),
        )

    async def _handle_create(
        self,
        user_id: UUID,
        text: str,
        lower: str,
        repo: BaseReminderRepository,
        prefs: NotificationPreferences,
        now_utc: datetime,
        local_now: datetime,
        tz,
    ) -> ConversationalReminderOutcome:
        title = _extract_clean_title(text)
        trigger_utc, rec_rule, rec_text, is_alarm, clarification = self._resolve_schedule_from_text(
            lower=lower, prefs=prefs, now_utc=now_utc, local_now=local_now
        )

        if clarification or trigger_utc is None:
            q = clarification or f'When would you like to be reminded to "{title}"?'
            return ConversationalReminderOutcome(
                handled=True,
                status="clarification_needed",
                clarification_question=q,
                clarification_options=[
                    "Today in 30 minutes",
                    "Tomorrow morning (9:00 AM)",
                    "Friday at 10:00 AM",
                ],
                system_instruction=(
                    f"[REMINDER AMBIGUITY DETECTED — DO NOT CREATE YET]\n"
                    f"Reason: {q}\n"
                    f"Ask the user to clarify the exact time/date before scheduling. Do NOT claim any reminder was created."
                ),
            )

        priority = ReminderPriority.alarm if is_alarm else prefs.notification_priority_default
        rem_type = ReminderType.alarm if is_alarm else ReminderType.general
        create_in = ReminderCreate(
            title=title,
            description=None,
            reminder_type=rem_type,
            trigger_at=trigger_utc,
            timezone=tz.key,
            recurrence_rule=rec_rule,
            recurrence_text=rec_text,
            priority=priority,
            is_alarm=is_alarm or (prefs.default_reminder_behavior == "alarm"),
            source=ReminderSource.chat,
        )

        try:
            saved = await repo.create_reminder(user_id=user_id, reminder=create_in)
        except Exception as exc:
            logger.error("Failed persisting conversational reminder for user %s: %s", user_id, exc)
            return ConversationalReminderOutcome(
                handled=True,
                status="failed",
                error_detail=str(exc),
                system_instruction=(
                    f"[VERIFIED REMINDER DATABASE RESULT: FAILED]\n"
                    f"Error: {exc}\n"
                    f"CRITICAL: The reminder was NOT saved. Inform the user clearly that saving failed and do NOT claim it was scheduled."
                ),
            )

        local_str = format_local_datetime(saved.trigger_at, saved.timezone)
        rec_info = f" ({saved.recurrence_text})" if saved.recurrence_text else ""
        return ConversationalReminderOutcome(
            handled=True,
            status="created",
            reminder=saved,
            summary_text=f"Saved reminder '{saved.title}' for {local_str}{rec_info}.",
            system_instruction=(
                f"[VERIFIED REMINDER DATABASE RESULT: SUCCEEDED]\n"
                f"Reminder ID: {saved.id}\n"
                f"Title: {saved.title}\n"
                f"Scheduled Time: {local_str}\n"
                f"Timezone: {saved.timezone}\n"
                f"Recurrence: {saved.recurrence_text or 'One-time'}\n"
                f"Alarm Style: {saved.is_alarm}\n"
                f"Confirm concisely to the user using ONLY these exact saved fields."
            ),
        )

    def _resolve_schedule_from_text(
        self,
        lower: str,
        prefs: NotificationPreferences,
        now_utc: datetime,
        local_now: datetime,
        default_date_from: Optional[datetime] = None,
    ) -> Tuple[Optional[datetime], Optional[RecurrenceRule], Optional[str], bool, Optional[str]]:
        """Resolve trigger_at (UTC), recurrence_rule, recurrence_text, is_alarm, and clarification prompt if ambiguous."""
        is_alarm = bool(re.search(r"\balarm\b|\bwake me\b", lower))

        # 1. Relative offset: "in 30 minutes", "in 2 hours", "in 3 days"
        rel_match = re.search(r"\bin\s+(\d+)\s+(minutes?|mins?|hours?|hrs?|days?)\b", lower)
        if rel_match:
            qty = int(rel_match.group(1))
            unit = rel_match.group(2)
            if unit.startswith("m"):
                delta = timedelta(minutes=qty)
            elif unit.startswith("h"):
                delta = timedelta(hours=qty)
            else:
                delta = timedelta(days=qty)
            return now_utc + delta, None, None, is_alarm, None

        time_tuple, is_ambig_ampm, ampm_reason = _parse_time_expression(lower, prefs)
        if is_ambig_ampm:
            return None, None, None, is_alarm, (
                f"{ampm_reason} Could you clarify whether you mean AM or PM?"
            )

        # 2. Recurring Monthly: "on the 1st of every month" / "every month on the 15th"
        monthly_match = re.search(
            r"(?:on\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+every\s+month|every\s+month(?:\s+on\s+the\s+(\d{1,2})(?:st|nd|rd|th)?)?)",
            lower,
        )
        if monthly_match:
            dom = int(monthly_match.group(1) or monthly_match.group(2) or "1")
            dom = max(1, min(31, dom))
            hr, mn = time_tuple if time_tuple else _parse_hhmm_tuple(prefs.daily_briefing_time, (9, 0))
            if not time_tuple and re.search(r"\b(?:evening)\b", lower):
                hr, mn = _parse_hhmm_tuple(prefs.evening_review_time, (19, 0))
            time_str = f"{hr:02d}:{mn:02d}"
            tz = local_now.tzinfo
            # Compute next monthly date matching dom
            import calendar
            year, month = local_now.year, local_now.month
            max_day = calendar.monthrange(year, month)[1]
            candidate_local = local_now.replace(day=min(dom, max_day), hour=hr, minute=mn, second=0, microsecond=0)
            if candidate_local <= local_now:
                next_month = month + 1 if month < 12 else 1
                next_year = year if month < 12 else year + 1
                max_day_next = calendar.monthrange(next_year, next_month)[1]
                candidate_local = candidate_local.replace(
                    year=next_year, month=next_month, day=min(dom, max_day_next)
                )
            rule = RecurrenceRule(
                frequency=RecurrenceFrequency.monthly,
                interval=1,
                day_of_month=dom,
                time_of_day=time_str,
            )
            ordinal = f"{dom}{'st' if dom % 10 == 1 and dom != 11 else 'nd' if dom % 10 == 2 and dom != 12 else 'rd' if dom % 10 == 3 and dom != 13 else 'th'}"
            rec_text = f"{ordinal} of every month at {candidate_local.strftime('%I:%M %p').lstrip('0')}"
            return candidate_local.astimezone(timezone.utc), rule, rec_text, is_alarm, None

        # 3. Recurring Daily: "every day at 7 AM" / "daily at 08:00" / "every morning"
        if re.search(r"\b(every\s+day|everyday|daily|every\s+morning|every\s+evening|every\s+night)\b", lower):
            if "every morning" in lower and not time_tuple:
                time_tuple = _parse_hhmm_tuple(prefs.daily_briefing_time, (9, 0))
            elif "every evening" in lower and not time_tuple:
                time_tuple = _parse_hhmm_tuple(prefs.evening_review_time, (19, 0))
            elif "every night" in lower and not time_tuple:
                time_tuple = (21, 0)

            if not time_tuple:
                return None, None, None, is_alarm, (
                    "What time each day would you like this recurring reminder to trigger?"
                )
            hr, mn = time_tuple
            time_str = f"{hr:02d}:{mn:02d}"
            candidate_local = local_now.replace(hour=hr, minute=mn, second=0, microsecond=0)
            if candidate_local <= local_now:
                candidate_local += timedelta(days=1)
            rule = RecurrenceRule(
                frequency=RecurrenceFrequency.daily,
                interval=1,
                time_of_day=time_str,
            )
            rec_text = f"Every day at {candidate_local.strftime('%I:%M %p').lstrip('0')}"
            return candidate_local.astimezone(timezone.utc), rule, rec_text, is_alarm, None

        # 4. Recurring Weekday: "every Sunday evening", "every Friday at 10 AM"
        every_wd_match = re.search(
            r"\bevery\s+(monday|mon|tuesday|tues?|wednesday|wed|thursday|thurs?|friday|fri|saturday|sat|sunday|sun)\b",
            lower,
        )
        if every_wd_match:
            wd_str = every_wd_match.group(1)
            target_wd = WEEKDAY_MAP[wd_str]
            if not time_tuple:
                return None, None, None, is_alarm, (
                    f"What time every {WEEKDAY_NAMES[target_wd]} should I remind you?"
                )
            hr, mn = time_tuple
            time_str = f"{hr:02d}:{mn:02d}"
            days_ahead = (target_wd - local_now.weekday()) % 7
            candidate_local = (local_now + timedelta(days=days_ahead)).replace(
                hour=hr, minute=mn, second=0, microsecond=0
            )
            if candidate_local <= local_now:
                candidate_local += timedelta(days=7)
            rule = RecurrenceRule(
                frequency=RecurrenceFrequency.weekly,
                interval=1,
                days_of_week=[target_wd],
                time_of_day=time_str,
            )
            rec_text = f"Every {WEEKDAY_NAMES[target_wd]} at {candidate_local.strftime('%I:%M %p').lstrip('0')}"
            return candidate_local.astimezone(timezone.utc), rule, rec_text, is_alarm, None

        # 5. Recurring Weekdays ("every weekday at 8 AM")
        if re.search(r"\bevery\s+weekday\b|\bweekdays\b", lower):
            if not time_tuple:
                return None, None, None, is_alarm, "What time on weekdays should this reminder trigger?"
            hr, mn = time_tuple
            candidate_local = local_now.replace(hour=hr, minute=mn, second=0, microsecond=0)
            while candidate_local <= local_now or candidate_local.weekday() >= 5:
                candidate_local += timedelta(days=1)
            rule = RecurrenceRule(
                frequency=RecurrenceFrequency.weekdays,
                interval=1,
                time_of_day=f"{hr:02d}:{mn:02d}",
            )
            rec_text = f"Weekdays at {candidate_local.strftime('%I:%M %p').lstrip('0')}"
            return candidate_local.astimezone(timezone.utc), rule, rec_text, is_alarm, None

        # 6. Explicit One-Time Date References
        target_local_date = None
        if re.search(r"\btomorrow\b", lower):
            target_local_date = (local_now + timedelta(days=1)).date()
        elif re.search(r"\b(today|tonight|this\s+(?:morning|afternoon|evening))\b", lower):
            target_local_date = local_now.date()
        else:
            wd_match = re.search(
                r"\b(?:on|for|this|next)?\s*(monday|mon|tuesday|tues?|wednesday|wed|thursday|thurs?|friday|fri|saturday|sat|sunday|sun)\b",
                lower,
            )
            if wd_match:
                wd = WEEKDAY_MAP[wd_match.group(1)]
                days_ahead = (wd - local_now.weekday()) % 7
                if days_ahead == 0 and ("next " in lower or (time_tuple and local_now.replace(hour=time_tuple[0], minute=time_tuple[1]) <= local_now)):
                    days_ahead = 7
                target_local_date = (local_now + timedelta(days=days_ahead)).date()
            else:
                iso_date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", lower)
                if iso_date_match:
                    try:
                        target_local_date = datetime.strptime(iso_date_match.group(1), "%Y-%m-%d").date()
                    except ValueError:
                        target_local_date = None

        # If neither date nor time is specified at all -> clarify!
        if target_local_date is None and time_tuple is None:
            return None, None, None, is_alarm, "When would you like to be reminded? Please include a date and time (e.g., today at 4 PM or Friday at 10 AM)."

        # Date specified (e.g. "tomorrow", "Friday"), but NO time or period -> clarify!
        if target_local_date is not None and time_tuple is None:
            day_label = target_local_date.strftime("%A, %b %d")
            return None, None, None, is_alarm, (
                f"What time on {day_label} would you like to be reminded? (For example, 9:00 AM, 2:00 PM, or 7:00 PM)"
            )

        # Time specified without date -> default to today (or tomorrow if already passed today, or target default_date_from for reschedule)
        hr, mn = time_tuple  # type: ignore[misc]
        if target_local_date is None:
            if default_date_from is not None:
                target_local_date = ensure_utc(default_date_from).astimezone(local_now.tzinfo).date()
            else:
                candidate_today = local_now.replace(hour=hr, minute=mn, second=0, microsecond=0)
                if candidate_today <= local_now:
                    target_local_date = (local_now + timedelta(days=1)).date()
                else:
                    target_local_date = local_now.date()

        tz = local_now.tzinfo
        final_local = datetime(
            target_local_date.year, target_local_date.month, target_local_date.day,
            hr, mn, 0, tzinfo=tz
        )
        return final_local.astimezone(timezone.utc), None, None, is_alarm, None

