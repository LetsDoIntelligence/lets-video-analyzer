"""In-process background jobs.

A deliberately small design for the POC: a single worker thread (the GPU is the bottleneck in
Phase 3 anyway), job state kept in the database, cooperative cancellation. The interface
(`submit` / `cancel` / handlers that `report` progress) is what a Celery/Arq worker would
replace later without touching the API layer.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Job, JobKind, JobStatus

logger = logging.getLogger("lets.jobs")

ACTIVE = (JobStatus.queued, JobStatus.running)


class JobCancelled(Exception):
    """Raised inside a handler (via `JobContext.checkpoint`) when the job was cancelled."""


@dataclass
class JobContext:
    job_id: str
    video_id: str
    _cancel: threading.Event
    _report: Callable[[float], None]

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def checkpoint(self) -> None:
        """Call regularly from long loops; aborts the job if it was cancelled."""
        if self._cancel.is_set():
            raise JobCancelled

    def report(self, progress: float) -> None:
        """Record progress (0..1) and honour cancellation."""
        self.checkpoint()
        self._report(min(max(progress, 0.0), 1.0))


Handler = Callable[[JobContext], None]


def _now() -> datetime:
    return datetime.now(UTC)


class JobRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        handlers: dict[JobKind, Handler],
        workers: int = 1,
    ) -> None:
        self._sessions = session_factory
        self.handlers = handlers
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="lets-job")
        self._cancel_flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------------------------

    def recover(self) -> int:
        """Fail jobs a previous process left unfinished (they can't be resumed)."""
        with self._sessions() as s:
            stale = list(s.scalars(select(Job).where(Job.status.in_(ACTIVE))))
            for job in stale:
                job.status = JobStatus.failed
                job.error = "Interrupted by a server restart."
                job.finished_at = _now()
            s.commit()
            return len(stale)

    def shutdown(self) -> None:
        with self._lock:
            for flag in self._cancel_flags.values():
                flag.set()
        self._pool.shutdown(wait=True, cancel_futures=True)

    # -- API ---------------------------------------------------------------------------------

    def submit(self, video_id: str, kind: JobKind) -> tuple[Job, bool]:
        """Queue a job. Returns (job, created); an already-active job of the same kind is reused."""
        if kind not in self.handlers:
            raise ValueError(f"No handler registered for job kind '{kind}'.")
        with self._lock, self._sessions() as s:
            existing = s.scalars(
                select(Job).where(
                    Job.video_id == video_id, Job.kind == kind, Job.status.in_(ACTIVE)
                )
            ).first()
            if existing:
                return existing, False
            job = Job(video_id=video_id, kind=kind)
            s.add(job)
            s.commit()
            flag = threading.Event()
            self._cancel_flags[job.id] = flag
            self._pool.submit(self._run, job.id, flag)
            return job, True

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns False if the job is unknown or already finished."""
        with self._lock:
            flag = self._cancel_flags.get(job_id)
        if flag is None:
            return False
        flag.set()
        return True

    # -- worker ------------------------------------------------------------------------------

    def _update(self, job_id: str, **fields: object) -> None:
        with self._sessions() as s:
            job = s.get(Job, job_id)
            if job is None:  # video (and so its jobs) was deleted meanwhile
                return
            for key, value in fields.items():
                setattr(job, key, value)
            s.commit()

    def _run(self, job_id: str, flag: threading.Event) -> None:
        try:
            with self._sessions() as s:
                job = s.get(Job, job_id)
                if job is None:
                    return
                kind, video_id = job.kind, job.video_id
            if flag.is_set():  # cancelled while still queued
                self._update(job_id, status=JobStatus.cancelled, finished_at=_now())
                return

            self._update(job_id, status=JobStatus.running, started_at=_now())
            ctx = JobContext(job_id, video_id, flag, lambda p: self._update(job_id, progress=p))
            try:
                self.handlers[kind](ctx)
            except JobCancelled:
                self._update(job_id, status=JobStatus.cancelled, finished_at=_now())
            except Exception as e:
                logger.exception("job %s (%s) failed", job_id, kind)
                self._update(
                    job_id,
                    status=JobStatus.failed,
                    error=str(e)[:500] or e.__class__.__name__,
                    finished_at=_now(),
                )
            else:
                self._update(job_id, status=JobStatus.succeeded, progress=1.0, finished_at=_now())
        finally:
            with self._lock:
                self._cancel_flags.pop(job_id, None)
