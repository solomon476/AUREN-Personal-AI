"""Domain and API schemas for Long-Term Memory, Epistemic Verification, and Context Transparency."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Orthogonal Taxonomy Types (Strictly aligned with PostgreSQL constraints)
# ---------------------------------------------------------------------------
MemoryType = Literal["fact", "preference", "goal", "project", "context", "observation"]
MemoryCategory = Literal["personal", "work", "technical", "health_lifestyle", "financial", "general"]
MemoryLifecycleStatus = Literal["active", "superseded", "expired", "archived", "rejected", "forgotten"]
MemoryConfirmationStatus = Literal["confirmed", "unconfirmed", "rejected", "system_asserted"]
MemoryOrigin = Literal[
    "explicit_user_statement",
    "inferred_dialogue",
    "user_direct_input",
    "user_direct_edit",
    "chat_inferred",
    "journal_inferred",
    "system_asserted",
    "legacy_import",
]

VALID_MEMORY_TYPES = {"fact", "preference", "goal", "project", "context", "observation"}
VALID_CATEGORIES = {"personal", "work", "technical", "health_lifestyle", "financial", "general"}
VALID_LIFECYCLE_STATUSES = {"active", "superseded", "expired", "archived", "rejected", "forgotten"}
VALID_CONFIRMATION_STATUSES = {"confirmed", "unconfirmed", "rejected", "system_asserted"}
VALID_ORIGINS = {
    "explicit_user_statement",
    "inferred_dialogue",
    "user_direct_input",
    "user_direct_edit",
    "chat_inferred",
    "journal_inferred",
    "system_asserted",
    "legacy_import",
}


class MemoryModel(BaseModel):
    """Domain model representing a persistent memory record."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    content: str
    memory_type: str = "fact"
    category: str = "general"
    importance: int = Field(default=1, ge=1, le=5)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confirmation_status: str = "unconfirmed"
    lifecycle_status: str = "active"
    origin: str = "user_direct_input"

    # Provenance and Lineage
    source_message_id: Optional[UUID] = None
    source_conversation_id: Optional[UUID] = None
    superseded_by_id: Optional[UUID] = None
    previous_version_id: Optional[UUID] = None
    root_memory_id: Optional[UUID] = None

    # Temporal & Access Audit
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    last_confirmed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    review_after: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryResponse(BaseModel):
    """API view for a memory entry exposing full epistemic metadata and provenance."""

    id: UUID
    content: str
    memory_type: str
    category: str
    importance: int
    confidence: Optional[float] = None
    confirmation_status: str
    lifecycle_status: str
    origin: str

    source_message_id: Optional[UUID] = None
    source_conversation_id: Optional[UUID] = None
    superseded_by_id: Optional[UUID] = None
    previous_version_id: Optional[UUID] = None
    root_memory_id: Optional[UUID] = None

    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    last_confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryListResponse(BaseModel):
    """Paginated collection view for Memory Explorer."""

    items: List[MemoryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class MemoryCreateRequest(BaseModel):
    """Request payload to manually create a confirmed memory."""

    content: str = Field(..., min_length=1, max_length=10000)
    memory_type: str = Field(default="fact")
    category: str = Field(default="general")
    importance: int = Field(default=3, ge=1, le=5)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Memory content cannot be empty or whitespace only.")
        return trimmed

    @field_validator("memory_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_MEMORY_TYPES:
            raise ValueError(f"Invalid memory_type '{v}'. Must be one of {sorted(VALID_MEMORY_TYPES)}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of {sorted(VALID_CATEGORIES)}")
        return v


class MemoryCorrectionRequest(BaseModel):
    """Request payload to correct an inaccurate memory, preserving historical lineage."""

    content: str = Field(..., min_length=1, max_length=10000)
    category: Optional[str] = None
    memory_type: Optional[str] = None
    importance: Optional[int] = Field(default=None, ge=1, le=5)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Corrected memory content cannot be empty.")
        return trimmed


class MemoryContextItem(BaseModel):
    """Safe, structured representation of a memory that was injected into conversation context."""

    id: UUID
    content: str
    memory_type: str
    category: str
    confirmation_status: str
    importance: int
    score: float


class MessageContextResponse(BaseModel):
    """Context provenance report explaining which memories influenced a specific assistant response."""

    message_id: UUID
    conversation_id: UUID
    model: Optional[str] = None
    retrieved_memories: List[MemoryContextItem] = Field(default_factory=list)
    memory_count: int = 0

