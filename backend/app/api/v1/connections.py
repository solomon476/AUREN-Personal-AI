"""API endpoints for Trusted Connections and Voluntary Location Sharing."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.models.connections import (
    ConnectionAcceptRequest,
    ConnectionInviteRequest,
    ConnectionListResponse,
    ConnectionResponse,
    LocationSharingToggleRequest,
    LocationUpdateRequest,
)
from app.models.user import AuthenticatedUser
from app.services.connections.repository import get_connection_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connections", tags=["Trusted Connections & Location Sharing"])


@router.get("", response_model=ConnectionListResponse, summary="List Trusted Connections")
async def list_connections(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ConnectionListResponse:
    """List mutual active connections and incoming/outgoing pending invites."""
    repo = get_connection_repository(user_token=current_user.token)
    items = await repo.list_connections(user_id=current_user.id)

    active = []
    pending = []

    for item in items:
        resp = ConnectionResponse(
            id=item.id,
            user_id=item.user_id,
            connected_user_id=item.connected_user_id,
            invite_code=item.invite_code,
            display_name=item.display_name,
            avatar_initials=item.avatar_initials,
            status=item.status,
            location_sharing_active=item.location_sharing_active,
            location_sharing_expires_at=item.location_sharing_expires_at,
            last_latitude=item.last_latitude,
            last_longitude=item.last_longitude,
            last_location_updated_at=item.last_location_updated_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        if item.status == "accepted":
            active.append(resp)
        elif item.status == "pending":
            pending.append(resp)

    return ConnectionListResponse(
        active_connections=active,
        pending_requests=pending,
        total=len(items),
    )


@router.post("/invite", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED, summary="Create Connection Invite")
async def create_invite(
    payload: ConnectionInviteRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ConnectionResponse:
    """Generate a secure invitation code and link to share with a trusted person."""
    repo = get_connection_repository(user_token=current_user.token)
    item = await repo.create_invite(user_id=current_user.id, display_name=payload.display_name)
    return ConnectionResponse(
        id=item.id,
        user_id=item.user_id,
        connected_user_id=item.connected_user_id,
        invite_code=item.invite_code,
        display_name=item.display_name,
        avatar_initials=item.avatar_initials,
        status=item.status,
        location_sharing_active=item.location_sharing_active,
        location_sharing_expires_at=item.location_sharing_expires_at,
        last_latitude=item.last_latitude,
        last_longitude=item.last_longitude,
        last_location_updated_at=item.last_location_updated_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/accept", response_model=ConnectionResponse, summary="Accept Connection Invite")
async def accept_invite(
    payload: ConnectionAcceptRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ConnectionResponse:
    """Establish a mutual connection by accepting a valid invitation code."""
    repo = get_connection_repository(user_token=current_user.token)
    try:
        item = await repo.accept_invite(user_id=current_user.id, invite_code=payload.invite_code)
        return ConnectionResponse(
            id=item.id,
            user_id=item.user_id,
            connected_user_id=item.connected_user_id,
            invite_code=item.invite_code,
            display_name=item.display_name,
            avatar_initials=item.avatar_initials,
            status=item.status,
            location_sharing_active=item.location_sharing_active,
            location_sharing_expires_at=item.location_sharing_expires_at,
            last_latitude=item.last_latitude,
            last_longitude=item.last_longitude,
            last_location_updated_at=item.last_location_updated_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/{connection_id}/decline", status_code=status.HTTP_200_OK, summary="Decline Connection Invite")
async def decline_invite(
    connection_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Decline a pending invitation."""
    repo = get_connection_repository(user_token=current_user.token)
    declined = await repo.decline_invite(user_id=current_user.id, connection_id=connection_id)
    if not declined:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
    return {"status": "declined"}


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke Connection")
async def revoke_connection(
    connection_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Revoke and permanently remove an active connection."""
    repo = get_connection_repository(user_token=current_user.token)
    revoked = await repo.revoke_connection(user_id=current_user.id, connection_id=connection_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found or access denied.")


@router.post("/location-sharing", status_code=status.HTTP_200_OK, summary="Toggle Voluntary Location Sharing")
async def toggle_location_sharing(
    payload: LocationSharingToggleRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Enable, pause, or disable voluntary temporary location sharing."""
    repo = get_connection_repository(user_token=current_user.token)
    await repo.toggle_location_sharing(user_id=current_user.id, payload=payload)
    return {
        "location_sharing_active": payload.enabled,
        "duration_minutes": payload.duration_minutes if payload.enabled else 0,
    }


@router.post("/location", status_code=status.HTTP_200_OK, summary="Update Current Location")
async def update_location(
    payload: LocationUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Submit updated GPS fix if location sharing is enabled."""
    repo = get_connection_repository(user_token=current_user.token)
    await repo.update_location(user_id=current_user.id, payload=payload)
    return {"status": "updated"}

