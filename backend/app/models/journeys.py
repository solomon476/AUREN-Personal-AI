"""Data models and API schemas for GPS Journeys and Offline Sync."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class GPSPoint(BaseModel):
    """Represents a discrete GPS waypoint with telemetry and sensor data."""

    lat: float = Field(..., description="Latitude coordinate in decimal degrees")
    lng: float = Field(..., description="Longitude coordinate in decimal degrees")
    altitude: Optional[float] = Field(default=None, description="Altitude in meters")
    accuracy: float = Field(..., description="Estimated horizontal accuracy in meters")
    speed: Optional[float] = Field(default=None, description="Speed over ground in m/s")
    heading: Optional[float] = Field(default=None, description="Bearing heading in degrees")
    timestamp: str = Field(..., description="ISO 8601 timestamp string or time string")


class JourneyModel(BaseModel):
    """Persisted GPS Journey record."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    title: str = "Recorded Journey"
    status: str = Field(default="completed", description="'recording', 'paused', 'completed', 'cancelled'")
    distance_meters: float = 0.0
    duration_seconds: int = 0
    avg_speed_kmh: Optional[float] = 0.0
    is_offline_recorded: bool = False
    is_team_assignment: bool = False
    assignment_site: Optional[str] = None
    assignment_purpose: Optional[str] = None
    assignment_notes: Optional[str] = None
    check_in_time: Optional[datetime] = None
    check_in_coords: Optional[str] = None
    points: List[Dict[str, Any]] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class JourneyCreateRequest(BaseModel):
    """Payload to create or sync a completed/in-progress journey."""

    id: Optional[UUID] = None
    title: str = Field(default="Recorded Journey", max_length=200)
    status: str = Field(default="completed")
    distance_meters: float = Field(default=0.0, ge=0)
    duration_seconds: int = Field(default=0, ge=0)
    avg_speed_kmh: Optional[float] = Field(default=0.0, ge=0)
    is_offline_recorded: bool = False
    is_team_assignment: bool = False
    assignment_site: Optional[str] = None
    assignment_purpose: Optional[str] = None
    assignment_notes: Optional[str] = None
    check_in_time: Optional[datetime] = None
    check_in_coords: Optional[str] = None
    points: List[Dict[str, Any]] = Field(default_factory=list)
    idempotency_key: Optional[str] = Field(default=None, max_length=128)
    completed_at: Optional[datetime] = None


class JourneySyncBatchRequest(BaseModel):
    """Batch payload for offline journeys sync upon reconnection."""

    journeys: List[JourneyCreateRequest]


class JourneyResponse(BaseModel):
    """API view for a single journey."""

    id: UUID
    title: str
    status: str
    distance_meters: float
    duration_seconds: int
    avg_speed_kmh: Optional[float] = 0.0
    is_offline_recorded: bool = False
    is_team_assignment: bool = False
    assignment_site: Optional[str] = None
    assignment_purpose: Optional[str] = None
    assignment_notes: Optional[str] = None
    check_in_time: Optional[datetime] = None
    check_in_coords: Optional[str] = None
    points: List[Dict[str, Any]] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class JourneyListResponse(BaseModel):
    """API view for a collection of journeys."""

    items: List[JourneyResponse]
    total: int

