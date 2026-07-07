"""
Job manager.

Tracks per-user check jobs, enforces single-job-per-user, and wires
the parser → checker → writer pipeline together.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

from bot.services.proxy.checker import CheckerConfig, CheckStats, ProxyChecker
from bot.services.proxy.parser import ProxyEntry, parse_proxy_list
from bot.services.proxy.writer import write_results
from bot.utils.logger import get_logger

log = get_logger(__name__)


class JobStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    DONE = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass
class Job:
    job_id: str
    user_id: int
    status: JobStatus = JobStatus.PENDING
    stats: Optional[CheckStats] = None
    output_paths: dict[str, Path] = field(default_factory=dict)
    error: Optional[str] = None
    invalid_count: int = 0
    checker: Optional[ProxyChecker] = None
    task: Optional[asyncio.Task] = None  # type: ignore[type-arg]


class JobManager:
    """Singleton-style in-memory job registry."""

    def __init__(self, output_dir: Path) -> None:
        self._jobs: dict[int, Job] = {}   # user_id → active job
        self._output_dir = output_dir

    def get_job(self, user_id: int) -> Optional[Job]:
        return self._jobs.get(user_id)

    def has_active_job(self, user_id: int) -> bool:
        job = self._jobs.get(user_id)
        return job is not None and job.status == JobStatus.RUNNING

    def cancel_job(self, user_id: int) -> bool:
        job = self._jobs.get(user_id)
        if job and job.checker:
            job.checker.cancel()
            job.status = JobStatus.CANCELLED
            return True
        return False

    async def start_job(
        self,
        user_id: int,
        raw_text: str,
        config: CheckerConfig,
        on_progress: Optional[Callable[[CheckStats], None]] = None,
        max_proxies: int = 100_000,
    ) -> Job:
        """Parse proxies, start checking, return the Job object immediately."""

        if self.has_active_job(user_id):
            raise RuntimeError("You already have a running job. Use /cancel first.")

        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id=job_id, user_id=user_id, status=JobStatus.RUNNING)
        self._jobs[user_id] = job

        proxies, invalid = parse_proxy_list(raw_text, limit=max_proxies)
        job.invalid_count = len(invalid)

        checker = ProxyChecker(config)
        job.checker = checker

        async def _run() -> None:
            try:
                results, stats = await checker.check_bulk(
                    proxies,
                    on_progress=on_progress,
                    progress_interval=max(1, len(proxies) // 200),
                )
                stats.invalid_format = job.invalid_count
                job.stats = stats
                job.output_paths = await write_results(
                    results, invalid, self._output_dir, job_id
                )
                job.status = (
                    JobStatus.CANCELLED if stats.cancelled else JobStatus.DONE
                )
                log.info(
                    "job_done",
                    job_id=job_id,
                    user=user_id,
                    working=stats.working,
                    total=stats.total,
                    elapsed=f"{stats.elapsed:.1f}s",
                )
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
            except Exception as exc:
                log.exception("job_failed", job_id=job_id, exc=str(exc))
                job.status = JobStatus.FAILED
                job.error = str(exc)

        job.task = asyncio.create_task(_run())
        return job
