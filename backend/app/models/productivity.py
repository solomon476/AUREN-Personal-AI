"""Pydantic data models and schemas for AUREN Phase 3C.4 Productivity Core:
Tasks, Projects, Goals, Relationships, and Dashboard Metrics.
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Status and Priority Enums
# ============================================================================

class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    completed = "completed"
    cancelled = "cancelled"


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class ProjectStatus(str, Enum):
    planning = "planning"
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    cancelled = "cancelled"
    archived = "archived"


class GoalStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    achieved = "achieved"
    paused = "paused"
    abandoned = "abandoned"
    # Legacy alias support
    completed = "completed"


# ============================================================================
# Task Models
# ============================================================================

class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.todo
    priority: TaskPriority = TaskPriority.medium
    project_id: Optional[UUID] = None
    goal_id: Optional[UUID] = None
    parent_task_id: Optional[UUID] = None
    due_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Task title cannot be empty or whitespace only")
        return s


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    project_id: Optional[UUID] = None
    goal_id: Optional[UUID] = None
    parent_task_id: Optional[UUID] = None
    due_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    tags: Optional[List[str]] = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Task title cannot be empty or whitespace only")
            return s
        return v


class TaskModel(TaskBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    project_name: Optional[str] = None
    goal_title: Optional[str] = None
    subtask_count: int = 0


class TaskListResponse(BaseModel):
    items: List[TaskModel]
    total: int
    page: int
    page_size: int


# ============================================================================
# Project Models
# ============================================================================

class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = "#4872bd"
    status: ProjectStatus = ProjectStatus.active
    start_date: Optional[date] = None
    target_date: Optional[date] = None
    goal_id: Optional[UUID] = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Project name cannot be empty or whitespace only")
        return s


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = None
    status: Optional[ProjectStatus] = None
    start_date: Optional[date] = None
    target_date: Optional[date] = None
    goal_id: Optional[UUID] = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Project name cannot be empty or whitespace only")
            return s
        return v


class ProjectModel(ProjectBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    goal_title: Optional[str] = None
    task_count: int = 0
    completed_task_count: int = 0
    progress_percentage: float = 0.0


class ProjectDetailModel(ProjectModel):
    tasks: List[TaskModel] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    items: List[ProjectModel]
    total: int
    page: int
    page_size: int


# ============================================================================
# Goal Models
# ============================================================================

class GoalBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: GoalStatus = GoalStatus.in_progress
    target_date: Optional[date] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = 0.0
    unit: Optional[str] = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Goal title cannot be empty or whitespace only")
        return s


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[GoalStatus] = None
    target_date: Optional[date] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    unit: Optional[str] = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Goal title cannot be empty or whitespace only")
            return s
        return v


class GoalModel(GoalBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    progress_percentage: Optional[float] = None
    project_count: int = 0
    task_count: int = 0


class GoalDetailModel(GoalModel):
    projects: List[ProjectModel] = Field(default_factory=list)
    tasks: List[TaskModel] = Field(default_factory=list)


class GoalListResponse(BaseModel):
    items: List[GoalModel]
    total: int
    page: int
    page_size: int


# ============================================================================
# Productivity Dashboard and Overview Models
# ============================================================================

class ProductivityDashboardResponse(BaseModel):
    active_tasks_count: int
    overdue_tasks_count: int
    completed_tasks_count: int
    active_projects_count: int
    active_goals_count: int
    upcoming_tasks: List[TaskModel] = Field(default_factory=list)
    overdue_tasks: List[TaskModel] = Field(default_factory=list)
    active_projects: List[ProjectModel] = Field(default_factory=list)
    active_goals: List[GoalModel] = Field(default_factory=list)
    recently_completed_tasks: List[TaskModel] = Field(default_factory=list)


# ============================================================================
# AI Context Summary Model
# ============================================================================

class ProductivityContextSummary(BaseModel):
    active_projects_summary: List[str] = Field(default_factory=list)
    pending_tasks_summary: List[str] = Field(default_factory=list)
    overdue_tasks_summary: List[str] = Field(default_factory=list)
    active_goals_summary: List[str] = Field(default_factory=list)
    total_active_tasks: int = 0
    total_active_projects: int = 0
    total_active_goals: int = 0

