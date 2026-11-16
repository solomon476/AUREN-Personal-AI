"""Abstract Base Repository Interface for AUREN Phase 3C.4 Productivity Core."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from uuid import UUID

from app.models.productivity import (
    GoalCreate,
    GoalDetailModel,
    GoalModel,
    GoalUpdate,
    ProductivityContextSummary,
    ProductivityDashboardResponse,
    ProjectCreate,
    ProjectDetailModel,
    ProjectModel,
    ProjectUpdate,
    TaskCreate,
    TaskModel,
    TaskUpdate,
)


class BaseProductivityRepository(ABC):
    """Abstract interface for Tasks, Projects, Goals, and Dashboard persistence."""

    # ------------------------------------------------------------------------
    # Task Operations
    # ------------------------------------------------------------------------

    @abstractmethod
    async def create_task(self, user_id: UUID, task: TaskCreate) -> TaskModel:
        """Create a new task under the authenticated user's ownership."""
        pass

    @abstractmethod
    async def get_task(self, user_id: UUID, task_id: UUID) -> Optional[TaskModel]:
        """Retrieve a task by ID ensuring ownership."""
        pass

    @abstractmethod
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
        """List tasks with filtering and pagination."""
        pass

    @abstractmethod
    async def update_task(
        self,
        user_id: UUID,
        task_id: UUID,
        update: TaskUpdate,
    ) -> Optional[TaskModel]:
        """Update an existing task ensuring ownership and relationship validation."""
        pass

    @abstractmethod
    async def delete_task(self, user_id: UUID, task_id: UUID) -> bool:
        """Delete a task owned by user."""
        pass

    # ------------------------------------------------------------------------
    # Project Operations
    # ------------------------------------------------------------------------

    @abstractmethod
    async def create_project(self, user_id: UUID, project: ProjectCreate) -> ProjectModel:
        """Create a new project under the authenticated user's ownership."""
        pass

    @abstractmethod
    async def get_project(self, user_id: UUID, project_id: UUID) -> Optional[ProjectDetailModel]:
        """Retrieve project with associated tasks and derived progress."""
        pass

    @abstractmethod
    async def list_projects(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        goal_id: Optional[UUID] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ProjectModel], int]:
        """List projects with derived progress and task counts."""
        pass

    @abstractmethod
    async def update_project(
        self,
        user_id: UUID,
        project_id: UUID,
        update: ProjectUpdate,
    ) -> Optional[ProjectModel]:
        """Update a project ensuring ownership."""
        pass

    @abstractmethod
    async def delete_project(
        self,
        user_id: UUID,
        project_id: UUID,
        delete_tasks: bool = False,
    ) -> bool:
        """Delete a project. If delete_tasks is False, associated tasks have project_id set to NULL."""
        pass

    # ------------------------------------------------------------------------
    # Goal Operations
    # ------------------------------------------------------------------------

    @abstractmethod
    async def create_goal(self, user_id: UUID, goal: GoalCreate) -> GoalModel:
        """Create a new goal under user ownership."""
        pass

    @abstractmethod
    async def get_goal(self, user_id: UUID, goal_id: UUID) -> Optional[GoalDetailModel]:
        """Retrieve goal with associated projects and tasks."""
        pass

    @abstractmethod
    async def list_goals(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[GoalModel], int]:
        """List goals with calculated progress percentages."""
        pass

    @abstractmethod
    async def update_goal(
        self,
        user_id: UUID,
        goal_id: UUID,
        update: GoalUpdate,
    ) -> Optional[GoalModel]:
        """Update goal ensuring ownership."""
        pass

    @abstractmethod
    async def delete_goal(self, user_id: UUID, goal_id: UUID) -> bool:
        """Delete goal. Linked projects and tasks have goal_id set to NULL."""
        pass

    # ------------------------------------------------------------------------
    # Productivity Dashboard and Context
    # ------------------------------------------------------------------------

    @abstractmethod
    async def get_dashboard(self, user_id: UUID) -> ProductivityDashboardResponse:
        """Compute aggregated productivity metrics from persisted records."""
        pass

    @abstractmethod
    async def get_productivity_context(
        self,
        user_id: UUID,
        max_items: int = 10,
    ) -> ProductivityContextSummary:
        """Assemble bounded read-only productivity context for conversational AI."""
        pass

