"""API Router for Long-Term Memory Explorer, Epistemic Verification, and Lineage Management."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import (
    DatabaseAuthError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseOperationError,
)
from app.core.security import get_current_user
from app.models.memory import (
    MemoryCorrectionRequest,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    VALID_CATEGORIES,
    VALID_CONFIRMATION_STATUSES,
    VALID_LIFECYCLE_STATUSES,
    VALID_MEMORY_TYPES,
)
from app.models.user import AuthenticatedUser
from app.services.memory.base_repository import BaseMemoryRepository
from app.services.memory.repository import get_memory_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memories", tags=["Memory Management & Epistemic Verification"])


def get_user_memory_repository(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BaseMemoryRepository:
    """Dependency injecting memory repository configured for authenticated user."""
    return get_memory_repository(user_token=current_user.token)


def _to_response(mem) -> MemoryResponse:
    """Helper mapping domain MemoryModel to API MemoryResponse."""
    return MemoryResponse(
        id=mem.id,
        content=mem.content,
        memory_type=mem.memory_type,
        category=mem.category,
        importance=mem.importance,
        confidence=mem.confidence,
        confirmation_status=mem.confirmation_status,
        lifecycle_status=mem.lifecycle_status,
        origin=mem.origin,
        source_message_id=mem.source_message_id,
        source_conversation_id=mem.source_conversation_id,
        superseded_by_id=mem.superseded_by_id,
        previous_version_id=mem.previous_version_id,
        root_memory_id=mem.root_memory_id,
        access_count=mem.access_count,
        last_accessed_at=mem.last_accessed_at,
        last_confirmed_at=mem.last_confirmed_at,
        created_at=mem.created_at,
        updated_at=mem.updated_at,
        metadata=mem.metadata,
    )


@router.get(
    "",
    response_model=MemoryListResponse,
    summary="List and Search Memories",
    description="Query user-scoped memories with server-side pagination, text search, and epistemic filters.",
)
async def list_memories(
    query: Optional[str] = Query(None, max_length=200, description="Substring search against memory content"),
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
    category: Optional[str] = Query(None, description="Filter by category"),
    confirmation_status: Optional[str] = Query(None, description="Filter by confirmation status"),
    lifecycle_status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryListResponse:
    """Return paginated memories belonging to the caller, strictly isolating journal entries."""
    if memory_type and memory_type not in VALID_MEMORY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory_type '{memory_type}'. Must be one of {sorted(VALID_MEMORY_TYPES)}",
        )
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category '{category}'. Must be one of {sorted(VALID_CATEGORIES)}",
        )
    if confirmation_status and confirmation_status not in VALID_CONFIRMATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid confirmation_status '{confirmation_status}'. Must be one of {sorted(VALID_CONFIRMATION_STATUSES)}",
        )
    if lifecycle_status and lifecycle_status not in VALID_LIFECYCLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid lifecycle_status '{lifecycle_status}'. Must be one of {sorted(VALID_LIFECYCLE_STATUSES)}",
        )

    try:
        items, total = await repo.list_memories(
            user_id=current_user.id,
            query=query,
            memory_type=memory_type,
            category=category,
            confirmation_status=confirmation_status,
            lifecycle_status=lifecycle_status,
            page=page,
            page_size=page_size,
        )
        has_more = (page * page_size) < total
        return MemoryListResponse(
            items=[_to_response(m) for m in items],
            total=total,
            page=page,
            page_size=page_size,
            has_more=has_more,
        )
    except (DatabaseAuthError, DatabaseConnectionError, DatabaseOperationError) as exc:
        logger.error("Database error in list_memories: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve memories.")


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Confirmed Memory",
    description="Manually record a user-asserted fact or preference in confirmed, active state.",
)
async def create_memory(
    payload: MemoryCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Record an explicit memory asserted by the user."""
    try:
        mem = await repo.create_memory(
            user_id=current_user.id,
            content=payload.content,
            memory_type=payload.memory_type,
            category=payload.category,
            importance=payload.importance,
            origin="user_direct_input",
        )
        return _to_response(mem)
    except DatabaseError as exc:
        logger.error("Database error creating memory: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create memory.")


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Get Memory Details",
    description="Retrieve comprehensive epistemic status, provenance, and lineage for a specific memory.",
)
async def get_memory(
    memory_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Retrieve an individual memory, strictly enforcing ownership."""
    try:
        mem = await repo.get_memory(current_user.id, memory_id)
        if not mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found or access denied.",
            )
        return _to_response(mem)
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error getting memory %s: %s", memory_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve memory.")


@router.post(
    "/{memory_id}/confirm",
    response_model=MemoryResponse,
    summary="Confirm Unconfirmed Memory",
    description="Explicitly verify and confirm an inferred memory item.",
)
async def confirm_memory(
    memory_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Confirm a memory candidate."""
    try:
        mem = await repo.confirm_memory(current_user.id, memory_id)
        if not mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found or access denied.",
            )
        return _to_response(mem)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {val_err}",
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error confirming memory %s: %s", memory_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to confirm memory.")


