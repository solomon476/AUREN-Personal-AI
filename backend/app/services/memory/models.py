"""Domain models for memory extraction, hybrid search, and context management."""

from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class MemorySearchResult(BaseModel):
    """Represents a scored memory candidate returned by hybrid retrieval."""

    id: UUID
    content: str
    memory_type: str
    category: str
    importance: int = Field(..., ge=1, le=5)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confirmation_status: str
    score: float


class ExtractedMemoryItem(BaseModel):
    """Represents an atomic extracted memory candidate from dialogue inference."""

    content: str = Field(..., min_length=1, max_length=10000)
    memory_type: str = Field(..., description="'fact', 'preference', 'goal', 'project', 'context', 'observation'")
    category: str = Field(..., description="'personal', 'work', 'technical', 'health_lifestyle', 'financial', 'general'")
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

