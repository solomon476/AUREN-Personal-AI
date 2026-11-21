"""FastAPI Application entry point for AUREN Personal AI Backend."""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info("Starting up %s (v%s) in [%s] mode...", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)

    # In-process background memory extraction worker
    worker_runner = None
    worker_task = None
    worker_db_url = settings.WORKER_DATABASE_URL or settings.DATABASE_URL
    if settings.MEMORY_WORKER_ENABLED and worker_db_url:
        try:
            from app.services.memory.runner import WorkerRunner
            logger.info("Initializing background memory extraction worker in application lifespan...")
            worker_runner = WorkerRunner(database_url=worker_db_url, settings=settings)
            worker_task = asyncio.create_task(worker_runner.run())
            logger.info("Background memory extraction worker task initiated successfully.")
        except Exception as exc:
            logger.warning("Could not launch background memory worker (non-blocking): %s", exc)
    else:
        logger.info("Background memory extraction worker is inactive (no WORKER_DATABASE_URL configured).")

    yield

    if worker_runner and worker_task:
        logger.info("Shutting down background memory extraction worker...")
        worker_runner.stop()
        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            logger.warning("Worker shutdown timed out or task cancelled during lifespan exit.")
        except Exception as exc:
            logger.error("Error encountered while stopping memory worker: %s", exc)

    logger.info("Shutting down %s...", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AUREN - Premium Personal AI Assistant Platform Backend API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https://frontend-[a-zA-Z0-9_\-]+\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint providing service information."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }

