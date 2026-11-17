"""Comprehensive tests for AUREN Phase 3C.4 Productivity Core:
1. Task, Project, and Goal CRUD, validation, and lifecycle transitions.
2. Ownership enforcement and cross-user isolation.
3. Cross-entity relationship integrity (project linking, goal linking, subtask hierarchies).
4. Derived progress calculations for projects and goals.
5. Deletion semantics (unlinking tasks vs deleting tasks; unlinking projects/tasks on goal deletion).
6. Productivity dashboard aggregation and metrics correctness.
7. Read-only AI productivity context assembly for conversational assistance.
8. Real PostgreSQL 18 RLS and migration 019 verification.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
import glob
from pathlib import Path
import tempfile
import uuid
from uuid import UUID, uuid4

import asyncpg
import pytest

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
from app.services.productivity.context_manager import ProductivityContextManager
from app.services.productivity.sqlite_repository import SQLiteProductivityRepository

PG_SOCK_DIR = Path("/tmp/auren_pg_sock")
PG_PORT = 54329
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations"

MOCK_AUTH_SQL = """
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE TABLE IF NOT EXISTS auth.users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email TEXT,
        raw_user_meta_data JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE OR REPLACE FUNCTION auth.uid() RETURNS UUID AS $$
        SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::UUID;
    $$ LANGUAGE sql STABLE;
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN CREATE ROLE postgres NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker') THEN CREATE ROLE auren_worker NOLOGIN NOINHERIT; END IF;
    END $$;
"""


@pytest.fixture
def temp_prod_repo():
    """Create an ephemeral SQLite productivity repository with an isolated DB file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_productivity.db"
        repo = SQLiteProductivityRepository(db_path=db_path)
        yield repo


# ============================================================================
# 1. Tasks Tests: CRUD, Lifecycle, and Validation
# ============================================================================

@pytest.mark.asyncio
async def test_task_crud_lifecycle_and_timestamps(temp_prod_repo):
    user_id = uuid4()

    # Create task
    task = await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(
            title="Implement user auth audit",
            description="Verify token validation and session security",
            status=TaskStatus.todo,
            priority=TaskPriority.high,
            due_date=datetime.now(timezone.utc) + timedelta(days=2),
            tags=["security", "auth"],
        ),
    )
    assert task.id is not None
    assert task.user_id == user_id
    assert task.title == "Implement user auth audit"
    assert task.status == TaskStatus.todo
    assert task.priority == TaskPriority.high
    assert task.completed_at is None
    assert "security" in task.tags

    # Read task
    fetched = await temp_prod_repo.get_task(user_id=user_id, task_id=task.id)
    assert fetched is not None
    assert fetched.title == task.title

    # Update to in_progress
    updated = await temp_prod_repo.update_task(
        user_id=user_id,
        task_id=task.id,
        update=TaskUpdate(status=TaskStatus.in_progress),
    )
    assert updated.status == TaskStatus.in_progress
    assert updated.completed_at is None

    # Transition to completed -> completed_at set
    completed = await temp_prod_repo.update_task(
        user_id=user_id,
        task_id=task.id,
        update=TaskUpdate(status=TaskStatus.completed),
    )
    assert completed.status == TaskStatus.completed
    assert completed.completed_at is not None

    # Reopen task -> completed_at reset to None
    reopened = await temp_prod_repo.update_task(
        user_id=user_id,
        task_id=task.id,
        update=TaskUpdate(status=TaskStatus.todo),
    )
    assert reopened.status == TaskStatus.todo
    assert reopened.completed_at is None

    # Delete task
    deleted = await temp_prod_repo.delete_task(user_id=user_id, task_id=task.id)
    assert deleted is True
    assert await temp_prod_repo.get_task(user_id=user_id, task_id=task.id) is None


