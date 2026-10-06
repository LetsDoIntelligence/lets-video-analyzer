"""Job handlers. Real implementations arrive with the pipeline phases."""

import time

from app.jobs.runner import Handler, JobContext
from app.models import JobKind


def make_stub_indexing(steps: int, step_seconds: float) -> Handler:
    """Placeholder for detection + tracking (Phase 3): just reports progress."""

    def handler(ctx: JobContext) -> None:
        for i in range(steps):
            time.sleep(step_seconds)
            ctx.report((i + 1) / steps)

    return handler


def default_handlers(stub_steps: int, stub_step_ms: int) -> dict[JobKind, Handler]:
    return {JobKind.indexing: make_stub_indexing(stub_steps, stub_step_ms / 1000)}
