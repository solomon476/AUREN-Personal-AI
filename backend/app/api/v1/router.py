"""Unified v1 API router consolidating all endpoints."""

from fastapi import APIRouter
from app.api.v1 import (
    auth,
    chat,
    connections,
    goals,
    health,
    journal,
    journeys,
    memories,
    notifications,
    productivity,
    projects,
    reflection,
    reminders,
    search,
    tasks,
)

api_router = APIRouter()

# Include feature routers
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(connections.router)
api_router.include_router(journeys.router)
api_router.include_router(memories.router)
api_router.include_router(tasks.router)
api_router.include_router(projects.router)
api_router.include_router(goals.router)
api_router.include_router(productivity.router)
api_router.include_router(reminders.router)
api_router.include_router(notifications.router)
api_router.include_router(search.router)
api_router.include_router(reflection.router)
api_router.include_router(journal.router)