@router.post(
    "/{memory_id}/reject",
    response_model=MemoryResponse,
    summary="Reject Inaccurate Inference",
    description="Reject an inferred memory candidate. Rejection is a terminal epistemic state.",
)
async def reject_memory(
    memory_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Reject a memory candidate."""
    try:
        mem = await repo.reject_memory(current_user.id, memory_id)
        if not mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found or access denied.",
            )
        return _to_response(mem)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {val_err}",
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error rejecting memory %s: %s", memory_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reject memory.")


@router.post(
    "/{memory_id}/correct",
    response_model=MemoryResponse,
    summary="Correct Memory (Lineage-Preserving)",
    description="Atomically supersede an inaccurate memory and register its verified replacement.",
)
async def correct_memory(
    memory_id: UUID,
    payload: MemoryCorrectionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Correct a memory, preserving lineage."""
    if payload.memory_type and payload.memory_type not in VALID_MEMORY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory_type '{payload.memory_type}'. Must be one of {sorted(VALID_MEMORY_TYPES)}",
        )
    if payload.category and payload.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category '{payload.category}'. Must be one of {sorted(VALID_CATEGORIES)}",
        )

    try:
        new_mem = await repo.correct_memory(
            user_id=current_user.id,
            memory_id=memory_id,
            content=payload.content,
            memory_type=payload.memory_type,
            category=payload.category,
            importance=payload.importance,
        )
        if not new_mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found or access denied.",
            )
        return _to_response(new_mem)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {val_err}",
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error correcting memory %s: %s", memory_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to correct memory.")


@router.post(
    "/{memory_id}/archive",
    response_model=MemoryResponse,
    summary="Archive Memory",
    description="Transition an active memory to archived status, excluding it from ordinary retrieval.",
)
async def archive_memory(
    memory_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Archive an active memory."""
    try:
        mem = await repo.archive_memory(current_user.id, memory_id)
        if not mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found or access denied.",
            )
        return _to_response(mem)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {val_err}",
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error archiving memory %s: %s", memory_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to archive memory.")


@router.post(
    "/{memory_id}/restore",
    response_model=MemoryResponse,
    summary="Restore Archived or Expired Memory",
    description="Restore an archived or expired memory back to active status.",
)
async def restore_memory(
    memory_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Restore an archived or expired memory."""
    try:
        mem = await repo.restore_memory(current_user.id, memory_id)
        if not mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found or access denied.",
            )
        return _to_response(mem)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {val_err}",
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error restoring memory %s: %s", memory_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to restore memory.")


@router.post(
    "/{memory_id}/outdated",
    response_model=MemoryResponse,
    summary="Mark Memory as Outdated",
    description="Transition an active memory to expired status.",
)
async def outdate_memory(
    memory_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: BaseMemoryRepository = Depends(get_user_memory_repository),
) -> MemoryResponse:
    """Mark a memory as expired/outdated."""
    try:
        mem = await repo.outdate_memory(current_user.id, memory_id)
        if not mem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found or access denied.",
            )
        return _to_response(mem)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {val_err}",
        )
    except HTTPException:
        raise
    except DatabaseError as exc:
        logger.error("Database error marking memory outdated %s: %s", memory_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to mark memory outdated.")