@pytest.mark.asyncio
async def test_task_cross_user_isolation(temp_prod_repo):
    user_a = uuid4()
    user_b = uuid4()

    task_a = await temp_prod_repo.create_task(
        user_id=user_a,
        task=TaskCreate(title="User A private task"),
    )

    # User B cannot get User A's task
    assert await temp_prod_repo.get_task(user_id=user_b, task_id=task_a.id) is None

    # User B cannot update User A's task
    updated = await temp_prod_repo.update_task(
        user_id=user_b,
        task_id=task_a.id,
        update=TaskUpdate(title="Malicious update by B"),
    )
    assert updated is None

    # User B cannot delete User A's task
    assert await temp_prod_repo.delete_task(user_id=user_b, task_id=task_a.id) is False

    # Task remains unchanged for User A
    check_a = await temp_prod_repo.get_task(user_id=user_a, task_id=task_a.id)
    assert check_a is not None
    assert check_a.title == "User A private task"


# ============================================================================
# 2. Projects & Tasks Relationships and Derived Progress
# ============================================================================

@pytest.mark.asyncio
async def test_project_progress_derived_from_tasks(temp_prod_repo):
    user_id = uuid4()

    # Create project with no tasks -> progress 0.0%
    project = await temp_prod_repo.create_project(
        user_id=user_id,
        project=ProjectCreate(
            name="AUREN v1.0 Launch",
            description="Q4 milestone launch",
            status=ProjectStatus.active,
        ),
    )
    assert project.progress_percentage == 0.0
    assert project.task_count == 0
    assert project.completed_task_count == 0

    # Add 4 tasks to project
    t1 = await temp_prod_repo.create_task(user_id=user_id, task=TaskCreate(title="Task 1", project_id=project.id))
    t2 = await temp_prod_repo.create_task(user_id=user_id, task=TaskCreate(title="Task 2", project_id=project.id))
    t3 = await temp_prod_repo.create_task(user_id=user_id, task=TaskCreate(title="Task 3", project_id=project.id))
    t4 = await temp_prod_repo.create_task(user_id=user_id, task=TaskCreate(title="Task 4", project_id=project.id))

    proj_detail = await temp_prod_repo.get_project(user_id=user_id, project_id=project.id)
    assert proj_detail.task_count == 4
    assert proj_detail.completed_task_count == 0
    assert proj_detail.progress_percentage == 0.0

    # Complete 1 of 4 tasks -> 25.0%
    await temp_prod_repo.update_task(user_id=user_id, task_id=t1.id, update=TaskUpdate(status=TaskStatus.completed))
    proj_detail = await temp_prod_repo.get_project(user_id=user_id, project_id=project.id)
    assert proj_detail.completed_task_count == 1
    assert proj_detail.progress_percentage == 25.0

    # Complete 2nd task -> 50.0%
    await temp_prod_repo.update_task(user_id=user_id, task_id=t2.id, update=TaskUpdate(status=TaskStatus.completed))
    proj_detail = await temp_prod_repo.get_project(user_id=user_id, project_id=project.id)
    assert proj_detail.completed_task_count == 2
    assert proj_detail.progress_percentage == 50.0

    # Complete all remaining tasks -> 100.0%
    await temp_prod_repo.update_task(user_id=user_id, task_id=t3.id, update=TaskUpdate(status=TaskStatus.completed))
    await temp_prod_repo.update_task(user_id=user_id, task_id=t4.id, update=TaskUpdate(status=TaskStatus.completed))
    proj_detail = await temp_prod_repo.get_project(user_id=user_id, project_id=project.id)
    assert proj_detail.completed_task_count == 4
    assert proj_detail.progress_percentage == 100.0


@pytest.mark.asyncio
async def test_cross_tenant_project_and_task_linking_prevention(temp_prod_repo):
    user_a = uuid4()
    user_b = uuid4()

    proj_a = await temp_prod_repo.create_project(
        user_id=user_a,
        project=ProjectCreate(name="User A Confidential Project"),
    )

    # User B attempts to attach a task to User A's project
    with pytest.raises(ValueError) as exc:
        await temp_prod_repo.create_task(
            user_id=user_b,
            task=TaskCreate(title="User B rogue task", project_id=proj_a.id),
        )
    assert "not found or access denied" in str(exc.value)

    # User B creates own task, then attempts to re-parent it to User A's project
    task_b = await temp_prod_repo.create_task(
        user_id=user_b,
        task=TaskCreate(title="User B task"),
    )
    with pytest.raises(ValueError) as exc:
        await temp_prod_repo.update_task(
            user_id=user_b,
            task_id=task_b.id,
            update=TaskUpdate(project_id=proj_a.id),
        )
    assert "not found or access denied" in str(exc.value)


