"""Abstract base repository interface for private journal storage."""

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional, Tuple
from uuid import UUID

from app.models.journal import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryUpdate,
)


class BaseJournalRepository(ABC):
    """Abstract interface defining required storage operations for private journal entries."""

    @abstractmethod
    async def list_entries(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        mood: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Tuple[List[JournalEntryResponse], int]:
        """List journal entries for a user with pagination and optional filters."""
        pass

    @abstractmethod
    async def get_entry(self, user_id: UUID, entry_id: UUID) -> Optional[JournalEntryResponse]:
        """Retrieve a single journal entry ensuring ownership."""
        pass

    @abstractmethod
    async def create_entry(self, user_id: UUID, payload: JournalEntryCreate) -> JournalEntryResponse:
        """Create a new journal entry."""
        pass

    @abstractmethod
    async def update_entry(
        self,
        user_id: UUID,
        entry_id: UUID,
        payload: JournalEntryUpdate,
    ) -> Optional[JournalEntryResponse]:
        """Update an existing journal entry ensuring ownership."""
        pass

    @abstractmethod
    async def delete_entry(self, user_id: UUID, entry_id: UUID) -> bool:
        """Delete an existing journal entry ensuring ownership."""
        pass
