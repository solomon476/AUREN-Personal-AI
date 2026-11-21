"""Abstract base repository for Trusted Connections and Location Sharing."""

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from app.models.connections import ConnectionModel, LocationSharingToggleRequest, LocationUpdateRequest


class BaseConnectionRepository(ABC):
    """Abstract interface defining operations for private connections and location sharing."""

    @abstractmethod
    async def list_connections(self, user_id: UUID) -> List[ConnectionModel]:
        """List active and pending connections associated with user."""
        pass

    @abstractmethod
    async def create_invite(self, user_id: UUID, display_name: str) -> ConnectionModel:
        """Create a new invitation code for a prospective connection."""
        pass

    @abstractmethod
    async def accept_invite(self, user_id: UUID, invite_code: str) -> ConnectionModel:
        """Accept an invitation, establishing a mutual connection."""
        pass

    @abstractmethod
    async def decline_invite(self, user_id: UUID, connection_id: UUID) -> bool:
        """Decline a pending connection invitation."""
        pass

    @abstractmethod
    async def revoke_connection(self, user_id: UUID, connection_id: UUID) -> bool:
        """Revoke or remove an existing connection."""
        pass

    @abstractmethod
    async def toggle_location_sharing(
        self,
        user_id: UUID,
        payload: LocationSharingToggleRequest,
    ) -> bool:
        """Enable or disable voluntary location sharing."""
        pass

    @abstractmethod
    async def update_location(
        self,
        user_id: UUID,
        payload: LocationUpdateRequest,
    ) -> bool:
        """Update live GPS location for user's active sharing sessions."""
        pass

