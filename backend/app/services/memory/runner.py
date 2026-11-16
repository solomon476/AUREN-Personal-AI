"""Standalone background worker runner for processing memory extraction jobs."""

import asyncio
import logging
import signal
import uuid
from typing import Any, Dict, List, Optional

import asyncpg

from app.core.config import Settings, settings as default_settings
from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.embeddings.factory import get_embedding_provider
from app.services.llm.base import BaseLLMProvider
from app.services.llm.factory import get_llm_provider
from app.services.memory.worker import MemoryExtractionWorker

logger = logging.getLogger(__name__)


class WorkerRunner:
    """Manages the lifecycle, polling loop, concurrency, and graceful shutdown of a memory extraction worker."""

    def __init__(
        self,
        worker_id: Optional[str] = None,
        db_pool: Optional[asyncpg.Pool] = None,
        database_url: Optional[str] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        poll_interval: Optional[float] = None,
        batch_size: Optional[int] = None,
        lease_seconds: Optional[int] = None,
        concurrency: Optional[int] = None,
        settings: Settings = default_settings,
    ):
        self.settings = settings
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.db_pool = db_pool
        self.database_url = database_url or settings.WORKER_DATABASE_URL
        self._owns_db_pool = db_pool is None

        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider

        self.poll_interval = poll_interval if poll_interval is not None else settings.MEMORY_WORKER_POLL_INTERVAL_SECONDS
        self.batch_size = batch_size if batch_size is not None else settings.MEMORY_WORKER_BATCH_SIZE
        self.lease_seconds = lease_seconds if lease_seconds is not None else settings.MEMORY_WORKER_LEASE_SECONDS
        self.concurrency = concurrency if concurrency is not None else settings.MEMORY_WORKER_CONCURRENCY

        self._stop_event = asyncio.Event()
        self._is_running = False
        self._worker: Optional[MemoryExtractionWorker] = None
        self._active_tasks: set = set()

        # Operational metrics
        self.metrics: Dict[str, int] = {
            "poll_cycles": 0,
            "jobs_claimed": 0,
            "jobs_succeeded": 0,
            "jobs_failed": 0,
        }

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def initialize(self):
        """Initializes database pool and provider dependencies."""
        if self.db_pool is None:
            if not self.database_url:
                raise ValueError("WORKER_DATABASE_URL or db_pool must be provided to run MemoryExtractionWorker")

            # Verify that connection does not attempt to authenticate directly as the NOLOGIN role 'auren_worker'
            try:
                from urllib.parse import urlparse
                parsed = urlparse(self.database_url)
                if parsed.username == "auren_worker":
                    raise ValueError(
                        "WORKER_DATABASE_URL cannot use 'auren_worker' directly (it is a NOLOGIN NOINHERIT role). "
                        "Configure the dedicated login role 'auren_worker_service' instead."
                    )
            except ValueError:
                raise
            except Exception as parse_err:
                logger.debug("Failed parsing worker database URL: %s", parse_err)

            logger.info("Connecting worker to database pool...")
            self.db_pool = await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=1,
                max_size=max(2, self.concurrency + 1),
            )

        if self.llm_provider is None:
            self.llm_provider = get_llm_provider(self.settings)

        if self.embedding_provider is None:
            try:
                self.embedding_provider = get_embedding_provider(self.settings)
            except Exception as emb_err:
                logger.warning("Could not initialize embedding provider for worker: %s", emb_err)
                self.embedding_provider = None

        self._worker = MemoryExtractionWorker(
            worker_id=self.worker_id,
            db_pool=self.db_pool,
            llm_provider=self.llm_provider,
            embedding_provider=self.embedding_provider,
            batch_size=self.batch_size,
            lease_seconds=self.lease_seconds,
        )

        logger.info(
            "WorkerRunner initialized [id=%s, concurrency=%d, poll=%.1fs, batch=%d, lease=%ds]",
            self.worker_id,
            self.concurrency,
            self.poll_interval,
            self.batch_size,
            self.lease_seconds,
        )

    def stop(self):
        """Signals the polling loop to stop cleanly."""
        logger.info("Stop requested for worker %s", self.worker_id)
        self._stop_event.set()

    async def run(self):
        """Main operational execution loop with polling and bounded concurrency."""
        if self._worker is None:
            await self.initialize()

        self._is_running = True
        semaphore = asyncio.Semaphore(self.concurrency)
        logger.info("Worker %s entering polling execution loop", self.worker_id)

        try:
            while not self._stop_event.is_set():
                self.metrics["poll_cycles"] += 1
                try:
                    jobs: List[Dict[str, Any]] = []
                    async with self.db_pool.acquire() as claim_conn:
                        jobs = await self._worker.claim_jobs(claim_conn)

                    if jobs:
                        self.metrics["jobs_claimed"] += len(jobs)
                        logger.info("Worker %s claimed %d extraction jobs", self.worker_id, len(jobs))

                        async def _process_single(job_data: Dict[str, Any]):
                            async with semaphore:
                                if self._stop_event.is_set():
                                    return
                                async with self.db_pool.acquire() as proc_conn:
                                    success = await self._worker.process_job(proc_conn, job_data)
                                    if success:
                                        self.metrics["jobs_succeeded"] += 1
                                    else:
                                        self.metrics["jobs_failed"] += 1

                        tasks = [asyncio.create_task(_process_single(j)) for j in jobs]
                        for t in tasks:
                            self._active_tasks.add(t)
                            t.add_done_callback(self._active_tasks.discard)

                        await asyncio.gather(*tasks, return_exceptions=True)
                    else:
                        # Sleep with responsive stop check
                        try:
                            await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                        except asyncio.TimeoutError:
                            pass

                except Exception as loop_err:
                    logger.warning("Error in worker polling cycle: %s", loop_err)
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass

        finally:
            self._is_running = False
            logger.info("Worker %s shutting down. Awaiting %d active tasks...", self.worker_id, len(self._active_tasks))
            if self._active_tasks:
                await asyncio.wait(self._active_tasks, timeout=15.0)

            if self._owns_db_pool and self.db_pool is not None:
                await self.db_pool.close()
                logger.info("Worker %s database pool closed", self.worker_id)

            logger.info(
                "Worker %s shutdown complete. Final metrics: %s",
                self.worker_id,
                self.metrics,
            )


def setup_signal_handlers(runner: WorkerRunner):
    """Installs POSIX signal handlers for graceful shutdown on SIGINT and SIGTERM."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runner.stop)
        except (NotImplementedError, RuntimeError):
            # Not supported on all environments (e.g. non-main threads or Windows)
            pass


async def main_async():
    """Asynchronous entry point for running the extraction worker process."""
    if not default_settings.MEMORY_WORKER_ENABLED:
        logger.info("MEMORY_WORKER_ENABLED is false; memory extraction worker will not start.")
        return

    runner = WorkerRunner()
    setup_signal_handlers(runner)
    await runner.run()


def main():
    """CLI entrypoint: python -m app.services.memory.runner"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Worker process interrupted by user.")


if __name__ == "__main__":
    main()

