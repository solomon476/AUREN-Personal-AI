"""Supabase PostgreSQL productivity repository adapter enforcing Row Level Security (RLS).

Interacts directly with Supabase PostgREST endpoints using authenticated user credentials
(never service-role) ensuring full tenant isolation and RLS policy enforcement.
"""

from datetime import date, datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from app.core.exceptions import DatabaseAuthError, DatabaseConnectionError, DatabaseError
from app.models.productivity import (
    GoalCreate,
    GoalDetailModel,
    GoalModel,
    GoalStatus,
    GoalUpdate,
    ProductivityContextSummary,
    ProductivityDashboardResponse,
    ProjectCreate,
    ProjectDetailModel,
    ProjectModel,
    ProjectStatus,
    ProjectUpdate,
    TaskCreate,
    TaskModel,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
)
from app.services.productivity.base_repository import BaseProductivityRepository

logger = logging.getLogger(__name__)


class SupabaseProductivityRepository(BaseProductivityRepository):
    """Supabase PostgREST productivity repository adapter."""

    def __init__(
        self,
        supabase_url: str,
        supabase_anon_key: str,
        user_token: Optional[str] = None,
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
        }
        if self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
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
            logger.error("Supabase connection error: %s", err)
            raise DatabaseConnectionError(f"Failed to connect to Supabase: {err}")
        except httpx.TimeoutException as err:
            logger.error("Supabase request timeout: %s", err)
            raise DatabaseConnectionError(f"Supabase request timed out: {err}")
        except httpx.RequestError as err:
            logger.error("Supabase network error: %s", err)
            raise DatabaseError(f"Network error interacting with Supabase: {err}")

        if response.status_code in (401, 403):
            raise DatabaseAuthError(f"Supabase authentication failed ({response.status_code}): {response.text}")

        return response

    # ------------------------------------------------------------------------
    # Mappings
    # ------------------------------------------------------------------------

    def _map_task(self, item: Dict[str, Any], project_name: Optional[str] = None, goal_title: Optional[str] = None) -> TaskModel:
        return TaskModel(
            id=UUID(item["id"]),
            user_id=UUID(item["user_id"]),
            title=item["title"],
            description=item.get("description"),
            status=TaskStatus(item["status"]),
            priority=TaskPriority(item["priority"]),
            project_id=UUID(item["project_id"]) if item.get("project_id") else None,
            goal_id=UUID(item["goal_id"]) if item.get("goal_id") else None,
            parent_task_id=UUID(item["parent_task_id"]) if item.get("parent_task_id") else None,
            due_date=datetime.fromisoformat(item["due_date"]) if item.get("due_date") else None,
            start_date=datetime.fromisoformat(item["start_date"]) if item.get("start_date") else None,
            completed_at=datetime.fromisoformat(item["completed_at"]) if item.get("completed_at") else None,
            tags=item.get("tags") or [],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]),
            project_name=project_name,
            goal_title=goal_title,
        )

    def _map_project(self, item: Dict[str, Any], task_count: int = 0, completed_task_count: int = 0, goal_title: Optional[str] = None) -> ProjectModel:
        progress = 0.0
        if task_count > 0:
            progress = round((completed_task_count / task_count) * 100.0, 1)

        start_date_val = None
        if item.get("start_date"):
            try:
                start_date_val = date.fromisoformat(item["start_date"].split("T")[0])
            except Exception:
                pass

        target_date_val = None
        if item.get("target_date"):
            try:
                target_date_val = date.fromisoformat(item["target_date"].split("T")[0])
            except Exception:
                pass

        return ProjectModel(
            id=UUID(item["id"]),
            user_id=UUID(item["user_id"]),
            name=item["name"],
            description=item.get("description"),
            color=item.get("color") or "#4872bd",
            status=ProjectStatus(item["status"]),
            start_date=start_date_val,
            target_date=target_date_val,
            completed_at=datetime.fromisoformat(item["completed_at"]) if item.get("completed_at") else None,
            goal_id=UUID(item["goal_id"]) if item.get("goal_id") else None,
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]),
            goal_title=goal_title,
            task_count=task_count,
            completed_task_count=completed_task_count,
            progress_percentage=progress,
        )

    def _map_goal(self, item: Dict[str, Any], project_count: int = 0, task_count: int = 0, completed_task_count: int = 0) -> GoalModel:
        target_date_val = None
        if item.get("target_date"):
            try:
                target_date_val = date.fromisoformat(item["target_date"].split("T")[0])
            except Exception:
                pass

        target_val = float(item["target_value"]) if item.get("target_value") is not None else None
        current_val = float(item["current_value"]) if item.get("current_value") is not None else 0.0

        progress_percentage: Optional[float] = None
        status = item["status"]
        if target_val and target_val > 0:
            progress_percentage = min(100.0, max(0.0, round((current_val / target_val) * 100.0, 1)))
        elif status in ("achieved", "completed"):
            progress_percentage = 100.0
        elif task_count > 0:
            progress_percentage = round((completed_task_count / task_count) * 100.0, 1)

        return GoalModel(
            id=UUID(item["id"]),
            user_id=UUID(item["user_id"]),
            title=item["title"],
            description=item.get("description"),
            status=GoalStatus(item["status"]),
            target_date=target_date_val,
            target_value=target_val,
            current_value=current_val,
            unit=item.get("unit"),
            completed_at=datetime.fromisoformat(item["completed_at"]) if item.get("completed_at") else None,
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]),
            progress_percentage=progress_percentage,
            project_count=project_count,
            task_count=task_count,
        )

    # ------------------------------------------------------------------------
    # Task Operations
    # ------------------------------------------------------------------------

    async def create_task(self, user_id: UUID, task: TaskCreate) -> TaskModel:
        payload = {
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority.value,
            "project_id": str(task.project_id) if task.project_id else None,
            "goal_id": str(task.goal_id) if task.goal_id else None,
            "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "tags": task.tags,
            "completed_at": datetime.now(timezone.utc).isoformat() if task.status == TaskStatus.completed else None,
        }
        resp = await self._request("POST", "/tasks", json_data=payload, prefer="return=representation")
        if resp.status_code not in (200, 201):
            raise DatabaseError(f"Failed creating task: {resp.text}")
        created_items = resp.json()
        if not created_items:
            raise DatabaseError("Task created but no data returned")
        return self._map_task(created_items[0])

    async def get_task(self, user_id: UUID, task_id: UUID) -> Optional[TaskModel]:
        resp = await self._request(
            "GET",
            "/tasks",
            params={
                "id": f"eq.{task_id}",
                "select": "*,projects(name),goals(title)",
            },
        )
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not items:
            return None
        item = items[0]
        proj_name = item.get("projects", {}).get("name") if isinstance(item.get("projects"), dict) else None
        goal_title = item.get("goals", {}).get("title") if isinstance(item.get("goals"), dict) else None
        return self._map_task(item, project_name=proj_name, goal_title=goal_title)

    async def list_tasks(
        self,
        user_id: UUID,
        project_id: Optional[UUID] = None,
        goal_id: Optional[UUID] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        query: Optional[str] = None,
        parent_task_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[TaskModel], int]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        params: Dict[str, Any] = {
            "select": "*,projects(name),goals(title)",
            "order": "created_at.desc",
            "limit": str(page_size),
            "offset": str(offset),
        }
        if project_id:
            params["project_id"] = f"eq.{project_id}"
        if goal_id:
            params["goal_id"] = f"eq.{goal_id}"
        if status:
            params["status"] = f"eq.{status}"
        if priority:
            params["priority"] = f"eq.{priority}"
        if parent_task_id:
            params["parent_task_id"] = f"eq.{parent_task_id}"
        if query:
            params["title"] = f"ilike.*{query}*"

        resp = await self._request("GET", "/tasks", params=params, prefer="count=exact")
        if resp.status_code != 200:
            return [], 0

        # Extract content-range for total
        total = 0
        cr = resp.headers.get("content-range", "")
        if "/" in cr:
            try:
                total = int(cr.split("/")[1])
            except Exception:
                total = len(resp.json())
        else:
            total = len(resp.json())

        items = []
        for it in resp.json():
            p_name = it.get("projects", {}).get("name") if isinstance(it.get("projects"), dict) else None
            g_title = it.get("goals", {}).get("title") if isinstance(it.get("goals"), dict) else None
            items.append(self._map_task(it, project_name=p_name, goal_title=g_title))

        return items, total

    async def update_task(
        self,
        user_id: UUID,
        task_id: UUID,
        update: TaskUpdate,
    ) -> Optional[TaskModel]:
        payload: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if update.title is not None:
            payload["title"] = update.title
        if update.description is not None:
            payload["description"] = update.description
        if update.status is not None:
            payload["status"] = update.status.value
            if update.status == TaskStatus.completed:
                payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                payload["completed_at"] = None
        if update.priority is not None:
            payload["priority"] = update.priority.value
        if update.project_id is not None:
            payload["project_id"] = str(update.project_id)
        if update.goal_id is not None:
            payload["goal_id"] = str(update.goal_id)
        if update.parent_task_id is not None:
            payload["parent_task_id"] = str(update.parent_task_id)
        if update.due_date is not None:
            payload["due_date"] = update.due_date.isoformat()
        if update.start_date is not None:
            payload["start_date"] = update.start_date.isoformat()
        if update.tags is not None:
            payload["tags"] = update.tags

        resp = await self._request(
            "PATCH",
            f"/tasks?id=eq.{task_id}",
            json_data=payload,
            prefer="return=representation",
        )
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not items:
            return None
        return await self.get_task(user_id, task_id)

    async def delete_task(self, user_id: UUID, task_id: UUID) -> bool:
        resp = await self._request("DELETE", f"/tasks?id=eq.{task_id}")
        return resp.status_code in (200, 204)

    # ------------------------------------------------------------------------
    # Project Operations
    # ------------------------------------------------------------------------

    async def create_project(self, user_id: UUID, project: ProjectCreate) -> ProjectModel:
        payload = {
            "name": project.name,
            "description": project.description,
            "color": project.color or "#4872bd",
            "status": project.status.value,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "target_date": project.target_date.isoformat() if project.target_date else None,
            "goal_id": str(project.goal_id) if project.goal_id else None,
            "completed_at": datetime.now(timezone.utc).isoformat() if project.status == ProjectStatus.completed else None,
        }
        resp = await self._request("POST", "/projects", json_data=payload, prefer="return=representation")
        if resp.status_code not in (200, 201):
            raise DatabaseError(f"Failed creating project: {resp.text}")
        items = resp.json()
        if not items:
            raise DatabaseError("Project created but no data returned")
        return self._map_project(items[0])

    async def get_project(self, user_id: UUID, project_id: UUID) -> Optional[ProjectDetailModel]:
        resp = await self._request(
            "GET",
            "/projects",
            params={
                "id": f"eq.{project_id}",
                "select": "*,goals(title),tasks(*)",
            },
        )
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not items:
            return None
        p = items[0]
        raw_tasks = p.get("tasks") or []
        completed_count = sum(1 for t in raw_tasks if t.get("status") == "completed")
        g_title = p.get("goals", {}).get("title") if isinstance(p.get("goals"), dict) else None

        base_proj = self._map_project(
            p,
            task_count=len(raw_tasks),
            completed_task_count=completed_count,
            goal_title=g_title,
        )

        tasks = [self._map_task(t, project_name=base_proj.name, goal_title=g_title) for t in raw_tasks]
        return ProjectDetailModel(**base_proj.model_dump(), tasks=tasks)

    async def list_projects(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        goal_id: Optional[UUID] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ProjectModel], int]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        params: Dict[str, Any] = {
            "select": "*,goals(title),tasks(id,status)",
            "order": "created_at.desc",
            "limit": str(page_size),
            "offset": str(offset),
        }
        if status:
            params["status"] = f"eq.{status}"
        if goal_id:
            params["goal_id"] = f"eq.{goal_id}"
        if query:
            params["name"] = f"ilike.*{query}*"

        resp = await self._request("GET", "/projects", params=params, prefer="count=exact")
        if resp.status_code != 200:
            return [], 0

        total = 0
        cr = resp.headers.get("content-range", "")
        if "/" in cr:
            try:
                total = int(cr.split("/")[1])
            except Exception:
                total = len(resp.json())
        else:
            total = len(resp.json())

        items = []
        for p in resp.json():
            raw_tasks = p.get("tasks") or []
            comp_count = sum(1 for t in raw_tasks if t.get("status") == "completed")
            g_title = p.get("goals", {}).get("title") if isinstance(p.get("goals"), dict) else None
            items.append(self._map_project(p, task_count=len(raw_tasks), completed_task_count=comp_count, goal_title=g_title))

        return items, total

    async def update_project(
        self,
        user_id: UUID,
        project_id: UUID,
        update: ProjectUpdate,
    ) -> Optional[ProjectModel]:
        payload: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if update.name is not None:
            payload["name"] = update.name
        if update.description is not None:
            payload["description"] = update.description
        if update.color is not None:
            payload["color"] = update.color
        if update.status is not None:
            payload["status"] = update.status.value
            if update.status == ProjectStatus.completed:
                payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                payload["completed_at"] = None
        if update.start_date is not None:
            payload["start_date"] = update.start_date.isoformat()
        if update.target_date is not None:
            payload["target_date"] = update.target_date.isoformat()
        if update.goal_id is not None:
            payload["goal_id"] = str(update.goal_id)

        resp = await self._request(
            "PATCH",
            f"/projects?id=eq.{project_id}",
            json_data=payload,
            prefer="return=representation",
        )
        if resp.status_code != 200:
            return None
        return await self.get_project(user_id, project_id)

    async def delete_project(
        self,
        user_id: UUID,
        project_id: UUID,
        delete_tasks: bool = False,
    ) -> bool:
        if delete_tasks:
            await self._request("DELETE", f"/tasks?project_id=eq.{project_id}")
        else:
            await self._request("PATCH", f"/tasks?project_id=eq.{project_id}", json_data={"project_id": None})
        resp = await self._request("DELETE", f"/projects?id=eq.{project_id}")
        return resp.status_code in (200, 204)

    # ------------------------------------------------------------------------
    # Goal Operations
    # ------------------------------------------------------------------------

    async def create_goal(self, user_id: UUID, goal: GoalCreate) -> GoalModel:
        payload = {
            "title": goal.title,
            "description": goal.description,
            "status": goal.status.value,
            "target_date": goal.target_date.isoformat() if goal.target_date else None,
            "target_value": goal.target_value,
            "current_value": goal.current_value or 0.0,
            "unit": goal.unit,
            "completed_at": datetime.now(timezone.utc).isoformat() if goal.status in (GoalStatus.achieved, GoalStatus.completed) else None,
        }
        resp = await self._request("POST", "/goals", json_data=payload, prefer="return=representation")
        if resp.status_code not in (200, 201):
            raise DatabaseError(f"Failed creating goal: {resp.text}")
        items = resp.json()
        if not items:
            raise DatabaseError("Goal created but no data returned")
        return self._map_goal(items[0])

    async def get_goal(self, user_id: UUID, goal_id: UUID) -> Optional[GoalDetailModel]:
        resp = await self._request(
            "GET",
            "/goals",
            params={
                "id": f"eq.{goal_id}",
                "select": "*,projects(*,tasks(id,status)),tasks(*)",
            },
        )
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not items:
            return None
        g = items[0]
        raw_projects = g.get("projects") or []
        raw_tasks = g.get("tasks") or []
        completed_tasks = sum(1 for t in raw_tasks if t.get("status") == "completed")

        base_goal = self._map_goal(
            g,
            project_count=len(raw_projects),
            task_count=len(raw_tasks),
            completed_task_count=completed_tasks,
        )

        projects = []
        for p in raw_projects:
            p_tasks = p.get("tasks") or []
            p_comp = sum(1 for pt in p_tasks if pt.get("status") == "completed")
            projects.append(self._map_project(p, task_count=len(p_tasks), completed_task_count=p_comp, goal_title=base_goal.title))

        tasks = [self._map_task(t, goal_title=base_goal.title) for t in raw_tasks]
        return GoalDetailModel(**base_goal.model_dump(), projects=projects, tasks=tasks)

    async def list_goals(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[GoalModel], int]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        params: Dict[str, Any] = {
            "select": "*,projects(id),tasks(id,status)",
            "order": "created_at.desc",
            "limit": str(page_size),
            "offset": str(offset),
        }
        if status:
            params["status"] = f"eq.{status}"
        if query:
            params["title"] = f"ilike.*{query}*"

        resp = await self._request("GET", "/goals", params=params, prefer="count=exact")
        if resp.status_code != 200:
            return [], 0

        total = 0
        cr = resp.headers.get("content-range", "")
        if "/" in cr:
            try:
                total = int(cr.split("/")[1])
            except Exception:
                total = len(resp.json())
        else:
            total = len(resp.json())

        items = []
        for g in resp.json():
            p_count = len(g.get("projects") or [])
            g_tasks = g.get("tasks") or []
            comp_count = sum(1 for t in g_tasks if t.get("status") == "completed")
            items.append(self._map_goal(g, project_count=p_count, task_count=len(g_tasks), completed_task_count=comp_count))

        return items, total

    async def update_goal(
        self,
        user_id: UUID,
        goal_id: UUID,
        update: GoalUpdate,
    ) -> Optional[GoalModel]:
        payload: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if update.title is not None:
            payload["title"] = update.title
        if update.description is not None:
            payload["description"] = update.description
        if update.status is not None:
            payload["status"] = update.status.value
            if update.status in (GoalStatus.achieved, GoalStatus.completed):
                payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                payload["completed_at"] = None
        if update.target_date is not None:
            payload["target_date"] = update.target_date.isoformat()
        if update.target_value is not None:
            payload["target_value"] = update.target_value
        if update.current_value is not None:
            payload["current_value"] = update.current_value
        if update.unit is not None:
            payload["unit"] = update.unit

        resp = await self._request(
            "PATCH",
            f"/goals?id=eq.{goal_id}",
            json_data=payload,
            prefer="return=representation",
        )
        if resp.status_code != 200:
            return None
        return await self.get_goal(user_id, goal_id)

    async def delete_goal(self, user_id: UUID, goal_id: UUID) -> bool:
        await self._request("PATCH", f"/projects?goal_id=eq.{goal_id}", json_data={"goal_id": None})
        await self._request("PATCH", f"/tasks?goal_id=eq.{goal_id}", json_data={"goal_id": None})
        resp = await self._request("DELETE", f"/goals?id=eq.{goal_id}")
        return resp.status_code in (200, 204)

    # ------------------------------------------------------------------------
    # Dashboard and Context
    # ------------------------------------------------------------------------

    async def get_dashboard(self, user_id: UUID) -> ProductivityDashboardResponse:
        tasks, _ = await self.list_tasks(user_id=user_id, page=1, page_size=100)
        projects, _ = await self.list_projects(user_id=user_id, page=1, page_size=50)
        goals, _ = await self.list_goals(user_id=user_id, page=1, page_size=50)

        now = datetime.now(timezone.utc)
        active_tasks = [t for t in tasks if t.status in (TaskStatus.todo, TaskStatus.in_progress, TaskStatus.blocked)]
        overdue_tasks = [t for t in active_tasks if t.due_date and t.due_date < now]
        completed_tasks = [t for t in tasks if t.status == TaskStatus.completed]
        active_projects = [p for p in projects if p.status in (ProjectStatus.planning, ProjectStatus.active, ProjectStatus.on_hold)]
        active_goals = [g for g in goals if g.status in (GoalStatus.not_started, GoalStatus.in_progress)]
        upcoming_tasks = [t for t in active_tasks if not t.due_date or t.due_date >= now][:6]
        recently_completed = sorted(completed_tasks, key=lambda t: t.completed_at or t.updated_at, reverse=True)[:5]

        return ProductivityDashboardResponse(
            active_tasks_count=len(active_tasks),
            overdue_tasks_count=len(overdue_tasks),
            completed_tasks_count=len(completed_tasks),
            active_projects_count=len(active_projects),
            active_goals_count=len(active_goals),
            overdue_tasks=overdue_tasks[:6],
            upcoming_tasks=upcoming_tasks,
            active_projects=active_projects[:6],
            active_goals=active_goals[:6],
            recently_completed_tasks=recently_completed,
        )

    async def get_productivity_context(
        self,
        user_id: UUID,
        max_items: int = 10,
    ) -> ProductivityContextSummary:
        dashboard = await self.get_dashboard(user_id)
        proj_summaries = [
            f"Project '{p.name}' ({p.status.value}, {p.progress_percentage}% completed: {p.completed_task_count}/{p.task_count} tasks)"
            for p in dashboard.active_projects[:5]
        ]
        overdue_summaries = [
            f"OVERDUE: '{t.title}' (priority: {t.priority.value}, due: {t.due_date.strftime('%Y-%m-%d') if t.due_date else ''})"
            for t in dashboard.overdue_tasks[:5]
        ]
        pending_summaries = [
            f"Task: '{t.title}' [{t.status.value}] (priority: {t.priority.value}" +
            (f", due: {t.due_date.strftime('%Y-%m-%d')}" if t.due_date else "") + ")"
            for t in dashboard.upcoming_tasks[:8]
        ]
        goal_summaries = [
            f"Goal '{g.title}' ({g.status.value}" +
            (f", progress: {g.current_value}/{g.target_value} {g.unit or ''}" if g.target_value else "") + ")"
            for g in dashboard.active_goals[:5]
        ]

        return ProductivityContextSummary(
            active_projects_summary=proj_summaries,
            overdue_tasks_summary=overdue_summaries,
            pending_tasks_summary=pending_summaries,
            active_goals_summary=goal_summaries,
            total_active_tasks=dashboard.active_tasks_count,
            total_active_projects=dashboard.active_projects_count,
            total_active_goals=dashboard.active_goals_count,
        )

