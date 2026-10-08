"""One UI-friendly view of a video's analysis state (latest job + stored index)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.runner import ACTIVE
from app.models import IndexStatus, Job, JobKind, JobStatus
from app.schemas import IndexOut, IndexState
from app.vision import store


def index_out(session: Session, video_id: str) -> IndexOut:
    """Combine the latest indexing job with the stored index into one state."""
    job = session.scalars(
        select(Job)
        .where(Job.video_id == video_id, Job.kind == JobKind.indexing)
        .order_by(Job.created_at.desc())
    ).first()
    index = store.get_index(session, video_id)

    if job is not None and job.status in ACTIVE:
        state = IndexState.queued if job.status == JobStatus.queued else IndexState.running
        return IndexOut(video_id=video_id, state=state, progress=job.progress, job_id=job.id)
    job_id = job.id if job else None
    if index is not None and index.status == IndexStatus.done:
        return IndexOut(
            video_id=video_id,
            state=IndexState.ready,
            progress=1.0,
            job_id=job_id,
            n_tracks=index.n_tracks,
        )
    if index is not None and index.status == IndexStatus.failed:
        return IndexOut(
            video_id=video_id, state=IndexState.failed, job_id=job_id, error=index.error
        )
    if job is not None and job.status == JobStatus.failed:
        return IndexOut(video_id=video_id, state=IndexState.failed, job_id=job_id, error=job.error)
    return IndexOut(video_id=video_id, state=IndexState.none, job_id=job_id)
