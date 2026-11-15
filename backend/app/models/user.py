"""Domain models for authenticated users and identity context."""

from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AuthenticatedUser(BaseModel):
    """Represents a validated, authenticated user parsed from a Supabase JWT."""

    id: UUID = Field(..., description="Unique Supabase Auth User ID (sub claim)")
    email: Optional[str] = Field(default=None, description="User email address")
    role: str = Field(default="authenticated", description="User role in Supabase")
    app_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)