@pytest.mark.asyncio
async def test_project_deletion_unlinks_tasks_by_default(temp_prod_repo):
    user_id = uuid4()
    proj = await temp_prod_repo.create_project(user_id=user_id, project=ProjectCreate(name="Temporary Project"))
    task = await temp_prod_repo.create_task(user_id=user_id, task=TaskCreate(title="Persistent Task", project_id=proj.id))

    # Delete project with delete_tasks=False (default safe behaviour)
    deleted = await temp_prod_repo.delete_project(user_id=user_id, project_id=proj.id, delete_tasks=False)
    assert deleted is True

    # Task remains intact, with project_id unlinked (None)
    check_task = await temp_prod_repo.get_task(user_id=user_id, task_id=task.id)
    assert check_task is not None
    assert check_task.project_id is None
    assert check_task.title == "Persistent Task"


# ============================================================================
# 3. Goals, Milestones, and Measurable Progress
# ============================================================================

@pytest.mark.asyncio
async def test_goal_measurable_progress_and_completion(temp_prod_repo):
    user_id = uuid4()

    # Goal with measurable target (e.g. Run 100 km, currently 25 km -> 25%)
    goal = await temp_prod_repo.create_goal(
        user_id=user_id,
        goal=GoalCreate(
            title="Run 100km this month",
            target_value=100.0,
            current_value=25.0,
            unit="km",
            status=GoalStatus.in_progress,
        ),
    )
    assert goal.progress_percentage == 25.0
    assert goal.completed_at is None

    # Update current value to 75 km -> 75%
    updated = await temp_prod_repo.update_goal(
        user_id=user_id,
        goal_id=goal.id,
        update=GoalUpdate(current_value=75.0),
    )
    assert updated.progress_percentage == 75.0

    # Mark achieved -> completed_at set, progress 100%
    achieved = await temp_prod_repo.update_goal(
        user_id=user_id,
        goal_id=goal.id,
        update=GoalUpdate(status=GoalStatus.achieved),
    )
    assert achieved.status == GoalStatus.achieved
    assert achieved.completed_at is not None


@pytest.mark.asyncio
async def test_goal_deletion_unlinks_projects_and_tasks(temp_prod_repo):
    user_id = uuid4()
    goal = await temp_prod_repo.create_goal(user_id=user_id, goal=GoalCreate(title="Master Machine Learning"))
    proj = await temp_prod_repo.create_project(user_id=user_id, project=ProjectCreate(name="Transformer Architecture Study", goal_id=goal.id))
    task = await temp_prod_repo.create_task(user_id=user_id, task=TaskCreate(title="Read Attention Is All You Need", goal_id=goal.id))

    # Delete goal
    deleted = await temp_prod_repo.delete_goal(user_id=user_id, goal_id=goal.id)
    assert deleted is True

    # Linked project and task have goal_id set to None
    check_proj = await temp_prod_repo.get_project(user_id=user_id, project_id=proj.id)
    assert check_proj.goal_id is None

    check_task = await temp_prod_repo.get_task(user_id=user_id, task_id=task.id)
    assert check_task.goal_id is None


