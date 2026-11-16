"""API endpoints for Projects Management in AUREN Phase 3C.4 Productivity Core."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import DatabaseAuthError, DatabaseConnectionError, DatabaseError
from app.core.security import get_current_user
from app.models.productivity import (
    ProjectCreate,
    ProjectDetailModel,
    ProjectListResponse,
    ProjectModel,
    ProjectStatus,
    ProjectUpdate,
)
from app.models.user import AuthenticatedUser
from app.services.productivity.base_repository import BaseProductivityRepository
from app.services.productivity.repository import get_productivity_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


def get_user_productivity_repo(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseProductivityRepository:
    return get_productivity_repository(user_token=current_user.token)


@router.post("", response_model=ProjectModel, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: ProjectCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ProjectModel:
    """Create a new project owned by the authenticated user."""
    try:
        return await repo.create_project(user_id=current_user.id, project=project_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error creating project for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create project.")


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status: Optional[str] = Query(None, description="Filter by status (planning, active, on_hold, completed, cancelled, archived)"),
    goal_id: Optional[UUID] = Query(None, description="Filter by associated goal ID"),
    query: Optional[str] = Query(None, description="Search query matching project name or description"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ProjectListResponse:
    """List projects owned by authenticated user with derived progress metrics and task counts."""
    try:
        items, total = await repo.list_projects(
            user_id=current_user.id,
            status=status,
            goal_id=goal_id,
            query=query,
            page=page,
            page_size=page_size,
        )
        return ProjectListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except DatabaseError as exc:
        logger.error("Database error listing projects for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list projects.")


@router.get("/{project_id}", response_model=ProjectDetailModel)
async def get_project(
    project_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ProjectDetailModel:
    """Retrieve a single project with its associated tasks and progress."""
    try:
        project = await repo.get_project(user_id=current_user.id, project_id=project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        return project
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error getting project %s: %s", project_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve project.")


@router.patch("/{project_id}", response_model=ProjectModel)
async def update_project(
    project_id: UUID,
    update_in: ProjectUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ProjectModel:
    """Update a project owned by the authenticated user."""
    try:
        project = await repo.update_project(user_id=current_user.id, project_id=project_id, update=update_in)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        return project
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error updating project %s: %s", project_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update project.")


@router.post("/{project_id}/status", response_model=ProjectModel)
async def change_project_status(
    project_id: UUID,
    new_status: ProjectStatus = Query(..., description="Target project status"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
) -> ProjectModel:
    """Change the lifecycle status of a project."""
    try:
        project = await repo.update_project(
            user_id=current_user.id,
            project_id=project_id,
            update=ProjectUpdate(status=new_status),
        )
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        return project
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DatabaseError as exc:
        logger.error("Database error changing status for project %s: %s", project_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update project status.")


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    delete_tasks: bool = Query(False, description="Whether to delete associated tasks or unlink them (SET NULL)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseProductivityRepository = Depends(get_user_productivity_repo),
):
    """Delete a project owned by the user. By default, unlinks tasks rather than destroying them."""
    try:
        deleted = await repo.delete_project(user_id=current_user.id, project_id=project_id, delete_tasks=delete_tasks)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error deleting project %s: %s", project_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete project.")

