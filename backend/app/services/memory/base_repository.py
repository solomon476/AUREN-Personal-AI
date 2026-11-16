"""Abstract Base Class for Memory Persistence Repositories.

Defines the asynchronous interface for memory exploration, lifecycle state transitions,
epistemic verification, and historical lineage tracking across SQLite and Supabase backends.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from uuid import UUID

from app.models.memory import MemoryModel


class BaseMemoryRepository(ABC):
    """Abstract interface for memory persistence, exploration, and verification.

    Guarantees:
    - User ownership enforcement on all queries and mutations.
    - Epistemic lifecycle state machine constraints (e.g. terminal rejected/superseded states).
    - Lineage preservation during memory correction (previous_version_id and superseded_by_id).
    - Strict journal isolation (no raw journal entries exposed through memory queries).
    - Asynchronous non-blocking contract.
    """

    @abstractmethod
    async def list_memories(
        self,
        user_id: UUID,
        query: Optional[str] = None,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        confirmation_status: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MemoryModel], int]:
        """List and search memories owned by user_id with server-side pagination and filters.

        Returns:
            Tuple of (memories_for_page, total_matching_count).
        """
        pass

    @abstractmethod
    async def get_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        """Fetch a single memory by ID, verifying caller ownership."""
        pass

    @abstractmethod
    async def create_memory(
        self,
        user_id: UUID,
        content: str,
        memory_type: str = "fact",
        category: str = "general",
        importance: int = 3,
        origin: str = "user_direct_input",
    ) -> MemoryModel:
        """Create a user-asserted memory in active/confirmed state."""
        pass

    @abstractmethod
    async def confirm_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        """Transition an unconfirmed memory to confirmed status.

        Fails if memory is not found, not owned by user, or in an invalid state (e.g. rejected/superseded).
        """
        pass

    @abstractmethod
    async def reject_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        """Reject an unconfirmed or candidate inference, transitioning it to rejected status.

        Terminal state: rejected memories cannot be confirmed, reactivated, or superseded.
        """
        pass

    @abstractmethod
    async def correct_memory(
        self,
        user_id: UUID,
        memory_id: UUID,
        content: str,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
    ) -> Optional[MemoryModel]:
        """Atomically correct an inaccurate memory, preserving historical lineage.

        Supersedes the target memory and creates a new active, confirmed memory linking to it.
        Returns the new active successor memory.
        """
        pass

    @abstractmethod
    async def archive_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        """Transition an active memory to archived status."""
        pass

    @abstractmethod
    async def restore_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        """Transition an archived or expired memory back to active status."""
        pass

    @abstractmethod
    async def outdate_memory(self, user_id: UUID, memory_id: UUID) -> Optional[MemoryModel]:
        """Mark an active memory as expired/outdated."""
        pass
