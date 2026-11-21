"""Data models and API schemas for Trusted Connections and Voluntary Location Sharing."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class ConnectionModel(BaseModel):
    """Persisted Trusted Connection entity."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    connected_user_id: Optional[UUID] = None
    invite_code: str
    display_name: str
    avatar_initials: str = "TC"
    status: str = Field(default="pending", description="'pending', 'accepted', 'declined', 'revoked'")
    location_sharing_active: bool = False
    location_sharing_expires_at: Optional[datetime] = None
    last_latitude: Optional[float] = None
    last_longitude: Optional[float] = None
    last_location_updated_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConnectionInviteRequest(BaseModel):
    """Request payload to create a new invitation code / link."""

    display_name: str = Field(..., min_length=1, max_length=100, description="Name or nickname for the intended connection")


class ConnectionAcceptRequest(BaseModel):
    """Request payload to accept an invitation code."""

    invite_code: str = Field(..., min_length=4, max_length=64, description="Invitation code received from connection")


class LocationSharingToggleRequest(BaseModel):
    """Request payload to enable, pause, or disable voluntary location sharing."""

    enabled: bool = Field(..., description="Whether location sharing is actively enabled")
    duration_minutes: Optional[int] = Field(default=60, ge=5, le=1440, description="Duration in minutes before sharing auto-expires")
    target_connection_ids: Optional[List[UUID]] = Field(default=None, description="Optional subset of connections. None means all trusted connections.")


class LocationUpdateRequest(BaseModel):
    """Live location update payload from user's active device."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accuracy: Optional[float] = None


class ConnectionResponse(BaseModel):
    """API view for a connection."""

    id: UUID
    user_id: UUID
    connected_user_id: Optional[UUID] = None
    invite_code: str
    display_name: str
    avatar_initials: str
    status: str
    location_sharing_active: bool
    location_sharing_expires_at: Optional[datetime] = None
    last_latitude: Optional[float] = None
    last_longitude: Optional[float] = None
    last_location_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ConnectionListResponse(BaseModel):
    """API view for connections list."""

    active_connections: List[ConnectionResponse] = Field(default_factory=list)
    pending_requests: List[ConnectionResponse] = Field(default_factory=list)
    items: List[ConnectionResponse] = Field(default_factory=list)
    total: int = 0