@pytest.mark.asyncio
async def test_parent_task_deletion_preserves_subtasks(temp_prod_repo):
    """Verify FINDING-03 resolution:
    Deleting a parent task preserves subtasks by setting parent_task_id to NULL,
    preventing unintended data loss.
    """
    user_id = uuid4()
    parent = await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(title="Parent Mission Task", priority=TaskPriority.urgent),
    )
    sub1 = await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(title="Subtask 1", parent_task_id=parent.id),
    )
    sub2 = await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(title="Subtask 2", parent_task_id=parent.id),
    )

    # Subtasks initially linked
    assert sub1.parent_task_id == parent.id
    assert sub2.parent_task_id == parent.id

    # Delete parent task
    deleted = await temp_prod_repo.delete_task(user_id=user_id, task_id=parent.id)
    assert deleted is True

    # Parent is gone
    check_parent = await temp_prod_repo.get_task(user_id=user_id, task_id=parent.id)
    assert check_parent is None

    # Subtasks still exist and their parent_task_id is now None (promoted to independent tasks)
    check_sub1 = await temp_prod_repo.get_task(user_id=user_id, task_id=sub1.id)
    assert check_sub1 is not None
    assert check_sub1.parent_task_id is None
    assert check_sub1.user_id == user_id

    check_sub2 = await temp_prod_repo.get_task(user_id=user_id, task_id=sub2.id)
    assert check_sub2 is not None
    assert check_sub2.parent_task_id is None
    assert check_sub2.user_id == user_id


def test_project_color_validation():
    """Verify FINDING-08 resolution:
    Project color validates hexadecimal codes and rejects malformed values.
    """
    # Valid hex codes
    p1 = ProjectCreate(name="Project 1", color="#4872bd")
    assert p1.color == "#4872bd"

    p2 = ProjectCreate(name="Project 2", color="#10B981")
    assert p2.color == "#10b981"

    p3 = ProjectCreate(name="Project 3", color="#fff")
    assert p3.color == "#fff"

    p4 = ProjectCreate(name="Project 4", color="#12345678")
    assert p4.color == "#12345678"

    p5 = ProjectCreate(name="Project 5", color=None)
    assert p5.color is None

    # Invalid values raise ValueError
    with pytest.raises(ValueError):
        ProjectCreate(name="Invalid Color", color="red")

    with pytest.raises(ValueError):
        ProjectCreate(name="Invalid CSS Injection", color="javascript:alert(1)")

    with pytest.raises(ValueError):
        ProjectCreate(name="Invalid Length", color="#12")

    with pytest.raises(ValueError):
        ProjectCreate(name="Invalid Non-hex", color="#xyz123")

    # Update model validation
    u_valid = ProjectUpdate(color="#8b5cf6")
    assert u_valid.color == "#8b5cf6"

    with pytest.raises(ValueError):
        ProjectUpdate(color="invalid")


# ============================================================================
# 4. Productivity Dashboard Aggregation
# ============================================================================

@pytest.mark.asyncio
async def test_productivity_dashboard_metrics(temp_prod_repo):
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    # Empty state check
    empty_dash = await temp_prod_repo.get_dashboard(user_id=user_id)
    assert empty_dash.active_tasks_count == 0
    assert empty_dash.overdue_tasks_count == 0
    assert empty_dash.completed_tasks_count == 0
    assert empty_dash.active_projects_count == 0
    assert empty_dash.active_goals_count == 0

    # Seed data
    # 1 Overdue task
    await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(
            title="Overdue report",
            status=TaskStatus.todo,
            due_date=now - timedelta(days=1),
        ),
    )
    # 1 Upcoming active task
    await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(
            title="Upcoming presentation",
            status=TaskStatus.in_progress,
            due_date=now + timedelta(days=3),
        ),
    )
    # 1 Completed task
    await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(
            title="Finished notes",
            status=TaskStatus.completed,
        ),
    )
    # 1 Active project
    await temp_prod_repo.create_project(
        user_id=user_id,
        project=ProjectCreate(name="Active Project Beta", status=ProjectStatus.active),
    )
    # 1 Active goal
    await temp_prod_repo.create_goal(
        user_id=user_id,
        goal=GoalCreate(title="Active Goal Alpha", status=GoalStatus.in_progress),
    )

    dash = await temp_prod_repo.get_dashboard(user_id=user_id)
    assert dash.active_tasks_count == 2
    assert dash.overdue_tasks_count == 1
    assert dash.completed_tasks_count == 1
    assert dash.active_projects_count == 1
    assert dash.active_goals_count == 1
    assert len(dash.overdue_tasks) == 1
    assert dash.overdue_tasks[0].title == "Overdue report"
    assert len(dash.recently_completed_tasks) == 1
    assert dash.recently_completed_tasks[0].title == "Finished notes"


