"""Timezone-aware scheduling, quiet-hours evaluation, and recurrence math for AUREN Reminders."""

import calendar
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.reminders import NotificationPreferences, RecurrenceFrequency, RecurrenceRule


def resolve_zoneinfo(tz_name: Optional[str]) -> ZoneInfo:
    """Resolve an IANA timezone name cleanly, defaulting safely to UTC if unset."""
    candidate = (tz_name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def ensure_utc(dt: datetime, default_tz: str = "UTC") -> datetime:
    """Convert a naive or aware datetime into timezone-aware UTC."""
    if dt.tzinfo is None:
        tz = resolve_zoneinfo(default_tz)
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


def format_local_datetime(dt_utc: datetime, tz_name: str = "UTC") -> str:
    """Format a UTC datetime cleanly in the target IANA timezone."""
    tz = resolve_zoneinfo(tz_name)
    local_dt = ensure_utc(dt_utc).astimezone(tz)
    hour_12 = local_dt.strftime("%I").lstrip("0") or "12"
    minute = local_dt.strftime("%M")
    ampm = local_dt.strftime("%p")
    return f"{local_dt.strftime('%a, %b')} {local_dt.day} at {hour_12}:{minute} {ampm} ({tz.key})"


def _parse_hhmm(val: str, fallback: time) -> time:
    try:
        parts = val.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return fallback


def is_within_quiet_hours(now_utc: datetime, prefs: NotificationPreferences) -> bool:
    """Determine if now_utc falls inside the user's configured quiet hours in their local timezone.

    Correctly handles both same-day intervals (e.g. 13:00-15:00) and
    overnight intervals spanning midnight (e.g. 22:00-07:00).
    """
    if not prefs.quiet_hours_enabled:
        return False

    tz = resolve_zoneinfo(prefs.timezone)
    local_now = ensure_utc(now_utc).astimezone(tz)
    current_t = local_now.time().replace(tzinfo=None)

    start_t = _parse_hhmm(prefs.quiet_hours_start, time(22, 0))
    end_t = _parse_hhmm(prefs.quiet_hours_end, time(7, 0))

    if start_t == end_t:
        return False
    if start_t < end_t:
        return start_t <= current_t < end_t
    # Overnight span (e.g., 22:00 -> 07:00)
    return current_t >= start_t or current_t < end_t


def _add_months_clamped(local_dt: datetime, months: int, target_day: Optional[int] = None) -> datetime:
    """Advance local_dt by N months, clamping day to month length (and honoring target_day if provided)."""
    total_months = (local_dt.year * 12 + (local_dt.month - 1)) + months
    new_year = total_months // 12
    new_month = (total_months % 12) + 1
    desired_day = target_day or local_dt.day
    max_day = calendar.monthrange(new_year, new_month)[1]
    clamped_day = min(desired_day, max_day)
    return local_dt.replace(year=new_year, month=new_month, day=clamped_day)


def _apply_time_of_day(local_dt: datetime, time_of_day: Optional[str]) -> datetime:
    if not time_of_day:
        return local_dt
    parsed = _parse_hhmm(time_of_day, local_dt.time())
    return local_dt.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)


def _step_once_local(local_dt: datetime, rule: RecurrenceRule, tz: ZoneInfo) -> datetime:
    """Advance a timezone-aware local datetime by one recurrence interval, preserving wall-clock time across DST."""
    freq = rule.frequency
    interval = max(1, rule.interval)
    naive = local_dt.replace(tzinfo=None)

    if freq == RecurrenceFrequency.interval_minutes:
        dt_utc = local_dt.astimezone(timezone.utc) + timedelta(minutes=interval)
        return dt_utc.astimezone(tz)

    if freq == RecurrenceFrequency.interval_hours:
        dt_utc = local_dt.astimezone(timezone.utc) + timedelta(hours=interval)
        return dt_utc.astimezone(tz)

    if freq == RecurrenceFrequency.interval_days or freq == RecurrenceFrequency.daily:
        next_naive = naive + timedelta(days=interval)
        next_naive = _apply_time_of_day(next_naive, rule.time_of_day)
        return next_naive.replace(tzinfo=tz)

    if freq == RecurrenceFrequency.weekdays:
        next_naive = naive + timedelta(days=1)
        while next_naive.weekday() >= 5:  # 5=Sat, 6=Sun
            next_naive += timedelta(days=1)
        next_naive = _apply_time_of_day(next_naive, rule.time_of_day)
        return next_naive.replace(tzinfo=tz)

    if freq == RecurrenceFrequency.weekly:
        target_days = rule.days_of_week or [naive.weekday()]
        cur_wd = naive.weekday()
        later_this_week = [d for d in target_days if d > cur_wd]
        if later_this_week:
            delta_days = later_this_week[0] - cur_wd
            next_naive = naive + timedelta(days=delta_days)
        else:
            # Wrap to earliest day in target_days after interval weeks
            delta_days = (7 * interval) - cur_wd + target_days[0]
            next_naive = naive + timedelta(days=delta_days)
        next_naive = _apply_time_of_day(next_naive, rule.time_of_day)
        return next_naive.replace(tzinfo=tz)

    if freq == RecurrenceFrequency.monthly:
        next_naive = _add_months_clamped(naive, interval, target_day=rule.day_of_month)
        next_naive = _apply_time_of_day(next_naive, rule.time_of_day)
        return next_naive.replace(tzinfo=tz)

    return (naive + timedelta(days=1)).replace(tzinfo=tz)


def compute_next_occurrence(
    current_trigger_utc: datetime,
    rule: RecurrenceRule,
    tz_name: str = "UTC",
    now_utc: Optional[datetime] = None,
    skip_missed: bool = True,
) -> Optional[datetime]:
    """Compute next UTC trigger timestamp for a recurring reminder.

    - Preserves local wall-clock time across DST changes.
    - When skip_missed=True (recommended), steps cleanly until > now_utc so missed outages never replay a flood.
    - Returns None if recurrence end_at has passed.
    """
    tz = resolve_zoneinfo(tz_name)
    ref_now = ensure_utc(now_utc) if now_utc else datetime.now(timezone.utc)
    local_cursor = ensure_utc(current_trigger_utc).astimezone(tz)

    # Bounded iteration safeguard against corrupt rules
    for _ in range(1000):
        local_cursor = _step_once_local(local_cursor, rule, tz)
        candidate_utc = local_cursor.astimezone(timezone.utc)
        if not skip_missed or candidate_utc > ref_now:
            if rule.end_at and candidate_utc > ensure_utc(rule.end_at):
                return None
            return candidate_utc

    return None

