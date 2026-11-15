"""Health check endpoint router."""

from fastapi import APIRouter, status
from app.core.config import settings
from app.models.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description="Returns current service operational status, version, and runtime environment.",
)
async def get_health() -> HealthResponse:
    """Return health check status for backend monitoring."""
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )

