"""Pydantic models for AUREN Private Journal."""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class JournalEntryBase(BaseModel):
    """Base fields for a private journal entry."""
    title: Optional[str] = Field(default=None, max_length=255, description="Optional entry title")
    content: str = Field(..., min_length=1, description="Markdown reflection content")
    mood: Optional[str] = Field(default=None, max_length=50, description="User mood or state of mind")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    is_private: bool = Field(default=True, description="Cryptographic privacy guarantee flag")
    entry_date: Optional[date] = Field(default=None, description="Date for this journal entry")


class JournalEntryCreate(JournalEntryBase):
    """Payload to create a new journal entry."""
    pass


class JournalEntryUpdate(BaseModel):
    """Payload to update an existing journal entry."""
    title: Optional[str] = Field(default=None, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1)
    mood: Optional[str] = Field(default=None, max_length=50)
    tags: Optional[List[str]] = None
    is_private: Optional[bool] = None
    entry_date: Optional[date] = None


class JournalEntryResponse(BaseModel):
    """Complete journal entry representation."""
    id: UUID
    user_id: UUID
    title: Optional[str] = None
    content: str
    mood: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_private: bool = True
    entry_date: date
    created_at: datetime
    updated_at: datetime


class JournalEntryListResponse(BaseModel):
    """Paginated list response for journal entries."""
    items: List[JournalEntryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
