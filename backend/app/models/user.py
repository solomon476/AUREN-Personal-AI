"""Domain models for authenticated users, profile management, and data export."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AuthenticatedUser(BaseModel):
    """Represents a validated, authenticated user parsed from a Supabase JWT."""

    id: UUID = Field(..., description="Unique Supabase Auth User ID (sub claim)")
    email: Optional[str] = Field(default=None, description="User email address")
    role: str = Field(default="authenticated", description="User role in Supabase")
    token: Optional[str] = Field(default=None, description="Raw Bearer JWT token of the authenticated session")
    app_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def user_id(self) -> UUID:
        """Compatibility property aliasing the canonical id attribute (Supabase Auth sub UUID)."""
        return self.id


class UserProfileUpdate(BaseModel):
    """Payload to update the user's profile and preferences."""

    full_name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=1024)
    preferences: Optional[Dict[str, Any]] = Field(default=None)


class UserProfileResponse(BaseModel):
    """Response schema for the authenticated user's profile (/api/v1/auth/me)."""

    id: UUID = Field(..., description="Unique user ID")
    email: Optional[str] = Field(default=None, description="User email address")
    role: str = Field(default="authenticated", description="Auth role")
    full_name: Optional[str] = Field(default=None, description="User full display name")
    avatar_url: Optional[str] = Field(default=None, description="User avatar image URL")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User personal and AI preferences")
    app_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)


class UserDataExportResponse(BaseModel):
    """Complete GDPR-compliant personal data export package."""

    user_id: UUID
    email: Optional[str] = None
    exported_at: datetime
    preferences: Dict[str, Any] = Field(default_factory=dict)
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    goals: List[Dict[str, Any]] = Field(default_factory=list)
    memories: List[Dict[str, Any]] = Field(default_factory=list)
    journal_entries: List[Dict[str, Any]] = Field(default_factory=list)
    conversations: List[Dict[str, Any]] = Field(default_factory=list)
