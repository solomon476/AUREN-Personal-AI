"""Abstract base repository for GPS Journeys."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from uuid import UUID

from app.models.journeys import JourneyCreateRequest, JourneyModel


class BaseJourneyRepository(ABC):
    """Abstract interface defining operations for journey persistence and retrieval."""

    @abstractmethod
    async def list_journeys(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[JourneyModel], int]:
        """List journeys for a user with pagination."""
        pass

    @abstractmethod
    async def get_journey_by_id(
        self,
        user_id: UUID,
        journey_id: UUID,
    ) -> Optional[JourneyModel]:
        """Retrieve a specific journey by ID."""
        pass

    @abstractmethod
    async def create_or_sync_journey(
        self,
        user_id: UUID,
        payload: JourneyCreateRequest,
    ) -> JourneyModel:
        """Create or sync a journey, deduplicating on idempotency_key."""
        pass

    @abstractmethod
    async def delete_journey(
        self,
        user_id: UUID,
        journey_id: UUID,
    ) -> bool:
        """Delete a journey owned by the user."""
        pass

