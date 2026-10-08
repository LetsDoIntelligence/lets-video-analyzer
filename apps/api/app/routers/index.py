from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.jobs.runner import ACTIVE
from app.models import IndexStatus, Job, JobKind, JobStatus, Video
from app.schemas import IndexOut, IndexState
from app.vision import store

router = APIRouter(tags=["index"])

SessionDep = Annotated[Session, Depends(get_session)]


def index_out(session: Session, video_id: str) -> IndexOut:
    """Combine the latest indexing job with the stored index into one UI-friendly state."""
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


@router.get("/videos/{video_id}/index", response_model=IndexOut)
def get_video_index(video_id: str, session: SessionDep) -> IndexOut:
    """Whether the video's objects have been detected and tracked yet, and how far along."""
    if session.get(Video, video_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    return index_out(session, video_id)
