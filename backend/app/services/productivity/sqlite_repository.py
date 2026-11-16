"""SQLite repository for AUREN Phase 3C.4 Productivity Core.

Disk-backed local-development and offline-testing adapter providing:
- Strict ownership verification on all operations.
- Cross-tenant relationship validation (preventing foreign project, goal, or parent task linking).
- Derived progress calculations for projects and goals.
- Immediate write transaction locks with atomic rollback.
- Asynchronous non-blocking contract via asyncio.to_thread.
"""

import asyncio
from datetime import date, datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

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

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_DB_PATH = DB_DIR / "auren_productivity.db"


class SQLiteProductivityRepository(BaseProductivityRepository):
    """SQLite implementation of BaseProductivityRepository."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_database(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'in_progress' NOT NULL,
                    target_date TEXT,
                    target_value REAL,
                    current_value REAL DEFAULT 0,
                    unit TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_goals_user_status ON goals(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_goals_user_created ON goals(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    color TEXT DEFAULT '#4872bd',
                    status TEXT DEFAULT 'active' NOT NULL,
                    start_date TEXT,
                    target_date TEXT,
                    completed_at TEXT,
                    goal_id TEXT REFERENCES goals(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_projects_user_status ON projects(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_projects_goal_id ON projects(goal_id);
                CREATE INDEX IF NOT EXISTS idx_projects_user_created ON projects(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
                    goal_id TEXT REFERENCES goals(id) ON DELETE SET NULL,
                    parent_task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'todo' NOT NULL,
                    priority TEXT DEFAULT 'medium' NOT NULL,
                    due_date TEXT,
                    start_date TEXT,
                    completed_at TEXT,
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_goal_id ON tasks(goal_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON tasks(parent_task_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_user_status_due ON tasks(user_id, status, due_date);
                CREATE INDEX IF NOT EXISTS idx_tasks_user_created ON tasks(user_id, created_at DESC);
            """)
            conn.commit()

    # ------------------------------------------------------------------------
    # Row to Model Mappings
    # ------------------------------------------------------------------------

    def _row_to_task(self, row: sqlite3.Row, project_name: Optional[str] = None, goal_title: Optional[str] = None, subtask_count: int = 0) -> TaskModel:
        tags_raw = row["tags"]
        tags: List[str] = []
        if tags_raw:
            try:
                tags = json.loads(tags_raw)
            except Exception:
                tags = []

        return TaskModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            title=row["title"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            project_id=UUID(row["project_id"]) if row["project_id"] else None,
            goal_id=UUID(row["goal_id"]) if row["goal_id"] else None,
            parent_task_id=UUID(row["parent_task_id"]) if row["parent_task_id"] else None,
            due_date=datetime.fromisoformat(row["due_date"]) if row["due_date"] else None,
            start_date=datetime.fromisoformat(row["start_date"]) if row["start_date"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            tags=tags,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            project_name=project_name,
            goal_title=goal_title,
            subtask_count=subtask_count,
        )

    def _row_to_project(self, row: sqlite3.Row, task_count: int = 0, completed_task_count: int = 0, goal_title: Optional[str] = None) -> ProjectModel:
        progress = 0.0
        if task_count > 0:
            progress = round((completed_task_count / task_count) * 100.0, 1)

        start_date_val = None
        if row["start_date"]:
            try:
                start_date_val = date.fromisoformat(row["start_date"].split("T")[0])
            except Exception:
                pass

        target_date_val = None
        if row["target_date"]:
            try:
                target_date_val = date.fromisoformat(row["target_date"].split("T")[0])
            except Exception:
                pass

        return ProjectModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            name=row["name"],
            description=row["description"],
            color=row["color"] or "#4872bd",
            status=ProjectStatus(row["status"]),
            start_date=start_date_val,
            target_date=target_date_val,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            goal_id=UUID(row["goal_id"]) if row["goal_id"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            goal_title=goal_title,
            task_count=task_count,
            completed_task_count=completed_task_count,
            progress_percentage=progress,
        )

    def _row_to_goal(self, row: sqlite3.Row, project_count: int = 0, task_count: int = 0, completed_task_count: int = 0) -> GoalModel:
        target_date_val = None
        if row["target_date"]:
            try:
                target_date_val = date.fromisoformat(row["target_date"].split("T")[0])
            except Exception:
                pass

        target_val = float(row["target_value"]) if row["target_value"] is not None else None
        current_val = float(row["current_value"]) if row["current_value"] is not None else 0.0

        # Calculate progress
        progress_percentage: Optional[float] = None
        status = row["status"]
        if target_val and target_val > 0:
            progress_percentage = min(100.0, max(0.0, round((current_val / target_val) * 100.0, 1)))
        elif status in ("achieved", "completed"):
            progress_percentage = 100.0
        elif task_count > 0:
            progress_percentage = round((completed_task_count / task_count) * 100.0, 1)

        return GoalModel(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            title=row["title"],
            description=row["description"],
            status=GoalStatus(row["status"]),
            target_date=target_date_val,
            target_value=target_val,
            current_value=current_val,
            unit=row["unit"],
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            progress_percentage=progress_percentage,
            project_count=project_count,
            task_count=task_count,
        )

    # ------------------------------------------------------------------------
    # Synchronous Task Implementations
    # ------------------------------------------------------------------------

    def _sync_create_task(self, user_id: UUID, task: TaskCreate) -> TaskModel:
        now_iso = datetime.now(timezone.utc).isoformat()
        task_id = str(uuid4())
        u_id = str(user_id)

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                # 1. Validate project ownership if project_id provided
                if task.project_id:
                    p_row = conn.execute(
                        "SELECT id FROM projects WHERE id = ? AND user_id = ?;",
                        (str(task.project_id), u_id),
                    ).fetchone()
                    if not p_row:
                        raise ValueError(f"Project {task.project_id} not found or access denied")

                # 2. Validate goal ownership if goal_id provided
                if task.goal_id:
                    g_row = conn.execute(
                        "SELECT id FROM goals WHERE id = ? AND user_id = ?;",
                        (str(task.goal_id), u_id),
                    ).fetchone()
                    if not g_row:
                        raise ValueError(f"Goal {task.goal_id} not found or access denied")

                # 3. Validate parent_task ownership if parent_task_id provided
                if task.parent_task_id:
                    pt_row = conn.execute(
                        "SELECT id FROM tasks WHERE id = ? AND user_id = ?;",
                        (str(task.parent_task_id), u_id),
                    ).fetchone()
                    if not pt_row:
                        raise ValueError(f"Parent task {task.parent_task_id} not found or access denied")

                completed_at = now_iso if task.status == TaskStatus.completed else None
                due_date_iso = task.due_date.isoformat() if task.due_date else None
                start_date_iso = task.start_date.isoformat() if task.start_date else None
                tags_json = json.dumps(task.tags or [])

                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, user_id, project_id, goal_id, parent_task_id,
                        title, description, status, priority, due_date, start_date,
                        completed_at, tags, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        task_id,
                        u_id,
                        str(task.project_id) if task.project_id else None,
                        str(task.goal_id) if task.goal_id else None,
                        str(task.parent_task_id) if task.parent_task_id else None,
                        task.title,
                        task.description,
                        task.status.value,
                        task.priority.value,
                        due_date_iso,
                        start_date_iso,
                        completed_at,
                        tags_json,
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return self._sync_get_task(user_id, UUID(task_id))  # type: ignore

    def _sync_get_task(self, user_id: UUID, task_id: UUID) -> Optional[TaskModel]:
        u_id = str(user_id)
        t_id = str(task_id)
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT t.*, p.name as project_name, g.title as goal_title,
                       (SELECT COUNT(*) FROM tasks sub WHERE sub.parent_task_id = t.id) as subtask_count
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                LEFT JOIN goals g ON t.goal_id = g.id AND g.user_id = t.user_id
                WHERE t.id = ? AND t.user_id = ?;
                """,
                (t_id, u_id),
            ).fetchone()
            if not row:
                return None
            return self._row_to_task(
                row,
                project_name=row["project_name"],
                goal_title=row["goal_title"],
                subtask_count=row["subtask_count"] or 0,
            )

    def _sync_list_tasks(
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
        u_id = str(user_id)
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        conditions = ["t.user_id = ?"]
        params: List[Any] = [u_id]

        if project_id:
            conditions.append("t.project_id = ?")
            params.append(str(project_id))
        if goal_id:
            conditions.append("t.goal_id = ?")
            params.append(str(goal_id))
        if status:
            conditions.append("t.status = ?")
            params.append(status)
        if priority:
            conditions.append("t.priority = ?")
            params.append(priority)
        if parent_task_id:
            conditions.append("t.parent_task_id = ?")
            params.append(str(parent_task_id))
        if query:
            conditions.append("(t.title LIKE ? OR t.description LIKE ?)")
            q = f"%{query.strip()}%"
            params.extend([q, q])

        where_clause = " AND ".join(conditions)

        with self._get_connection() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) FROM tasks t WHERE {where_clause};",
                params,
            ).fetchone()
            total = count_row[0] if count_row else 0

            # Query items
            query_sql = f"""
                SELECT t.*, p.name as project_name, g.title as goal_title,
                       (SELECT COUNT(*) FROM tasks sub WHERE sub.parent_task_id = t.id) as subtask_count
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                LEFT JOIN goals g ON t.goal_id = g.id AND g.user_id = t.user_id
                WHERE {where_clause}
                ORDER BY 
                    CASE 
                        WHEN t.status = 'completed' THEN 2 
                        WHEN t.status = 'cancelled' THEN 3 
                        ELSE 1 
                    END,
                    CASE WHEN t.due_date IS NOT NULL THEN 0 ELSE 1 END,
                    t.due_date ASC,
                    t.created_at DESC
                LIMIT ? OFFSET ?;
            """
            item_params = params + [page_size, offset]
            rows = conn.execute(query_sql, item_params).fetchall()
            items = [
                self._row_to_task(
                    r,
                    project_name=r["project_name"],
                    goal_title=r["goal_title"],
                    subtask_count=r["subtask_count"] or 0,
                )
                for r in rows
            ]
            return items, total

    def _sync_update_task(
        self,
        user_id: UUID,
        task_id: UUID,
        update: TaskUpdate,
    ) -> Optional[TaskModel]:
        u_id = str(user_id)
        t_id = str(task_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT * FROM tasks WHERE id = ? AND user_id = ?;",
                    (t_id, u_id),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return None

                # Validate project ownership if changing project_id
                if update.project_id is not None:
                    p_row = conn.execute(
                        "SELECT id FROM projects WHERE id = ? AND user_id = ?;",
                        (str(update.project_id), u_id),
                    ).fetchone()
                    if not p_row:
                        raise ValueError(f"Project {update.project_id} not found or access denied")

                # Validate goal ownership if changing goal_id
                if update.goal_id is not None:
                    g_row = conn.execute(
                        "SELECT id FROM goals WHERE id = ? AND user_id = ?;",
                        (str(update.goal_id), u_id),
                    ).fetchone()
                    if not g_row:
                        raise ValueError(f"Goal {update.goal_id} not found or access denied")

                # Validate parent_task ownership if changing parent_task_id
                if update.parent_task_id is not None:
                    if str(update.parent_task_id) == t_id:
                        raise ValueError("A task cannot be its own parent")
                    pt_row = conn.execute(
                        "SELECT id FROM tasks WHERE id = ? AND user_id = ?;",
                        (str(update.parent_task_id), u_id),
                    ).fetchone()
                    if not pt_row:
                        raise ValueError(f"Parent task {update.parent_task_id} not found or access denied")

                updates: Dict[str, Any] = {"updated_at": now_iso}

                if update.title is not None:
                    updates["title"] = update.title
                if update.description is not None:
                    updates["description"] = update.description
                if update.status is not None:
                    updates["status"] = update.status.value
                    if update.status == TaskStatus.completed:
                        updates["completed_at"] = row["completed_at"] or now_iso
                    else:
                        updates["completed_at"] = None
                if update.priority is not None:
                    updates["priority"] = update.priority.value
                if update.project_id is not None:
                    updates["project_id"] = str(update.project_id)
                if update.goal_id is not None:
                    updates["goal_id"] = str(update.goal_id)
                if update.parent_task_id is not None:
                    updates["parent_task_id"] = str(update.parent_task_id)
                if update.due_date is not None:
                    updates["due_date"] = update.due_date.isoformat()
                if update.start_date is not None:
                    updates["start_date"] = update.start_date.isoformat()
                if update.tags is not None:
                    updates["tags"] = json.dumps(update.tags)

                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [t_id, u_id]

                conn.execute(
                    f"UPDATE tasks SET {set_clause} WHERE id = ? AND user_id = ?;",
                    values,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return self._sync_get_task(user_id, task_id)

    def _sync_delete_task(self, user_id: UUID, task_id: UUID) -> bool:
        u_id = str(user_id)
        t_id = str(task_id)
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT id FROM tasks WHERE id = ? AND user_id = ?;",
                    (t_id, u_id),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return False

                conn.execute(
                    "DELETE FROM tasks WHERE id = ? AND user_id = ?;",
                    (t_id, u_id),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------------------
    # Synchronous Project Implementations
    # ------------------------------------------------------------------------

    def _sync_create_project(self, user_id: UUID, project: ProjectCreate) -> ProjectModel:
        now_iso = datetime.now(timezone.utc).isoformat()
        project_id = str(uuid4())
        u_id = str(user_id)

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                if project.goal_id:
                    g_row = conn.execute(
                        "SELECT id FROM goals WHERE id = ? AND user_id = ?;",
                        (str(project.goal_id), u_id),
                    ).fetchone()
                    if not g_row:
                        raise ValueError(f"Goal {project.goal_id} not found or access denied")

                completed_at = now_iso if project.status == ProjectStatus.completed else None
                start_date_str = project.start_date.isoformat() if project.start_date else None
                target_date_str = project.target_date.isoformat() if project.target_date else None

                conn.execute(
                    """
                    INSERT INTO projects (
                        id, user_id, name, description, color, status,
                        start_date, target_date, completed_at, goal_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        project_id,
                        u_id,
                        project.name,
                        project.description,
                        project.color or "#4872bd",
                        project.status.value,
                        start_date_str,
                        target_date_str,
                        completed_at,
                        str(project.goal_id) if project.goal_id else None,
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        p = self._sync_get_project(user_id, UUID(project_id))
        assert p is not None
        return p

    def _sync_get_project(self, user_id: UUID, project_id: UUID) -> Optional[ProjectDetailModel]:
        u_id = str(user_id)
        p_id = str(project_id)
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT p.*, g.title as goal_title,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id AND t.status = 'completed') as completed_task_count
                FROM projects p
                LEFT JOIN goals g ON p.goal_id = g.id AND g.user_id = p.user_id
                WHERE p.id = ? AND p.user_id = ?;
                """,
                (p_id, u_id),
            ).fetchone()
            if not row:
                return None

            base_proj = self._row_to_project(
                row,
                task_count=row["task_count"] or 0,
                completed_task_count=row["completed_task_count"] or 0,
                goal_title=row["goal_title"],
            )

            # Retrieve associated tasks
            t_rows = conn.execute(
                """
                SELECT t.*, p.name as project_name, g.title as goal_title,
                       (SELECT COUNT(*) FROM tasks sub WHERE sub.parent_task_id = t.id) as subtask_count
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                LEFT JOIN goals g ON t.goal_id = g.id AND g.user_id = t.user_id
                WHERE t.project_id = ? AND t.user_id = ?
                ORDER BY 
                    CASE 
                        WHEN t.status = 'completed' THEN 2 
                        WHEN t.status = 'cancelled' THEN 3 
                        ELSE 1 
                    END,
                    t.created_at DESC;
                """,
                (p_id, u_id),
            ).fetchall()

            tasks = [
                self._row_to_task(
                    tr,
                    project_name=tr["project_name"],
                    goal_title=tr["goal_title"],
                    subtask_count=tr["subtask_count"] or 0,
                )
                for tr in t_rows
            ]

            return ProjectDetailModel(
                **base_proj.model_dump(),
                tasks=tasks,
            )

    def _sync_list_projects(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        goal_id: Optional[UUID] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ProjectModel], int]:
        u_id = str(user_id)
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        conditions = ["p.user_id = ?"]
        params: List[Any] = [u_id]

        if status:
            conditions.append("p.status = ?")
            params.append(status)
        if goal_id:
            conditions.append("p.goal_id = ?")
            params.append(str(goal_id))
        if query:
            conditions.append("(p.name LIKE ? OR p.description LIKE ?)")
            q = f"%{query.strip()}%"
            params.extend([q, q])

        where_clause = " AND ".join(conditions)

        with self._get_connection() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) FROM projects p WHERE {where_clause};",
                params,
            ).fetchone()
            total = count_row[0] if count_row else 0

            query_sql = f"""
                SELECT p.*, g.title as goal_title,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id AND t.status = 'completed') as completed_task_count
                FROM projects p
                LEFT JOIN goals g ON p.goal_id = g.id AND g.user_id = p.user_id
                WHERE {where_clause}
                ORDER BY 
                    CASE 
                        WHEN p.status = 'active' THEN 1 
                        WHEN p.status = 'planning' THEN 2 
                        WHEN p.status = 'on_hold' THEN 3 
                        WHEN p.status = 'completed' THEN 4 
                        ELSE 5 
                    END,
                    p.created_at DESC
                LIMIT ? OFFSET ?;
            """
            rows = conn.execute(query_sql, params + [page_size, offset]).fetchall()
            items = [
                self._row_to_project(
                    r,
                    task_count=r["task_count"] or 0,
                    completed_task_count=r["completed_task_count"] or 0,
                    goal_title=r["goal_title"],
                )
                for r in rows
            ]
            return items, total

    def _sync_update_project(
        self,
        user_id: UUID,
        project_id: UUID,
        update: ProjectUpdate,
    ) -> Optional[ProjectModel]:
        u_id = str(user_id)
        p_id = str(project_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT * FROM projects WHERE id = ? AND user_id = ?;",
                    (p_id, u_id),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return None

                if update.goal_id is not None:
                    g_row = conn.execute(
                        "SELECT id FROM goals WHERE id = ? AND user_id = ?;",
                        (str(update.goal_id), u_id),
                    ).fetchone()
                    if not g_row:
                        raise ValueError(f"Goal {update.goal_id} not found or access denied")

                updates: Dict[str, Any] = {"updated_at": now_iso}

                if update.name is not None:
                    updates["name"] = update.name
                if update.description is not None:
                    updates["description"] = update.description
                if update.color is not None:
                    updates["color"] = update.color
                if update.status is not None:
                    updates["status"] = update.status.value
                    if update.status == ProjectStatus.completed:
                        updates["completed_at"] = row["completed_at"] or now_iso
                    else:
                        updates["completed_at"] = None
                if update.start_date is not None:
                    updates["start_date"] = update.start_date.isoformat()
                if update.target_date is not None:
                    updates["target_date"] = update.target_date.isoformat()
                if update.goal_id is not None:
                    updates["goal_id"] = str(update.goal_id)

                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [p_id, u_id]

                conn.execute(
                    f"UPDATE projects SET {set_clause} WHERE id = ? AND user_id = ?;",
                    values,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        p = self._sync_get_project(user_id, project_id)
        return p

    def _sync_delete_project(
        self,
        user_id: UUID,
        project_id: UUID,
        delete_tasks: bool = False,
    ) -> bool:
        u_id = str(user_id)
        p_id = str(project_id)

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT id FROM projects WHERE id = ? AND user_id = ?;",
                    (p_id, u_id),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return False

                if delete_tasks:
                    conn.execute("DELETE FROM tasks WHERE project_id = ? AND user_id = ?;", (p_id, u_id))
                else:
                    conn.execute("UPDATE tasks SET project_id = NULL WHERE project_id = ? AND user_id = ?;", (p_id, u_id))

                conn.execute("DELETE FROM projects WHERE id = ? AND user_id = ?;", (p_id, u_id))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------------------
    # Synchronous Goal Implementations
    # ------------------------------------------------------------------------

    def _sync_create_goal(self, user_id: UUID, goal: GoalCreate) -> GoalModel:
        now_iso = datetime.now(timezone.utc).isoformat()
        goal_id = str(uuid4())
        u_id = str(user_id)

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                completed_at = now_iso if goal.status in (GoalStatus.achieved, GoalStatus.completed) else None
                target_date_str = goal.target_date.isoformat() if goal.target_date else None

                conn.execute(
                    """
                    INSERT INTO goals (
                        id, user_id, title, description, status,
                        target_date, target_value, current_value, unit,
                        completed_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        goal_id,
                        u_id,
                        goal.title,
                        goal.description,
                        goal.status.value,
                        target_date_str,
                        goal.target_value,
                        goal.current_value or 0.0,
                        goal.unit,
                        completed_at,
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        g = self._sync_get_goal(user_id, UUID(goal_id))
        assert g is not None
        return g

    def _sync_get_goal(self, user_id: UUID, goal_id: UUID) -> Optional[GoalDetailModel]:
        u_id = str(user_id)
        g_id = str(goal_id)

        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT g.*,
                       (SELECT COUNT(*) FROM projects p WHERE p.goal_id = g.id AND p.user_id = g.user_id) as project_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.user_id = g.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.user_id = g.user_id AND t.status = 'completed') as completed_task_count
                FROM goals g
                WHERE g.id = ? AND g.user_id = ?;
                """,
                (g_id, u_id),
            ).fetchone()
            if not row:
                return None

            base_goal = self._row_to_goal(
                row,
                project_count=row["project_count"] or 0,
                task_count=row["task_count"] or 0,
                completed_task_count=row["completed_task_count"] or 0,
            )

            # Fetch linked projects
            p_rows = conn.execute(
                """
                SELECT p.*,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id AND t.status = 'completed') as completed_task_count
                FROM projects p
                WHERE p.goal_id = ? AND p.user_id = ?
                ORDER BY p.created_at DESC;
                """,
                (g_id, u_id),
            ).fetchall()
            projects = [
                self._row_to_project(
                    pr,
                    task_count=pr["task_count"] or 0,
                    completed_task_count=pr["completed_task_count"] or 0,
                    goal_title=base_goal.title,
                )
                for pr in p_rows
            ]

            # Fetch linked tasks
            t_rows = conn.execute(
                """
                SELECT t.*, p.name as project_name, g.title as goal_title,
                       (SELECT COUNT(*) FROM tasks sub WHERE sub.parent_task_id = t.id) as subtask_count
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                LEFT JOIN goals g ON t.goal_id = g.id AND g.user_id = t.user_id
                WHERE t.goal_id = ? AND t.user_id = ?
                ORDER BY t.created_at DESC;
                """,
                (g_id, u_id),
            ).fetchall()
            tasks = [
                self._row_to_task(
                    tr,
                    project_name=tr["project_name"],
                    goal_title=tr["goal_title"],
                    subtask_count=tr["subtask_count"] or 0,
                )
                for tr in t_rows
            ]

            return GoalDetailModel(
                **base_goal.model_dump(),
                projects=projects,
                tasks=tasks,
            )

    def _sync_list_goals(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[GoalModel], int]:
        u_id = str(user_id)
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        conditions = ["g.user_id = ?"]
        params: List[Any] = [u_id]

        if status:
            conditions.append("g.status = ?")
            params.append(status)
        if query:
            conditions.append("(g.title LIKE ? OR g.description LIKE ?)")
            q = f"%{query.strip()}%"
            params.extend([q, q])

        where_clause = " AND ".join(conditions)

        with self._get_connection() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) FROM goals g WHERE {where_clause};",
                params,
            ).fetchone()
            total = count_row[0] if count_row else 0

            query_sql = f"""
                SELECT g.*,
                       (SELECT COUNT(*) FROM projects p WHERE p.goal_id = g.id AND p.user_id = g.user_id) as project_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.user_id = g.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.user_id = g.user_id AND t.status = 'completed') as completed_task_count
                FROM goals g
                WHERE {where_clause}
                ORDER BY 
                    CASE 
                        WHEN g.status = 'in_progress' THEN 1 
                        WHEN g.status = 'not_started' THEN 2 
                        WHEN g.status = 'paused' THEN 3 
                        WHEN g.status = 'achieved' THEN 4 
                        ELSE 5 
                    END,
                    g.created_at DESC
                LIMIT ? OFFSET ?;
            """
            rows = conn.execute(query_sql, params + [page_size, offset]).fetchall()
            items = [
                self._row_to_goal(
                    r,
                    project_count=r["project_count"] or 0,
                    task_count=r["task_count"] or 0,
                    completed_task_count=r["completed_task_count"] or 0,
                )
                for r in rows
            ]
            return items, total

    def _sync_update_goal(
        self,
        user_id: UUID,
        goal_id: UUID,
        update: GoalUpdate,
    ) -> Optional[GoalModel]:
        u_id = str(user_id)
        g_id = str(goal_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT * FROM goals WHERE id = ? AND user_id = ?;",
                    (g_id, u_id),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return None

                updates: Dict[str, Any] = {"updated_at": now_iso}

                if update.title is not None:
                    updates["title"] = update.title
                if update.description is not None:
                    updates["description"] = update.description
                if update.status is not None:
                    updates["status"] = update.status.value
                    if update.status in (GoalStatus.achieved, GoalStatus.completed):
                        updates["completed_at"] = row["completed_at"] or now_iso
                    else:
                        updates["completed_at"] = None
                if update.target_date is not None:
                    updates["target_date"] = update.target_date.isoformat()
                if update.target_value is not None:
                    updates["target_value"] = update.target_value
                if update.current_value is not None:
                    updates["current_value"] = update.current_value
                if update.unit is not None:
                    updates["unit"] = update.unit

                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [g_id, u_id]

                conn.execute(
                    f"UPDATE goals SET {set_clause} WHERE id = ? AND user_id = ?;",
                    values,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        g = self._sync_get_goal(user_id, goal_id)
        return g

    def _sync_delete_goal(self, user_id: UUID, goal_id: UUID) -> bool:
        u_id = str(user_id)
        g_id = str(goal_id)

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT id FROM goals WHERE id = ? AND user_id = ?;",
                    (g_id, u_id),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return False

                conn.execute("UPDATE projects SET goal_id = NULL WHERE goal_id = ? AND user_id = ?;", (g_id, u_id))
                conn.execute("UPDATE tasks SET goal_id = NULL WHERE goal_id = ? AND user_id = ?;", (g_id, u_id))
                conn.execute("DELETE FROM goals WHERE id = ? AND user_id = ?;", (g_id, u_id))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------------------
    # Synchronous Dashboard and Context Implementations
    # ------------------------------------------------------------------------

    def _sync_get_dashboard(self, user_id: UUID) -> ProductivityDashboardResponse:
        u_id = str(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            # Aggregate counts
            counts_row = conn.execute(
                """
                SELECT 
                    (SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status IN ('todo', 'in_progress', 'blocked')) as active_tasks,
                    (SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status IN ('todo', 'in_progress', 'blocked') AND due_date IS NOT NULL AND due_date < ?) as overdue_tasks,
                    (SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed') as completed_tasks,
                    (SELECT COUNT(*) FROM projects WHERE user_id = ? AND status IN ('planning', 'active', 'on_hold')) as active_projects,
                    (SELECT COUNT(*) FROM goals WHERE user_id = ? AND status IN ('not_started', 'in_progress')) as active_goals;
                """,
                (u_id, u_id, now_iso, u_id, u_id, u_id),
            ).fetchone()

            # Overdue tasks (up to 6)
            overdue_rows = conn.execute(
                """
                SELECT t.*, p.name as project_name, g.title as goal_title, 0 as subtask_count
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                LEFT JOIN goals g ON t.goal_id = g.id AND g.user_id = t.user_id
                WHERE t.user_id = ? AND t.status IN ('todo', 'in_progress', 'blocked') AND t.due_date IS NOT NULL AND t.due_date < ?
                ORDER BY t.due_date ASC
                LIMIT 6;
                """,
                (u_id, now_iso),
            ).fetchall()

            # Upcoming tasks (due in future, up to 6)
            upcoming_rows = conn.execute(
                """
                SELECT t.*, p.name as project_name, g.title as goal_title, 0 as subtask_count
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                LEFT JOIN goals g ON t.goal_id = g.id AND g.user_id = t.user_id
                WHERE t.user_id = ? AND t.status IN ('todo', 'in_progress') AND (t.due_date IS NULL OR t.due_date >= ?)
                ORDER BY 
                    CASE WHEN t.due_date IS NOT NULL THEN 0 ELSE 1 END,
                    t.due_date ASC,
                    CASE t.priority 
                        WHEN 'urgent' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        ELSE 4 
                    END,
                    t.created_at DESC
                LIMIT 6;
                """,
                (u_id, now_iso),
            ).fetchall()

            # Active projects (up to 6)
            proj_rows = conn.execute(
                """
                SELECT p.*, g.title as goal_title,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id AND t.status = 'completed') as completed_task_count
                FROM projects p
                LEFT JOIN goals g ON p.goal_id = g.id AND g.user_id = p.user_id
                WHERE p.user_id = ? AND p.status IN ('planning', 'active', 'on_hold')
                ORDER BY p.updated_at DESC
                LIMIT 6;
                """,
                (u_id,),
            ).fetchall()

            # Active goals (up to 6)
            goal_rows = conn.execute(
                """
                SELECT g.*,
                       (SELECT COUNT(*) FROM projects p WHERE p.goal_id = g.id AND p.user_id = g.user_id) as project_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.user_id = g.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.user_id = g.user_id AND t.status = 'completed') as completed_task_count
                FROM goals g
                WHERE g.user_id = ? AND g.status IN ('not_started', 'in_progress')
                ORDER BY g.updated_at DESC
                LIMIT 6;
                """,
                (u_id,),
            ).fetchall()

            # Recently completed tasks (up to 5)
            comp_rows = conn.execute(
                """
                SELECT t.*, p.name as project_name, g.title as goal_title, 0 as subtask_count
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                LEFT JOIN goals g ON t.goal_id = g.id AND g.user_id = t.user_id
                WHERE t.user_id = ? AND t.status = 'completed'
                ORDER BY t.completed_at DESC, t.updated_at DESC
                LIMIT 5;
                """,
                (u_id,),
            ).fetchall()

            return ProductivityDashboardResponse(
                active_tasks_count=counts_row["active_tasks"] if counts_row else 0,
                overdue_tasks_count=counts_row["overdue_tasks"] if counts_row else 0,
                completed_tasks_count=counts_row["completed_tasks"] if counts_row else 0,
                active_projects_count=counts_row["active_projects"] if counts_row else 0,
                active_goals_count=counts_row["active_goals"] if counts_row else 0,
                overdue_tasks=[self._row_to_task(r, r["project_name"], r["goal_title"]) for r in overdue_rows],
                upcoming_tasks=[self._row_to_task(r, r["project_name"], r["goal_title"]) for r in upcoming_rows],
                active_projects=[self._row_to_project(r, r["task_count"] or 0, r["completed_task_count"] or 0, r["goal_title"]) for r in proj_rows],
                active_goals=[self._row_to_goal(r, r["project_count"] or 0, r["task_count"] or 0, r["completed_task_count"] or 0) for r in goal_rows],
                recently_completed_tasks=[self._row_to_task(r, r["project_name"], r["goal_title"]) for r in comp_rows],
            )

    def _sync_get_productivity_context(
        self,
        user_id: UUID,
        max_items: int = 10,
    ) -> ProductivityContextSummary:
        u_id = str(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            # Active projects
            proj_rows = conn.execute(
                """
                SELECT name, status,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.user_id = p.user_id AND t.status = 'completed') as completed_task_count
                FROM projects p
                WHERE user_id = ? AND status IN ('planning', 'active', 'on_hold')
                ORDER BY updated_at DESC LIMIT 5;
                """,
                (u_id,),
            ).fetchall()

            proj_summaries = []
            for r in proj_rows:
                pct = 0.0
                tc = r["task_count"] or 0
                cc = r["completed_task_count"] or 0
                if tc > 0:
                    pct = round((cc / tc) * 100.0)
                proj_summaries.append(f"Project '{r['name']}' ({r['status']}, {pct}% completed: {cc}/{tc} tasks)")

            # Overdue tasks
            overdue_rows = conn.execute(
                """
                SELECT t.title, t.priority, t.due_date, p.name as project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                WHERE t.user_id = ? AND t.status IN ('todo', 'in_progress', 'blocked') AND t.due_date IS NOT NULL AND t.due_date < ?
                ORDER BY t.due_date ASC LIMIT 5;
                """,
                (u_id, now_iso),
            ).fetchall()

            overdue_summaries = [
                f"OVERDUE: '{r['title']}' (priority: {r['priority']}, due: {r['due_date'].split('T')[0]}" +
                (f", in project '{r['project_name']}'" if r['project_name'] else "") + ")"
                for r in overdue_rows
            ]

            # Pending high-priority or upcoming tasks
            pending_rows = conn.execute(
                """
                SELECT t.title, t.status, t.priority, t.due_date, p.name as project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id AND p.user_id = t.user_id
                WHERE t.user_id = ? AND t.status IN ('todo', 'in_progress')
                ORDER BY 
                    CASE t.priority 
                        WHEN 'urgent' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        ELSE 4 
                    END,
                    t.created_at DESC LIMIT 8;
                """,
                (u_id,),
            ).fetchall()

            pending_summaries = [
                f"Task: '{r['title']}' [{r['status']}] (priority: {r['priority']}" +
                (f", due: {r['due_date'].split('T')[0]}" if r['due_date'] else "") +
                (f", project: '{r['project_name']}'" if r['project_name'] else "") + ")"
                for r in pending_rows
            ]

            # Active goals
            goal_rows = conn.execute(
                """
                SELECT title, status, target_value, current_value, unit
                FROM goals
                WHERE user_id = ? AND status IN ('not_started', 'in_progress')
                ORDER BY updated_at DESC LIMIT 5;
                """,
                (u_id,),
            ).fetchall()

            goal_summaries = []
            for r in goal_rows:
                metric_str = ""
                if r["target_value"]:
                    metric_str = f", progress: {r['current_value'] or 0}/{r['target_value']} {r['unit'] or ''}"
                goal_summaries.append(f"Goal '{r['title']}' ({r['status']}{metric_str})")

            # Total counts
            tot_row = conn.execute(
                """
                SELECT 
                    (SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status IN ('todo', 'in_progress', 'blocked')) as tot_tasks,
                    (SELECT COUNT(*) FROM projects WHERE user_id = ? AND status IN ('planning', 'active', 'on_hold')) as tot_projects,
                    (SELECT COUNT(*) FROM goals WHERE user_id = ? AND status IN ('not_started', 'in_progress')) as tot_goals;
                """,
                (u_id, u_id, u_id),
            ).fetchone()

            return ProductivityContextSummary(
                active_projects_summary=proj_summaries,
                overdue_tasks_summary=overdue_summaries,
                pending_tasks_summary=pending_summaries,
                active_goals_summary=goal_summaries,
                total_active_tasks=tot_row["tot_tasks"] if tot_row else 0,
                total_active_projects=tot_row["tot_projects"] if tot_row else 0,
                total_active_goals=tot_row["tot_goals"] if tot_row else 0,
            )

    # ------------------------------------------------------------------------
    # Asynchronous Public Interface (Delegating to Thread Worker)
    # ------------------------------------------------------------------------

    async def create_task(self, user_id: UUID, task: TaskCreate) -> TaskModel:
        return await asyncio.to_thread(self._sync_create_task, user_id, task)

    async def get_task(self, user_id: UUID, task_id: UUID) -> Optional[TaskModel]:
        return await asyncio.to_thread(self._sync_get_task, user_id, task_id)

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
        return await asyncio.to_thread(
            self._sync_list_tasks,
            user_id,
            project_id,
            goal_id,
            status,
            priority,
            query,
            parent_task_id,
            page,
            page_size,
        )

    async def update_task(
        self,
        user_id: UUID,
        task_id: UUID,
        update: TaskUpdate,
    ) -> Optional[TaskModel]:
        return await asyncio.to_thread(self._sync_update_task, user_id, task_id, update)

    async def delete_task(self, user_id: UUID, task_id: UUID) -> bool:
        return await asyncio.to_thread(self._sync_delete_task, user_id, task_id)

    async def create_project(self, user_id: UUID, project: ProjectCreate) -> ProjectModel:
        return await asyncio.to_thread(self._sync_create_project, user_id, project)

    async def get_project(self, user_id: UUID, project_id: UUID) -> Optional[ProjectDetailModel]:
        return await asyncio.to_thread(self._sync_get_project, user_id, project_id)

    async def list_projects(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        goal_id: Optional[UUID] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ProjectModel], int]:
        return await asyncio.to_thread(
            self._sync_list_projects,
            user_id,
            status,
            goal_id,
            query,
            page,
            page_size,
        )

    async def update_project(
        self,
        user_id: UUID,
        project_id: UUID,
        update: ProjectUpdate,
    ) -> Optional[ProjectModel]:
        return await asyncio.to_thread(self._sync_update_project, user_id, project_id, update)

    async def delete_project(
        self,
        user_id: UUID,
        project_id: UUID,
        delete_tasks: bool = False,
    ) -> bool:
        return await asyncio.to_thread(self._sync_delete_project, user_id, project_id, delete_tasks)

    async def create_goal(self, user_id: UUID, goal: GoalCreate) -> GoalModel:
        return await asyncio.to_thread(self._sync_create_goal, user_id, goal)

    async def get_goal(self, user_id: UUID, goal_id: UUID) -> Optional[GoalDetailModel]:
        return await asyncio.to_thread(self._sync_get_goal, user_id, goal_id)

    async def list_goals(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[GoalModel], int]:
        return await asyncio.to_thread(
            self._sync_list_goals,
            user_id,
            status,
            query,
            page,
            page_size,
        )

    async def update_goal(
        self,
        user_id: UUID,
        goal_id: UUID,
        update: GoalUpdate,
    ) -> Optional[GoalModel]:
        return await asyncio.to_thread(self._sync_update_goal, user_id, goal_id, update)

    async def delete_goal(self, user_id: UUID, goal_id: UUID) -> bool:
        return await asyncio.to_thread(self._sync_delete_goal, user_id, goal_id)

    async def get_dashboard(self, user_id: UUID) -> ProductivityDashboardResponse:
        return await asyncio.to_thread(self._sync_get_dashboard, user_id)

    async def get_productivity_context(
        self,
        user_id: UUID,
        max_items: int = 10,
    ) -> ProductivityContextSummary:
        return await asyncio.to_thread(self._sync_get_productivity_context, user_id, max_items)

