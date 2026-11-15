"""Unified v1 API router consolidating all endpoints."""

from fastapi import APIRouter
from app.api.v1 import health

api_router = APIRouter()

# Include feature routers
api_router.include_router(health.router, tags=["Health"])

