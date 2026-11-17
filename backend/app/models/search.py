"""Pydantic models for Phase 3C.5 Omnisearch & Reflective Intelligence APIs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Source Types
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    conversation = "conversation"
    message = "message"
    memory = "memory"
    task = "task"
    project = "project"
    goal = "goal"


class RelationshipType(str, Enum):
    related = "related"
    supports = "supports"
    contradicts = "contradicts"
    supersedes = "supersedes"
    derived_from = "derived_from"
    referenced_in = "referenced_in"


# ---------------------------------------------------------------------------
# Omnisearch
# ---------------------------------------------------------------------------

class OmnisearchQuery(BaseModel):
    """Query parameters for the unified search endpoint."""
    q: str = Field(..., min_length=1, max_length=500, description="Search query string")
    sources: Optional[List[SourceType]] = Field(
        default=None,
        description="Restrict search to these source types. Null means all."
    )
    date_from: Optional[datetime] = Field(default=None, description="Earliest created_at filter")
    date_to: Optional[datetime] = Field(default=None, description="Latest created_at filter")
    page: int = Field(default=1, ge=1, description="1-based page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Results per page")


class SearchResultItem(BaseModel):
    """A single result returned by the unified search."""
    source_type: SourceType
    id: UUID
    title: str
    snippet: str = Field(description="Short excerpt with query terms highlighted or context")
    created_at: datetime
    updated_at: Optional[datetime] = None
    score: float = Field(description="Relevance score 0–1; higher is more relevant")
    provenance: str = Field(
        description="Human-readable origin label (e.g. 'confirmed memory', 'ai-extracted memory')"
    )
    navigation_path: str = Field(
        description="Frontend route for direct navigation (e.g. '/tasks/uuid')"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OmnisearchResponse(BaseModel):
    """Paginated response from the unified search endpoint."""
    query: str
    sources_searched: List[SourceType]
    results: List[SearchResultItem]
    total_count: int
    page: int
    page_size: int
    has_more: bool


# ---------------------------------------------------------------------------
# Record Links
# ---------------------------------------------------------------------------

class RecordLinkItem(BaseModel):
    """A persisted cross-entity relationship."""
    id: UUID
    user_id: UUID
    source_type: SourceType
    source_id: UUID
    target_type: SourceType
    target_id: UUID
    relationship_type: RelationshipType
    confidence: float = Field(ge=0.0, le=1.0)
    is_inferred: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RecordLinkCreate(BaseModel):
    """Request body for creating a user-confirmed record link."""
    source_type: SourceType
    source_id: UUID
    target_type: SourceType
    target_id: UUID
    relationship_type: RelationshipType = RelationshipType.related
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: Optional[str] = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Reflective Intelligence
# ---------------------------------------------------------------------------

class ContradictionItem(BaseModel):
    """A detected potential contradiction between two memory records."""
    memory_a_id: UUID
    memory_a_content: str
    memory_a_status: str
    memory_b_id: UUID
    memory_b_content: str
    memory_b_status: str
    contradiction_type: str = Field(
        description="'value_conflict', 'supersession_chain', or 'temporal_inconsistency'"
    )
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0, description="Detector confidence in this finding")
    suggested_action: str


class StalenessItem(BaseModel):
    """A record flagged as potentially outdated and worth user review."""
    source_type: SourceType
    id: UUID
    title: str
    reason: str = Field(description="Why this record is flagged (overdue, no recent update, etc.)")
    last_updated: Optional[datetime]
    navigation_path: str
    staleness_score: float = Field(ge=0.0, le=1.0)


class RelatedRecord(BaseModel):
    """A record related to a given source entity, with relationship context."""
    source_type: SourceType
    id: UUID
    title: str
    relationship_type: RelationshipType
    relationship_source: str = Field(
        description="'explicit_link', 'structural', or 'inferred'"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    navigation_path: str


class ReflectionInsightsResponse(BaseModel):
    """Overview of all reflection signals for the user."""
    contradiction_count: int
    staleness_count: int
    inferred_link_count: int
    contradictions: List[ContradictionItem]
    staleness_items: List[StalenessItem]
    generated_at: datetime


class RelationshipsResponse(BaseModel):
    """Related records for a given source entity."""
    source_type: SourceType
    source_id: UUID
    relationships: List[RelatedRecord]
    total_count: int

