"""Authentication and user profile router."""

from fastapi import APIRouter, Depends, status

from app.core.security import get_current_user
from app.models.user import (
    AuthenticatedUser,
    UserDataExportResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.profile_service import profile_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Authenticated User Profile",
    description="Validates the caller's Supabase JWT and returns their profile and preferences.",
)
async def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Return the profile and preferences for the authenticated caller."""
    return await profile_service.get_profile(current_user)


@router.patch(
    "/profile",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update User Profile & Preferences",
    description="Update user display name, avatar, and AI/application preferences.",
)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Update profile and preferences for the authenticated caller."""
    return await profile_service.update_profile(current_user, payload)


@router.post(
    "/export",
    response_model=UserDataExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Export User Personal Data",
    description="Export complete structured package of user tasks, projects, goals, memories, and journal entries.",
)
async def export_my_data(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UserDataExportResponse:
    """Export complete personal data package for authenticated user."""
    return await profile_service.export_data(current_user)