# ============================================================================
# 5. Controlled Conversational AI Productivity Context
# ============================================================================

@pytest.mark.asyncio
async def test_conversational_productivity_context_assembly(temp_prod_repo):
    user_id = uuid4()
    ctx_mgr = ProductivityContextManager(repository=temp_prod_repo)

    # Empty state: returns None (no noise injected)
    context_str, summary = await ctx_mgr.assemble_productivity_context(user_id=user_id)
    assert context_str is None
    assert summary.total_active_tasks == 0

    # Seed an overdue task and an active project
    now = datetime.now(timezone.utc)
    await temp_prod_repo.create_project(
        user_id=user_id,
        project=ProjectCreate(name="Mobile App Redesign", status=ProjectStatus.active),
    )
    await temp_prod_repo.create_task(
        user_id=user_id,
        task=TaskCreate(
            title="Wireframe Navigation Flow",
            priority=TaskPriority.urgent,
            status=TaskStatus.todo,
            due_date=now - timedelta(days=2),
        ),
    )

    context_str, summary = await ctx_mgr.assemble_productivity_context(user_id=user_id)
    assert context_str is not None
    assert "USER PRODUCTIVITY CONTEXT (READ-ONLY)" in context_str
    assert "POLICY: You are strictly read-only" in context_str
    assert "Wireframe Navigation Flow" in context_str
    assert "Mobile App Redesign" in context_str
    assert summary.total_active_tasks == 1
    assert summary.total_active_projects == 1


# ============================================================================
# 6. PostgreSQL 18 RLS Security and Migration 019 Verification
# ============================================================================

@pytest.fixture(scope="session")
def postgresql_server():
    return {"host": str(PG_SOCK_DIR), "port": PG_PORT}


