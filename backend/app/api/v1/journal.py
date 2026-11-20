"""Private Journal API endpoints for AUREN.

Strict privacy invariants:
- Endpoints require authenticated callers (no anonymous access).
- Tenant isolation is strictly enforced by user.id.
- Journal entries are NEVER exposed to unconsented memory pipelines or assistant retrieval.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.models.journal import (
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    JournalEntryUpdate,
)
from app.models.user import AuthenticatedUser
from app.services.journal.repository import get_journal_repository

router = APIRouter(prefix="/journal", tags=["Journal"])


@router.get(
    "",
    response_model=JournalEntryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Journal Entries",
    description="Retrieve chronological private journal entries belonging to the authenticated user.",
)
async def list_journal_entries(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    start_date: Optional[date] = Query(default=None, description="Filter entries on or after this date"),
    end_date: Optional[date] = Query(default=None, description="Filter entries on or before this date"),
    mood: Optional[str] = Query(default=None, description="Filter by recorded mood"),
    query: Optional[str] = Query(default=None, description="Search keyword in title or content"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JournalEntryListResponse:
    repo = get_journal_repository(user_token=current_user.token)
    items, total = await repo.list_entries(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        mood=mood,
        query=query,
    )
    has_more = (page * page_size) < total
    return JournalEntryListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.post(
    "",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Journal Entry",
    description="Create a new private, distraction-free journal entry for the authenticated user.",
)
async def create_journal_entry(
    payload: JournalEntryCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JournalEntryResponse:
    repo = get_journal_repository(user_token=current_user.token)
    return await repo.create_entry(user_id=current_user.id, payload=payload)


@router.get(
    "/{entry_id}",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Journal Entry",
    description="Retrieve a single private journal entry by UUID ensuring strict user ownership.",
)
async def get_journal_entry(
    entry_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JournalEntryResponse:
    repo = get_journal_repository(user_token=current_user.token)
    entry = await repo.get_entry(user_id=current_user.id, entry_id=entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry {entry_id} not found.",
        )
    return entry


@router.put(
    "/{entry_id}",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Journal Entry",
    description="Update an existing private journal entry ensuring strict user ownership.",
)
@router.patch(
    "/{entry_id}",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_200_OK,
    summary="Patch Journal Entry",
    description="Partially update an existing private journal entry ensuring strict user ownership.",
)
async def update_journal_entry(
    entry_id: UUID,
    payload: JournalEntryUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JournalEntryResponse:
    repo = get_journal_repository(user_token=current_user.token)
    updated = await repo.update_entry(user_id=current_user.id, entry_id=entry_id, payload=payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry {entry_id} not found.",
        )
    return updated


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Journal Entry",
    description="Permanently delete a private journal entry ensuring strict user ownership.",
)
async def delete_journal_entry(
    entry_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    repo = get_journal_repository(user_token=current_user.token)
    deleted = await repo.delete_entry(user_id=current_user.id, entry_id=entry_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry {entry_id} not found.",
        )
