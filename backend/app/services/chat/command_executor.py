"""Unified Chat Command Executor across all AUREN Personal AI domains.

Parses structured `auren-action` JSON blocks emitted by the assistant and safely executes
authenticated, RLS-scoped mutations across Tasks, Projects, Goals, Reminders, Private Journal,
Long-Term Memories, Connections, GPS Journeys, Settings Preferences, and App Navigation.

Safety & Privacy Guarantees:
- All database calls execute strictly under the authenticated caller (`user.id` + `user.token`).
- Private Journal entries remain write-only in chat (can create, never read back).
- Destructive delete operations (`delete_*`, `reject_memory`, `revoke_connection`) are marked
  `requires_confirmation` so the UI asks the user for a 1-tap Confirm before permanent deletion.
- Navigation targets and settings keys are strictly allowlisted.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from app.models.connections import LocationSharingToggleRequest
from app.models.journal import JournalEntryCreate
from app.models.journeys import JourneyCreateRequest
from app.models.productivity import (
    GoalCreate,
    GoalStatus,
    GoalUpdate,
    ProjectCreate,
    ProjectStatus,
    ProjectUpdate,
    TaskCreate,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
)
from app.models.reminders import (
    NotificationPreferences,
    ReminderCreate,
    ReminderModel,
    ReminderPriority,
    ReminderSource,
    ReminderType,
    ReminderUpdate,
)
from app.models.user import AuthenticatedUser, UserProfileUpdate
from app.services.connections.repository import get_connection_repository
from app.services.journal.repository import get_journal_repository
from app.services.journeys.repository import get_journey_repository
from app.services.memory.repository import get_memory_repository
from app.services.productivity.repository import get_productivity_repository
from app.services.productivity.task_reminder_sync import (
    apply_task_create_reminder_sync,
    apply_task_update_reminder_sync,
)
from app.services.profile_service import profile_service
from app.services.reminders.repository import get_reminder_repository

logger = logging.getLogger(__name__)

ROUTE_ALIASES: Dict[str, str] = {
    "home": "/home",
    "dashboard": "/home",
    "command": "/home",
    "command center": "/home",
    "chat": "/chat",
    "assistant": "/chat",
    "tasks": "/tasks",
    "task": "/tasks",
    "timetable": "/tasks",
    "schedule": "/tasks",
    "projects": "/projects",
    "project": "/projects",
    "goals": "/goals",
    "goal": "/goals",
    "productivity": "/productivity",
    "overview": "/productivity",
    "reminders": "/reminders",
    "reminder": "/reminders",
    "alarms": "/reminders",
    "alerts": "/reminders",
    "journal": "/journal",
    "private journal": "/journal",
    "reflection": "/reflection",
    "audit": "/reflection",
    "settings": "/settings",
    "preferences": "/settings",
    "memories": "/memories",
    "memory": "/memories",
    "connections": "/connections",
    "contacts": "/connections",
    "operations": "/operations",
    "gps": "/operations",
    "journeys": "/journeys",
    "journey": "/journeys",
    "search": "/search",
    "system": "/system",
}

ALLOWED_ROUTES: Set[str] = set(ROUTE_ALIASES.values())

ALLOWED_SETTINGS_KEYS: Set[str] = {
    "full_name",
    "theme",
    "ai_model",
    "ai_tone",
    "ai_custom_instructions",
    "memory_auto_extraction",
    "timezone",
    "in_app_notifications_enabled",
    "browser_push_enabled",
    "audible_alerts_enabled",
    "reminder_sound",
    "default_reminder_behavior",
    "default_snooze_minutes",
    "quiet_hours_enabled",
    "quiet_hours_start",
    "quiet_hours_end",
    "quiet_hours_allow_alarms",
    "daily_briefing_enabled",
    "daily_briefing_time",
    "evening_review_enabled",
    "evening_review_time",
    "notification_priority_default",
    "recurring_missed_policy",
    "task_default_lead_minutes",
    "auto_remind_new_tasks",
    "overdue_task_reminders_enabled",
    "auto_reschedule_task_reminders",
    "suppress_reminders_on_task_complete",
    "hide_sensitive_lockscreen",
}

CONFIRMATION_REQUIRED_TYPES: Set[str] = {
    "delete_task",
    "delete_project",
    "delete_goal",
    "delete_reminder",
    "delete_journal",
    "delete_memory",
    "reject_memory",
    "revoke_connection",
    "delete_connection",
    "delete_journey",
}

ACTION_BLOCK_RE = re.compile(r"```auren[-_]action\s*(.*?)```", flags=re.DOTALL | re.IGNORECASE)


@dataclass
class ExecutedCommandResult:
    action_type: str
    status: str  # "executed" | "requires_confirmation" | "failed" | "skipped"
    domain: str
    summary: str
    entity_id: Optional[str] = None
    navigate_to: Optional[str] = None
    error: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "status": self.status,
            "domain": self.domain,
            "summary": self.summary,
            "entity_id": self.entity_id,
            "navigate_to": self.navigate_to,
            "error": self.error,
        }


@dataclass
class ExecutedCommandsBatch:
    results: List[ExecutedCommandResult] = field(default_factory=list)
    domains: Set[str] = field(default_factory=set)
    navigate_to: Optional[str] = None
    updated_preferences: Optional[Dict[str, Any]] = None
    reminder_created_or_updated: Optional[ReminderModel] = None
    reminder_action_status: Optional[str] = None
    failures: List[str] = field(default_factory=list)

    def has_events(self) -> bool:
        return bool(self.results or self.domains or self.navigate_to or self.updated_preferences)


def parse_action_blocks(response_text: str) -> List[Dict[str, Any]]:
    """Extract JSON command objects from fenced `auren-action` / `auren_action` blocks."""
    actions: List[Dict[str, Any]] = []
    for raw_block in ACTION_BLOCK_RE.findall(response_text or ""):
        cleaned = raw_block.strip()
        if not cleaned:
            continue
        try:
            parsed = json.loads(cleaned)
        except Exception:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict) and item.get("type"):
                actions.append(item)
    return actions


def _parse_optional_uuid(val: Any) -> Optional[UUID]:
    if not val:
        return None
    try:
        return UUID(str(val).strip())
    except Exception:
        return None


def _parse_optional_datetime(val: Any) -> Optional[datetime]:
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        if len(s) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return datetime.fromisoformat(f"{s}T09:00:00+00:00")
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_optional_date(val: Any) -> Optional[date]:
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def _normalize_route(raw: Any) -> Optional[str]:
    if not raw:
        return None
    val = str(raw).strip().lower()
    if val in ROUTE_ALIASES:
        return ROUTE_ALIASES[val]
    candidate = val if val.startswith("/") else f"/{val}"
    if candidate in ALLOWED_ROUTES:
        return candidate
    for key, route in ROUTE_ALIASES.items():
        if key in val:
            return route
    return None


class ChatCommandExecutor:
    """Executes structured `auren-action` commands against authenticated domain repositories."""

    def __init__(
        self,
        user: AuthenticatedUser,
        default_timezone: str = "UTC",
        skip_prehandled_reminder: bool = False,
        prod_repo: Any = None,
        rem_repo: Any = None,
        mem_repo: Any = None,
        journal_repo: Any = None,
        conn_repo: Any = None,
        journey_repo: Any = None,
        profile_svc: Any = None,
    ):
        self.user = user
        self.default_timezone = default_timezone or "UTC"
        self.skip_prehandled_reminder = skip_prehandled_reminder
        self._prod_repo = prod_repo
        self._rem_repo = rem_repo
        self._mem_repo = mem_repo
        self._journal_repo = journal_repo
        self._conn_repo = conn_repo
        self._journey_repo = journey_repo
        self._profile_svc = profile_svc or profile_service

    @property
    def prod_repo(self):
        if self._prod_repo is None:
            self._prod_repo = get_productivity_repository(user_token=self.user.token)
        return self._prod_repo

    @property
    def rem_repo(self):
        if self._rem_repo is None:
            self._rem_repo = get_reminder_repository(user_token=self.user.token)
        return self._rem_repo

    @property
    def mem_repo(self):
        if self._mem_repo is None:
            self._mem_repo = get_memory_repository(user_token=self.user.token)
        return self._mem_repo

    @property
    def journal_repo(self):
        if self._journal_repo is None:
            self._journal_repo = get_journal_repository(user_token=self.user.token)
        return self._journal_repo

    @property
    def conn_repo(self):
        if self._conn_repo is None:
            self._conn_repo = get_connection_repository(user_token=self.user.token)
        return self._conn_repo

    @property
    def journey_repo(self):
        if self._journey_repo is None:
            self._journey_repo = get_journey_repository(user_token=self.user.token)
        return self._journey_repo

    async def execute_blocks_from_text(self, response_text: str) -> ExecutedCommandsBatch:
        batch = ExecutedCommandsBatch()
        actions = parse_action_blocks(response_text)
        for act in actions:
            res = await self.execute_action(act)
            batch.results.append(res)
            if res.status == "executed":
                batch.domains.add(res.domain)
                if res.navigate_to:
                    batch.navigate_to = res.navigate_to
                if res.action_type == "update_settings" and res.payload.get("preferences"):
                    batch.updated_preferences = {
                        **(batch.updated_preferences or {}),
                        **res.payload["preferences"],
                    }
                if res.domain == "reminders" and res.payload.get("reminder"):
                    batch.reminder_created_or_updated = res.payload["reminder"]
                    batch.reminder_action_status = res.action_type
            elif res.status == "failed" and res.error:
                batch.failures.append(f"{res.action_type}: {res.error}")
        return batch

    async def execute_action(self, action: Dict[str, Any]) -> ExecutedCommandResult:
        atype = str(action.get("type") or "").strip().lower()
        if not atype:
            return ExecutedCommandResult(action_type="unknown", status="skipped", domain="system", summary="Ignored empty action")

        if atype in CONFIRMATION_REQUIRED_TYPES:
            domain_map = {
                "delete_task": "tasks",
                "delete_project": "projects",
                "delete_goal": "goals",
                "delete_reminder": "reminders",
                "delete_journal": "journal",
                "delete_memory": "memories",
                "reject_memory": "memories",
                "revoke_connection": "connections",
                "delete_connection": "connections",
                "delete_journey": "journeys",
            }
            return ExecutedCommandResult(
                action_type=atype,
                status="requires_confirmation",
                domain=domain_map.get(atype, "system"),
                summary="Requires explicit confirmation click before deletion.",
            )

        if self.skip_prehandled_reminder and atype in (
            "create_reminder", "update_reminder", "complete_reminder", "snooze_reminder", "cancel_reminder"
        ):
            return ExecutedCommandResult(
                action_type=atype,
                status="skipped",
                domain="reminders",
                summary="Already executed by pre-stream conversational reminder engine.",
            )

        try:
            if atype in ("create_task", "update_task", "complete_task"):
                return await self._handle_task(atype, action)
            if atype in ("create_project", "update_project"):
                return await self._handle_project(atype, action)
            if atype in ("create_goal", "update_goal"):
                return await self._handle_goal(atype, action)
            if atype in ("create_reminder", "update_reminder", "complete_reminder", "snooze_reminder", "cancel_reminder"):
                return await self._handle_reminder(atype, action)
            if atype == "create_journal":
                return await self._handle_journal(action)
            if atype in ("create_memory", "confirm_memory", "correct_memory", "archive_memory"):
                return await self._handle_memory(atype, action)
            if atype in ("create_connection_invite", "create_connection", "accept_connection_invite", "toggle_location_sharing"):
                return await self._handle_connection(atype, action)
            if atype == "create_journey":
                return await self._handle_journey(action)
            if atype in ("update_settings", "update_preferences"):
                return await self._handle_settings(action)
            if atype == "navigate":
                return self._handle_navigate(action)
            return ExecutedCommandResult(
                action_type=atype,
                status="skipped",
                domain="system",
                summary=f"Unsupported action type '{atype}'.",
            )
        except Exception as exc:
            logger.warning("ChatCommandExecutor failed for %s: %s", atype, exc)
            return ExecutedCommandResult(
                action_type=atype,
                status="failed",
                domain="system",
                summary=f"Failed executing {atype}",
                error=str(exc),
            )

    async def _find_task(self, action: Dict[str, Any]):
        tid = _parse_optional_uuid(action.get("task_id") or action.get("id"))
        if tid:
            found = await self.prod_repo.get_task(user_id=self.user.id, task_id=tid)
            if found:
                return found
        needle = str(action.get("target_title") or action.get("match") or action.get("title") or "").strip()
        if not needle:
            return None
        items, _ = await self.prod_repo.list_tasks(user_id=self.user.id, query=needle, page=1, page_size=10)
        nl = needle.lower()
        for t in items:
            if t.title.lower() == nl:
                return t
        for t in items:
            if nl in t.title.lower() or t.title.lower() in nl:
                return t
        return None

    async def _find_project_id(self, name_or_id: Any) -> Optional[UUID]:
        uid = _parse_optional_uuid(name_or_id)
        if uid:
            return uid
        if not name_or_id:
            return None
        needle = str(name_or_id).strip()
        items, _ = await self.prod_repo.list_projects(user_id=self.user.id, query=needle, page=1, page_size=5)
        nl = needle.lower()
        for p in items:
            if p.name.lower() == nl or nl in p.name.lower():
                return p.id
        return None

    async def _find_goal_id(self, title_or_id: Any) -> Optional[UUID]:
        uid = _parse_optional_uuid(title_or_id)
        if uid:
            return uid
        if not title_or_id:
            return None
        needle = str(title_or_id).strip()
        items, _ = await self.prod_repo.list_goals(user_id=self.user.id, query=needle, page=1, page_size=5)
        nl = needle.lower()
        for g in items:
            if g.title.lower() == nl or nl in g.title.lower():
                return g.id
        return None

    async def _handle_task(self, atype: str, action: Dict[str, Any]) -> ExecutedCommandResult:
        if atype == "complete_task":
            existing = await self._find_task(action)
            if existing:
                update_in = TaskUpdate(status=TaskStatus.completed)
                updated = await self.prod_repo.update_task(user_id=self.user.id, task_id=existing.id, update=update_in)
                if updated:
                    await apply_task_update_reminder_sync(
                        user=self.user, existing=existing, updated=updated, update_in=update_in, rem_repo=self.rem_repo
                    )
                    return ExecutedCommandResult(
                        action_type="complete_task",
                        status="executed",
                        domain="tasks",
                        entity_id=str(updated.id),
                        summary=f"Completed task '{updated.title}'",
                        payload=action,
                    )
            title = str(action.get("title") or "Completed Task").strip()[:255]
            created = await self.prod_repo.create_task(
                user_id=self.user.id,
                task=TaskCreate(title=title, status=TaskStatus.completed, priority=TaskPriority.medium),
            )
            return ExecutedCommandResult(
                action_type="complete_task",
                status="executed",
                domain="tasks",
                entity_id=str(created.id),
                summary=f"Logged completed task '{created.title}'",
                payload=action,
            )

        if atype == "update_task":
            existing = await self._find_task(action)
            if not existing:
                return ExecutedCommandResult(
                    action_type="update_task",
                    status="failed",
                    domain="tasks",
                    summary="Task not found to update",
                    error="No matching task found for update_task.",
                )
            proj_id = await self._find_project_id(action.get("project_id") or action.get("project_name"))
            goal_id = await self._find_goal_id(action.get("goal_id") or action.get("goal_title"))
            prio_val = action.get("priority")
            status_val = action.get("status")
            update_in = TaskUpdate(
                title=str(action.get("new_title") or (action.get("title") if action.get("target_title") else "")).strip()[:255] or None,
                description=action.get("description"),
                priority=TaskPriority(str(prio_val).lower()) if prio_val else None,
                status=TaskStatus(str(status_val).lower()) if status_val else None,
                due_date=_parse_optional_datetime(action.get("due_date")),
                start_date=_parse_optional_datetime(action.get("start_date")),
                project_id=proj_id,
                goal_id=goal_id,
                tags=action.get("tags") if isinstance(action.get("tags"), list) else None,
                reminder_mode=action.get("reminder_mode"),
                reminder_offset_minutes=action.get("reminder_offset_minutes"),
                reminder_at=_parse_optional_datetime(action.get("reminder_at")),
                reminder_is_alarm=action.get("reminder_is_alarm"),
                reminder_timezone=action.get("timezone") or self.default_timezone,
            )
            updated = await self.prod_repo.update_task(user_id=self.user.id, task_id=existing.id, update=update_in)
            if not updated:
                raise RuntimeError("Task update returned None")
            await apply_task_update_reminder_sync(
                user=self.user, existing=existing, updated=updated, update_in=update_in, rem_repo=self.rem_repo
            )
            return ExecutedCommandResult(
                action_type="update_task",
                status="executed",
                domain="tasks",
                entity_id=str(updated.id),
                summary=f"Updated task '{updated.title}'",
                payload=action,
            )

        # create_task
        proj_id = await self._find_project_id(action.get("project_id") or action.get("project_name"))
        goal_id = await self._find_goal_id(action.get("goal_id") or action.get("goal_title"))
        prio_raw = str(action.get("priority") or "medium").lower()
        prio = TaskPriority(prio_raw) if prio_raw in TaskPriority._value2member_map_ else TaskPriority.medium
        status_raw = str(action.get("status") or "todo").lower()
        t_status = TaskStatus(status_raw) if status_raw in TaskStatus._value2member_map_ else TaskStatus.todo
        task_in = TaskCreate(
            title=str(action.get("title") or "Untitled Task").strip()[:255],
            description=action.get("description"),
            priority=prio,
            status=t_status,
            due_date=_parse_optional_datetime(action.get("due_date")),
            start_date=_parse_optional_datetime(action.get("start_date")),
            project_id=proj_id,
            goal_id=goal_id,
            tags=[str(t) for t in action.get("tags", [])] if isinstance(action.get("tags"), list) else [],
            reminder_mode=action.get("reminder_mode"),
            reminder_offset_minutes=action.get("reminder_offset_minutes"),
            reminder_at=_parse_optional_datetime(action.get("reminder_at")),
            reminder_is_alarm=action.get("reminder_is_alarm"),
            reminder_timezone=action.get("timezone") or self.default_timezone,
        )
        created = await self.prod_repo.create_task(user_id=self.user.id, task=task_in)
        await apply_task_create_reminder_sync(user=self.user, task_in=task_in, created=created, rem_repo=self.rem_repo)
        return ExecutedCommandResult(
            action_type="create_task",
            status="executed",
            domain="tasks",
            entity_id=str(created.id),
            summary=f"Created task '{created.title}'",
            payload=action,
        )

    async def _handle_project(self, atype: str, action: Dict[str, Any]) -> ExecutedCommandResult:
        if atype == "update_project":
            pid = await self._find_project_id(action.get("project_id") or action.get("target_name") or action.get("name") or action.get("title"))
            if not pid:
                return ExecutedCommandResult(
                    action_type="update_project",
                    status="failed",
                    domain="projects",
                    summary="Project not found",
                    error="No matching project found to update.",
                )
            st_raw = action.get("status")
            updated = await self.prod_repo.update_project(
                user_id=self.user.id,
                project_id=pid,
                update=ProjectUpdate(
                    name=str(action.get("new_name") or (action.get("name") if action.get("target_name") else "")).strip()[:255] or None,
                    description=action.get("description"),
                    color=action.get("color"),
                    status=ProjectStatus(str(st_raw).lower()) if st_raw else None,
                    target_date=_parse_optional_date(action.get("target_date")),
                    goal_id=await self._find_goal_id(action.get("goal_id") or action.get("goal_title")),
                ),
            )
            if not updated:
                raise RuntimeError("Project update failed")
            return ExecutedCommandResult(
                action_type="update_project",
                status="executed",
                domain="projects",
                entity_id=str(updated.id),
                summary=f"Updated project '{updated.name}'",
                payload=action,
            )

        goal_id = await self._find_goal_id(action.get("goal_id") or action.get("goal_title"))
        st_raw = str(action.get("status") or "active").lower()
        p_status = ProjectStatus(st_raw) if st_raw in ProjectStatus._value2member_map_ else ProjectStatus.active
        created = await self.prod_repo.create_project(
            user_id=self.user.id,
            project=ProjectCreate(
                name=str(action.get("name") or action.get("title") or "Untitled Project").strip()[:255],
                description=action.get("description"),
                color=action.get("color") or "#10b981",
                status=p_status,
                start_date=_parse_optional_date(action.get("start_date")),
                target_date=_parse_optional_date(action.get("target_date")),
                goal_id=goal_id,
            ),
        )
        return ExecutedCommandResult(
            action_type="create_project",
            status="executed",
            domain="projects",
            entity_id=str(created.id),
            summary=f"Created project '{created.name}'",
            payload=action,
        )

    async def _handle_goal(self, atype: str, action: Dict[str, Any]) -> ExecutedCommandResult:
        if atype == "update_goal":
            gid = await self._find_goal_id(action.get("goal_id") or action.get("target_title") or action.get("title") or action.get("name"))
            if not gid:
                return ExecutedCommandResult(
                    action_type="update_goal",
                    status="failed",
                    domain="goals",
                    summary="Goal not found",
                    error="No matching goal found to update.",
                )
            st_raw = action.get("status")
            updated = await self.prod_repo.update_goal(
                user_id=self.user.id,
                goal_id=gid,
                update=GoalUpdate(
                    title=str(action.get("new_title") or (action.get("title") if action.get("target_title") else "")).strip()[:255] or None,
                    description=action.get("description"),
                    status=GoalStatus(str(st_raw).lower()) if st_raw else None,
                    target_date=_parse_optional_date(action.get("target_date")),
                    target_value=action.get("target_value"),
                    current_value=action.get("current_value"),
                    unit=action.get("unit"),
                ),
            )
            if not updated:
                raise RuntimeError("Goal update failed")
            return ExecutedCommandResult(
                action_type="update_goal",
                status="executed",
                domain="goals",
                entity_id=str(updated.id),
                summary=f"Updated goal '{updated.title}'",
                payload=action,
            )

        st_raw = str(action.get("status") or "in_progress").lower()
        g_status = GoalStatus(st_raw) if st_raw in GoalStatus._value2member_map_ else GoalStatus.in_progress
        created = await self.prod_repo.create_goal(
            user_id=self.user.id,
            goal=GoalCreate(
                title=str(action.get("title") or action.get("name") or "Untitled Goal").strip()[:255],
                description=action.get("description"),
                status=g_status,
                target_date=_parse_optional_date(action.get("target_date")),
                target_value=action.get("target_value"),
                current_value=action.get("current_value") or 0.0,
                unit=action.get("unit"),
            ),
        )
        return ExecutedCommandResult(
            action_type="create_goal",
            status="executed",
            domain="goals",
            entity_id=str(created.id),
            summary=f"Created goal '{created.title}'",
            payload=action,
        )

    async def _find_reminder(self, action: Dict[str, Any]) -> Optional[ReminderModel]:
        rid = _parse_optional_uuid(action.get("reminder_id") or action.get("id"))
        if rid:
            found = await self.rem_repo.get_reminder(user_id=self.user.id, reminder_id=rid)
            if found:
                return found
        needle = str(action.get("target_title") or action.get("title") or action.get("query") or "").strip()
        if not needle:
            return None
        items, _ = await self.rem_repo.list_reminders(user_id=self.user.id, query=needle, page=1, page_size=10)
        nl = needle.lower()
        for r in items:
            if r.title.lower() == nl or nl in r.title.lower():
                return r
        return items[0] if items else None

    async def _handle_reminder(self, atype: str, action: Dict[str, Any]) -> ExecutedCommandResult:
        if atype == "create_reminder":
            trig = _parse_optional_datetime(action.get("trigger_at"))
            if not trig:
                return ExecutedCommandResult(
                    action_type="create_reminder",
                    status="failed",
                    domain="reminders",
                    summary="Missing valid reminder trigger_at",
                    error="Missing or invalid trigger_at timestamp.",
                )
            saved = await self.rem_repo.create_reminder(
                user_id=self.user.id,
                reminder=ReminderCreate(
                    title=str(action.get("title") or "Personal Reminder")[:255],
                    description=action.get("description"),
                    reminder_type=ReminderType.alarm if action.get("is_alarm") else ReminderType.general,
                    trigger_at=trig,
                    timezone=str(action.get("timezone") or self.default_timezone),
                    is_alarm=bool(action.get("is_alarm", False)),
                    priority=ReminderPriority.alarm if action.get("is_alarm") else ReminderPriority.normal,
                    source=ReminderSource.chat,
                ),
            )
            return ExecutedCommandResult(
                action_type="create_reminder",
                status="executed",
                domain="reminders",
                entity_id=str(saved.id),
                summary=f"Scheduled reminder '{saved.title}'",
                payload={"reminder": saved},
            )

        existing = await self._find_reminder(action)
        if not existing:
            return ExecutedCommandResult(
                action_type=atype,
                status="failed",
                domain="reminders",
                summary="Reminder not found",
                error=f"Could not find matching reminder for {atype}.",
            )
        if atype == "complete_reminder":
            saved = await self.rem_repo.complete_reminder(user_id=self.user.id, reminder_id=existing.id)
        elif atype == "cancel_reminder":
            saved = await self.rem_repo.cancel_reminder(user_id=self.user.id, reminder_id=existing.id)
        elif atype == "snooze_reminder":
            mins = max(1, min(1440, int(action.get("snooze_minutes") or 10)))
            saved = await self.rem_repo.snooze_reminder(
                user_id=self.user.id,
                reminder_id=existing.id,
                snoozed_until=datetime.now(timezone.utc) + timedelta(minutes=mins),
            )
        else:  # update_reminder
            saved = await self.rem_repo.update_reminder(
                user_id=self.user.id,
                reminder_id=existing.id,
                update=ReminderUpdate(
                    title=action.get("new_title") or (action.get("title") if action.get("target_title") else None),
                    description=action.get("description"),
                    trigger_at=_parse_optional_datetime(action.get("trigger_at")),
                    timezone=action.get("timezone"),
                    is_alarm=action.get("is_alarm"),
                ),
            )
        return ExecutedCommandResult(
            action_type=atype,
            status="executed",
            domain="reminders",
            entity_id=str(saved.id if saved else existing.id),
            summary=f"Updated reminder '{saved.title if saved else existing.title}'",
            payload={"reminder": saved},
        )

    async def _handle_journal(self, action: Dict[str, Any]) -> ExecutedCommandResult:
        content = str(action.get("content") or action.get("description") or action.get("title") or "").strip()
        if not content:
            return ExecutedCommandResult(
                action_type="create_journal",
                status="failed",
                domain="journal",
                summary="Journal content was empty",
                error="Journal entry content cannot be empty.",
            )
        tags = [str(t).strip() for t in action.get("tags", []) if str(t).strip()] if isinstance(action.get("tags"), list) else []
        created = await self.journal_repo.create_entry(
            user_id=self.user.id,
            payload=JournalEntryCreate(
                title=str(action["title"]).strip()[:255] if action.get("title") else None,
                content=content,
                mood=str(action["mood"]).strip().lower()[:50] if action.get("mood") else None,
                tags=tags,
                is_private=True,
                entry_date=_parse_optional_date(action.get("entry_date")),
            ),
        )
        return ExecutedCommandResult(
            action_type="create_journal",
            status="executed",
            domain="journal",
            entity_id=str(created.id),
            summary=f"Saved private journal entry '{created.title or 'Reflection'}'",
            payload=action,
        )

    async def _find_memory(self, action: Dict[str, Any]):
        mid = _parse_optional_uuid(action.get("memory_id") or action.get("id"))
        if mid:
            found = await self.mem_repo.get_memory(user_id=self.user.id, memory_id=mid)
            if found:
                return found
        needle = str(action.get("target_content") or action.get("query") or action.get("content") or "").strip()
        if not needle:
            return None
        items, _ = await self.mem_repo.list_memories(user_id=self.user.id, query=needle, page=1, page_size=10)
        return items[0] if items else None

    async def _handle_memory(self, atype: str, action: Dict[str, Any]) -> ExecutedCommandResult:
        if atype == "create_memory":
            content = str(action.get("content") or action.get("fact") or "").strip()
            if not content:
                raise ValueError("Memory content is required.")
            mtype = str(action.get("memory_type") or "fact").lower()
            if mtype not in ("fact", "preference", "goal", "project", "context", "observation"):
                mtype = "fact"
            cat = str(action.get("category") or "general").lower()
            if cat not in ("personal", "work", "technical", "health_lifestyle", "financial", "general"):
                cat = "general"
            imp = max(1, min(5, int(action.get("importance") or 3)))
            created = await self.mem_repo.create_memory(
                user_id=self.user.id,
                content=content,
                memory_type=mtype,
                category=cat,
                importance=imp,
                origin="explicit_user_statement",
            )
            return ExecutedCommandResult(
                action_type="create_memory",
                status="executed",
                domain="memories",
                entity_id=str(created.id),
                summary=f"Saved memory '{created.content[:60]}'",
                payload=action,
            )

        existing = await self._find_memory(action)
        if not existing:
            return ExecutedCommandResult(
                action_type=atype,
                status="failed",
                domain="memories",
                summary="Memory not found",
                error="No matching memory found.",
            )
        if atype == "confirm_memory":
            saved = await self.mem_repo.confirm_memory(user_id=self.user.id, memory_id=existing.id)
        elif atype == "archive_memory":
            saved = await self.mem_repo.archive_memory(user_id=self.user.id, memory_id=existing.id)
        else:  # correct_memory
            new_text = str(action.get("new_content") or action.get("content") or "").strip()
            if not new_text:
                raise ValueError("Updated memory content is required for correct_memory.")
            saved = await self.mem_repo.correct_memory(
                user_id=self.user.id,
                memory_id=existing.id,
                content=new_text,
                memory_type=action.get("memory_type"),
                category=action.get("category"),
                importance=action.get("importance"),
            )
        return ExecutedCommandResult(
            action_type=atype,
            status="executed",
            domain="memories",
            entity_id=str(saved.id if saved else existing.id),
            summary=f"Updated memory ({atype})",
            payload=action,
        )

    async def _handle_connection(self, atype: str, action: Dict[str, Any]) -> ExecutedCommandResult:
        if atype in ("create_connection_invite", "create_connection"):
            name = str(action.get("display_name") or action.get("name") or "Trusted Connection").strip()[:100]
            created = await self.conn_repo.create_invite(user_id=self.user.id, display_name=name)
            return ExecutedCommandResult(
                action_type="create_connection_invite",
                status="executed",
                domain="connections",
                entity_id=str(created.id),
                summary=f"Created connection invite for '{created.display_name}' (code: {created.invite_code})",
                payload=action,
            )
        if atype == "accept_connection_invite":
            code = str(action.get("invite_code") or "").strip()
            if not code:
                raise ValueError("invite_code is required")
            accepted = await self.conn_repo.accept_invite(user_id=self.user.id, invite_code=code)
            return ExecutedCommandResult(
                action_type="accept_connection_invite",
                status="executed",
                domain="connections",
                entity_id=str(accepted.id),
                summary=f"Accepted connection invite from '{accepted.display_name}'",
                payload=action,
            )
        # toggle_location_sharing
        enabled = bool(action.get("enabled", False))
        dur = max(5, min(1440, int(action.get("duration_minutes") or 60)))
        await self.conn_repo.toggle_location_sharing(
            user_id=self.user.id,
            payload=LocationSharingToggleRequest(enabled=enabled, duration_minutes=dur),
        )
        return ExecutedCommandResult(
            action_type="toggle_location_sharing",
            status="executed",
            domain="connections",
            summary=f"Location sharing {'enabled' if enabled else 'paused'}",
            payload=action,
        )

    async def _handle_journey(self, action: Dict[str, Any]) -> ExecutedCommandResult:
        title = str(action.get("title") or "Recorded Journey").strip()[:200]
        created = await self.journey_repo.create_or_sync_journey(
            user_id=self.user.id,
            payload=JourneyCreateRequest(
                title=title,
                status=str(action.get("status") or "completed"),
                assignment_site=action.get("assignment_site"),
                assignment_purpose=action.get("assignment_purpose"),
                assignment_notes=action.get("assignment_notes"),
                is_team_assignment=bool(action.get("assignment_site") or action.get("is_team_assignment")),
            ),
        )
        return ExecutedCommandResult(
            action_type="create_journey",
            status="executed",
            domain="journeys",
            entity_id=str(created.id),
            summary=f"Saved journey '{created.title}'",
            payload=action,
        )

    async def _handle_settings(self, action: Dict[str, Any]) -> ExecutedCommandResult:
        raw_prefs = action.get("preferences") if isinstance(action.get("preferences"), dict) else action
        filtered_prefs: Dict[str, Any] = {}
        for k, v in raw_prefs.items():
            if k in ALLOWED_SETTINGS_KEYS and k != "full_name" and v is not None:
                filtered_prefs[k] = v
        full_name = raw_prefs.get("full_name") if isinstance(raw_prefs.get("full_name"), str) else None
        if not filtered_prefs and full_name is None:
            raise ValueError("No supported settings fields provided.")
        updated = await self._profile_svc.update_profile(
            self.user,
            UserProfileUpdate(
                full_name=full_name,
                preferences=filtered_prefs or None,
            ),
        )
        return ExecutedCommandResult(
            action_type="update_settings",
            status="executed",
            domain="settings",
            entity_id=str(updated.id),
            summary="Updated your AUREN preferences",
            payload={"preferences": filtered_prefs, "full_name": full_name},
        )

    def _handle_navigate(self, action: Dict[str, Any]) -> ExecutedCommandResult:
        route = _normalize_route(action.get("path") or action.get("target") or action.get("screen"))
        if not route:
            return ExecutedCommandResult(
                action_type="navigate",
                status="failed",
                domain="navigation",
                summary="Unknown screen path",
                error="Requested screen path is not a recognized AUREN route.",
            )
        return ExecutedCommandResult(
            action_type="navigate",
            status="executed",
            domain="navigation",
            navigate_to=route,
            summary=f"Opened {route}",
            payload={"path": route},
        )