@pytest.mark.asyncio
async def test_postgresql_migration_019_rls_and_cross_tenant_prevention(postgresql_server):
    """Verify on local PostgreSQL 18:
    1. Migration 019 applies cleanly on top of all 18 preceding migrations.
    2. RLS prevents User B from reading User A's tasks, projects, or goals.
    3. RLS prevents User B from attaching a task to User A's project (violating tasks_insert_own).
    4. RLS prevents User B from attaching a project to User A's goal (violating projects_insert_own).
    5. Anonymous callers are denied all operations.
    """
    db_name = f"auren_prod_test_{uuid4().hex[:10]}"
    admin_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="postgres")
    await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    await admin_conn.close()

    conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name)
    try:
        await conn.execute(MOCK_AUTH_SQL)
        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611*.sql")))
        assert len(migration_files) >= 20, f"Expected at least 20 migrations, got {len(migration_files)}"
        for mf in migration_files:
            sql = Path(mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        user_a = uuid4()
        user_b = uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, 'a@example.com'), ($2, 'b@example.com')", user_a, user_b)

        # 1. User A creates a goal and project
        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")
        await conn.execute("SET ROLE authenticated")
        goal_a_id = await conn.fetchval(
            """
            INSERT INTO public.goals (user_id, title, status)
            VALUES ($1, 'User A Strategic Goal', 'in_progress')
            RETURNING id;
            """,
            user_a,
        )
        assert goal_a_id is not None

        proj_a_id = await conn.fetchval(
            """
            INSERT INTO public.projects (user_id, name, status, goal_id)
            VALUES ($1, 'User A Project', 'active', $2)
            RETURNING id;
            """,
            user_a,
            goal_a_id,
        )
        assert proj_a_id is not None

        task_a_id = await conn.fetchval(
            """
            INSERT INTO public.tasks (user_id, title, status, project_id, goal_id)
            VALUES ($1, 'User A Task', 'todo', $2, $3)
            RETURNING id;
            """,
            user_a,
            proj_a_id,
            goal_a_id,
        )
        assert task_a_id is not None

        # 2. Switch to User B
        await conn.execute(f"SET request.jwt.claim.sub = '{user_b}'")

        # User B cannot read User A's records under authenticated role
        b_tasks = await conn.fetch("SELECT * FROM public.tasks WHERE id = $1", task_a_id)
        assert len(b_tasks) == 0

        b_projs = await conn.fetch("SELECT * FROM public.projects WHERE id = $1", proj_a_id)
        assert len(b_projs) == 0

        b_goals = await conn.fetch("SELECT * FROM public.goals WHERE id = $1", goal_a_id)
        assert len(b_goals) == 0

        # 3. User B attempts cross-tenant project linking to User A's goal -> RLS check fails
        with pytest.raises(asyncpg.PostgresError) as exc_p:
            await conn.execute(
                """
                INSERT INTO public.projects (user_id, name, status, goal_id)
                VALUES ($1, 'User B Malicious Project', 'active', $2);
                """,
                user_b,
                goal_a_id,
            )
        assert "row-level security policy" in str(exc_p.value).lower()

        # 4. User B attempts cross-tenant task linking to User A's project -> RLS check fails
        with pytest.raises(asyncpg.PostgresError) as exc_t:
            await conn.execute(
                """
                INSERT INTO public.tasks (user_id, title, status, project_id)
                VALUES ($1, 'User B Malicious Task', 'todo', $2);
                """,
                user_b,
                proj_a_id,
            )
        assert "row-level security policy" in str(exc_t.value).lower()

        # 5. Anonymous role is denied
        await conn.execute("RESET ROLE")
        await conn.execute("RESET request.jwt.claim.sub")
        await conn.execute("SET ROLE anon")
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError) as exc_anon:
                await conn.fetch("SELECT * FROM public.tasks")
            assert "permission denied" in str(exc_anon.value).lower()
        finally:
            await conn.execute("RESET ROLE")

        # 6. Verify Migration 020: Parent task deletion sets subtask parent_task_id to NULL (ON DELETE SET NULL)
        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")
        await conn.execute("SET ROLE authenticated")

        parent_t_id = await conn.fetchval(
            "INSERT INTO public.tasks (user_id, title, status) VALUES ($1, 'Postgres Parent Task', 'todo') RETURNING id;",
            user_a,
        )
        sub_t_id = await conn.fetchval(
            "INSERT INTO public.tasks (user_id, title, status, parent_task_id) VALUES ($1, 'Postgres Subtask', 'todo', $2) RETURNING id;",
            user_a,
            parent_t_id,
        )
        assert sub_t_id is not None

        # Delete parent task
        await conn.execute("DELETE FROM public.tasks WHERE id = $1 AND user_id = $2;", parent_t_id, user_a)

        # Subtask still exists and parent_task_id is now NULL
        sub_row = await conn.fetchrow("SELECT id, parent_task_id FROM public.tasks WHERE id = $1;", sub_t_id)
        assert sub_row is not None
        assert sub_row["parent_task_id"] is None

    finally:
        await conn.close()
        admin_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="postgres")
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await admin_conn.close()


