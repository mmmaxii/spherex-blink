"""Background jobs for work that takes more than a couple of seconds (reading many images, spectra).

The API never blocks on that work: a route submits a job and answers at once with its status; the
frontend polls /api/jobs/{id} until it is done. Jobs live in memory, so the service must run as a
single process (one uvicorn worker), which is what we have on Render.

    job = get_job_manager().submit("blink", job_id, lambda progress: run_blink(params, progress))

- The job id is derived from the request parameters, so two people asking for the same thing share
  one job instead of doing the work twice.
- `progress(fraction, stage)` is called by the pipeline; both values are shown to the user.
- A failed job keeps the error in the API's error shape; asking again starts it again.
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from ..config import get_settings
from ..errors import AppError, Busy, error_body
from .memory import give_back

log = logging.getLogger(__name__)

Status = Literal["queued", "running", "done", "failed"]
Progress = Callable[[float, str], None]
JobFn = Callable[[Progress], dict[str, Any]]


@dataclass
class Job:
    id: str
    kind: str
    status: Status = "queued"
    progress: float = 0.0
    stage: str = "Waiting in the queue"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 3),
            "stage": self.stage,
            "result": self.result,
            "error": self.error,
        }


def finished_job(job_id: str, kind: str, result: dict[str, Any]) -> Job:
    """A job that needed no work (its product was already on disk)."""
    return Job(id=job_id, kind=kind, status="done", progress=1.0, stage="Done", result=result)


class JobManager:
    def __init__(self, max_workers: int, max_queued: int, ttl_s: float):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._max_queued = max_queued
        self._ttl_s = ttl_s
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, job_id: str, fn: JobFn) -> Job:
        with self._lock:
            self._forget_old()
            existing = self._jobs.get(job_id)
            if existing and existing.status != "failed":
                return existing
            waiting = sum(1 for j in self._jobs.values() if j.status == "queued")
            if waiting >= self._max_queued:
                raise Busy("The server is busy with other requests. Try again in a minute.", retry_after_s=30)
            job = Job(id=job_id, kind=kind)
            self._jobs[job_id] = job
        self._pool.submit(self._run, job, fn)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def forget_finished(self, job_id: str) -> None:
        """Drop a finished job so the next submit runs it again (used when its files were removed)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in ("done", "failed"):
                del self._jobs[job_id]

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
            for job in self._jobs.values():
                counts[job.status] += 1
            return counts

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self, job: Job, fn: JobFn) -> None:
        job.status, job.stage = "running", "Starting"
        started = time.time()

        def progress(fraction: float, stage: str) -> None:
            job.progress = min(max(fraction, 0.0), 1.0)
            job.stage = stage

        try:
            job.result = fn(progress)
            job.status, job.progress, job.stage = "done", 1.0, "Done"
            log.info("job %s (%s) done in %.1f s", job.id, job.kind, time.time() - started)
        except AppError as e:
            job.error, job.status, job.stage = e.to_body(), "failed", "Failed"
            log.warning("job %s (%s) failed: %s %s", job.id, job.kind, e.code, e.message)
        except Exception as e:  # noqa: BLE001 - a job must never take the worker thread down
            job.error, job.status, job.stage = error_body(e), "failed", "Failed"
            log.exception("job %s (%s) crashed", job.id, job.kind)
        finally:
            job.finished_at = time.time()
            give_back()  # hand the job's freed memory back to the system

    def _forget_old(self) -> None:
        now = time.time()
        for job_id in [
            j.id for j in self._jobs.values() if j.finished_at and now - j.finished_at > self._ttl_s
        ]:
            del self._jobs[job_id]


@lru_cache
def get_job_manager() -> JobManager:
    s = get_settings()
    return JobManager(s.max_concurrent_jobs, s.max_queued_jobs, s.job_ttl_s)
