"""API endpoints for GPS Journeys and Offline Sync."""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.models.journeys import (
    JourneyCreateRequest,
    JourneyListResponse,
    JourneyResponse,
    JourneySyncBatchRequest,
)
from app.models.user import AuthenticatedUser
from app.services.journeys.repository import get_journey_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journeys", tags=["GPS Journeys & Field Tracking"])


@router.get("", response_model=JourneyListResponse, summary="List GPS Journeys")
async def list_journeys(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JourneyListResponse:
    """Retrieve recorded journey history for the authenticated user."""
    repo = get_journey_repository(user_token=current_user.token)
    items, total = await repo.list_journeys(user_id=current_user.id, limit=limit, offset=offset)
    return JourneyListResponse(
        items=[
            JourneyResponse(
                id=item.id,
                title=item.title,
                status=item.status,
                distance_meters=item.distance_meters,
                duration_seconds=item.duration_seconds,
                avg_speed_kmh=item.avg_speed_kmh,
                is_offline_recorded=item.is_offline_recorded,
                is_team_assignment=item.is_team_assignment,
                assignment_site=item.assignment_site,
                assignment_purpose=item.assignment_purpose,
                assignment_notes=item.assignment_notes,
                check_in_time=item.check_in_time,
                check_in_coords=item.check_in_coords,
                points=item.points,
                idempotency_key=item.idempotency_key,
                created_at=item.created_at,
                completed_at=item.completed_at,
            )
            for item in items
        ],
        total=total,
    )


@router.post("", response_model=JourneyResponse, status_code=status.HTTP_201_CREATED, summary="Create or Sync Journey")
async def create_or_sync_journey(
    payload: JourneyCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JourneyResponse:
    """Save an active, finished, or offline-recorded journey with idempotency protection."""
    repo = get_journey_repository(user_token=current_user.token)
    item = await repo.create_or_sync_journey(user_id=current_user.id, payload=payload)
    return JourneyResponse(
        id=item.id,
        title=item.title,
        status=item.status,
        distance_meters=item.distance_meters,
        duration_seconds=item.duration_seconds,
        avg_speed_kmh=item.avg_speed_kmh,
        is_offline_recorded=item.is_offline_recorded,
        is_team_assignment=item.is_team_assignment,
        assignment_site=item.assignment_site,
        assignment_purpose=item.assignment_purpose,
        assignment_notes=item.assignment_notes,
        check_in_time=item.check_in_time,
        check_in_coords=item.check_in_coords,
        points=item.points,
        idempotency_key=item.idempotency_key,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


@router.post("/sync-batch", response_model=List[JourneyResponse], summary="Batch Sync Offline Journeys")
async def sync_offline_journeys_batch(
    payload: JourneySyncBatchRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[JourneyResponse]:
    """Synchronize multiple journeys recorded while device was disconnected."""
    repo = get_journey_repository(user_token=current_user.token)
    results = []
    for item_req in payload.journeys:
        try:
            item = await repo.create_or_sync_journey(user_id=current_user.id, payload=item_req)
            results.append(
                JourneyResponse(
                    id=item.id,
                    title=item.title,
                    status=item.status,
                    distance_meters=item.distance_meters,
                    duration_seconds=item.duration_seconds,
                    avg_speed_kmh=item.avg_speed_kmh,
                    is_offline_recorded=item.is_offline_recorded,
                    is_team_assignment=item.is_team_assignment,
                    assignment_site=item.assignment_site,
                    assignment_purpose=item.assignment_purpose,
                    assignment_notes=item.assignment_notes,
                    check_in_time=item.check_in_time,
                    check_in_coords=item.check_in_coords,
                    points=item.points,
                    idempotency_key=item.idempotency_key,
                    created_at=item.created_at,
                    completed_at=item.completed_at,
                )
            )
        except Exception as exc:
            logger.warning("Error syncing journey in batch: %s", exc)
    return results


@router.get("/{journey_id}", response_model=JourneyResponse, summary="Get Journey Details")
async def get_journey(
    journey_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JourneyResponse:
    """Retrieve full journey telemetry and GPS point list."""
    repo = get_journey_repository(user_token=current_user.token)
    item = await repo.get_journey_by_id(user_id=current_user.id, journey_id=journey_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found.")

    return JourneyResponse(
        id=item.id,
        title=item.title,
        status=item.status,
        distance_meters=item.distance_meters,
        duration_seconds=item.duration_seconds,
        avg_speed_kmh=item.avg_speed_kmh,
        is_offline_recorded=item.is_offline_recorded,
        is_team_assignment=item.is_team_assignment,
        assignment_site=item.assignment_site,
        assignment_purpose=item.assignment_purpose,
        assignment_notes=item.assignment_notes,
        check_in_time=item.check_in_time,
        check_in_coords=item.check_in_coords,
        points=item.points,
        idempotency_key=item.idempotency_key,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


@router.delete("/{journey_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Journey")
async def delete_journey(
    journey_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a user-owned journey record."""
    repo = get_journey_repository(user_token=current_user.token)
    deleted = await repo.delete_journey(user_id=current_user.id, journey_id=journey_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found or access denied.")