@pytest.mark.asyncio
async def test_postgresql_migration_022_record_links_endpoint_ownership(postgresql_server):
    """Verify on local PostgreSQL 18:
    1. Migration 022 applies cleanly on top of all 21 preceding migrations.
    2. User A can link their own task to their own project.
    3. User B cannot link their task to User A's task (foreign target rejected by trigger).
    4. User B cannot link User A's task to their task (foreign source rejected by trigger).
    5. User B cannot spoof User A's user_id in record_links (rejected by trigger).
    6. Nonexistent UUIDs are rejected.
    """
    db_name = f"auren_rl_test_{uuid4().hex[:10]}"
    admin_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="postgres")
    await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    await admin_conn.close()

    conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database=db_name)
    try:
        await conn.execute(MOCK_AUTH_SQL)
        migration_files = sorted(glob.glob(str(MIGRATIONS_DIR / "202611*.sql")))
        assert len(migration_files) >= 22, f"Expected at least 22 migrations, got {len(migration_files)}"
        for mf in migration_files:
            sql = Path(mf).read_text(encoding="utf-8")
            await conn.execute(sql)

        user_a = uuid4()
        user_b = uuid4()
        await conn.execute("INSERT INTO auth.users (id, email) VALUES ($1, 'a@example.com'), ($2, 'b@example.com')", user_a, user_b)

        # 1. User A creates task and project
        await conn.execute(f"SET request.jwt.claim.sub = '{user_a}'")
        await conn.execute("SET ROLE authenticated")

        task_a_id = await conn.fetchval(
            "INSERT INTO public.tasks (user_id, title, status) VALUES ($1, 'Task A', 'todo') RETURNING id;",
            user_a,
        )
        proj_a_id = await conn.fetchval(
            "INSERT INTO public.projects (user_id, name, status) VALUES ($1, 'Project A', 'active') RETURNING id;",
            user_a,
        )
        assert task_a_id is not None
        assert proj_a_id is not None

        # User A creates valid record_link (task A -> project A) -> SUCCEEDS
        link_a_id = await conn.fetchval(
            """
            INSERT INTO public.record_links (user_id, source_type, source_id, target_type, target_id, relationship_type)
            VALUES ($1, 'task', $2, 'project', $3, 'related')
            RETURNING id;
            """,
            user_a,
            task_a_id,
            proj_a_id,
        )
        assert link_a_id is not None

        # 2. Switch to User B
        await conn.execute(f"SET request.jwt.claim.sub = '{user_b}'")
        task_b_id = await conn.fetchval(
            "INSERT INTO public.tasks (user_id, title, status) VALUES ($1, 'Task B', 'todo') RETURNING id;",
            user_b,
        )
        assert task_b_id is not None

        # 3. User B attempts cross-tenant target linking: User B task -> User A project -> REJECTED
        with pytest.raises(asyncpg.PostgresError) as exc_target:
            await conn.execute(
                """
                INSERT INTO public.record_links (user_id, source_type, source_id, target_type, target_id, relationship_type)
                VALUES ($1, 'task', $2, 'project', $3, 'related');
                """,
                user_b,
                task_b_id,
                proj_a_id,
            )
        assert "not found or not owned by user" in str(exc_target.value)

        # 4. User B attempts cross-tenant source linking: User A task -> User B task -> REJECTED
        with pytest.raises(asyncpg.PostgresError) as exc_source:
            await conn.execute(
                """
                INSERT INTO public.record_links (user_id, source_type, source_id, target_type, target_id, relationship_type)
                VALUES ($1, 'task', $2, 'task', $3, 'related');
                """,
                user_b,
                task_a_id,
                task_b_id,
            )
        assert "not found or not owned by user" in str(exc_source.value)

        # 5. User B attempts to spoof User A's user_id -> REJECTED
        with pytest.raises(asyncpg.PostgresError) as exc_spoof:
            await conn.execute(
                """
                INSERT INTO public.record_links (user_id, source_type, source_id, target_type, target_id, relationship_type)
                VALUES ($1, 'task', $2, 'project', $3, 'related');
                """,
                user_a,  # Spoofed user_id
                task_a_id,
                proj_a_id,
            )
        assert "must equal auth.uid()" in str(exc_spoof.value) or "row-level security" in str(exc_spoof.value).lower()

        # 6. Nonexistent UUID -> REJECTED
        fake_id = uuid4()
        with pytest.raises(asyncpg.PostgresError) as exc_fake:
            await conn.execute(
                """
                INSERT INTO public.record_links (user_id, source_type, source_id, target_type, target_id, relationship_type)
                VALUES ($1, 'task', $2, 'task', $3, 'related');
                """,
                user_b,
                task_b_id,
                fake_id,
            )
        assert "not found or not owned by user" in str(exc_fake.value)

    finally:
        await conn.close()
        admin_conn = await asyncpg.connect(host=postgresql_server["host"], port=postgresql_server["port"], database="postgres")
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await admin_conn.close()
