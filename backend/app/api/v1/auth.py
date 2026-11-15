"""Authentication router managing user identity verification."""

from fastapi import APIRouter, Depends, status
from app.core.security import get_current_user
from app.models.user import AuthenticatedUser, UserProfileResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Authenticated User Profile",
    description="Validates the caller's Supabase JWT and returns their profile information.",
)
async def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Return the profile information for the authenticated caller."""
    full_name = current_user.user_metadata.get("full_name") or current_user.user_metadata.get("name")
    avatar_url = current_user.user_metadata.get("avatar_url") or current_user.user_metadata.get("picture")

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        full_name=full_name,
        avatar_url=avatar_url,
        app_metadata=current_user.app_metadata,
        user_metadata=current_user.user_metadata,
    )

