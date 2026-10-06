import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session
from app.jobs.runner import ACTIVE, JobRunner
from app.models import Job, Video
from app.schemas import JobCreate, JobOut

router = APIRouter(tags=["jobs"])

SessionDep = Annotated[Session, Depends(get_session)]


def get_runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.jobs
    return runner


RunnerDep = Annotated[JobRunner, Depends(get_runner)]

POLL_SECONDS = 0.25


def _job_or_404(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return job


@router.post("/videos/{video_id}/jobs", response_model=JobOut, status_code=202)
def start_job(
    video_id: str,
    body: JobCreate,
    session: SessionDep,
    runner: RunnerDep,
    response: Response,
) -> Job:
    """Start a job for a video. If one of that kind is already running, it is returned (200)."""
    if session.get(Video, video_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    try:
        job, created = runner.submit(video_id, body.kind)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if not created:
        response.status_code = status.HTTP_200_OK
    return job


@router.get("/videos/{video_id}/jobs", response_model=list[JobOut])
def list_video_jobs(video_id: str, session: SessionDep) -> list[Job]:
    if session.get(Video, video_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    return list(
        session.scalars(select(Job).where(Job.video_id == video_id).order_by(Job.created_at.desc()))
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: SessionDep) -> Job:
    return _job_or_404(session, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, status_code=202)
def cancel_job(job_id: str, session: SessionDep, runner: RunnerDep) -> Job:
    job = _job_or_404(session, job_id)
    if job.status not in ACTIVE or not runner.cancel(job_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "That job has already finished.")
    return job


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events: the job's state on connect, then on every change, until it ends."""
    factory: sessionmaker[Session] = request.app.state.session_factory

    def snapshot() -> JobOut | None:
        with factory() as s:
            job = s.get(Job, job_id)
            return JobOut.model_validate(job) if job else None

    first = await run_in_threadpool(snapshot)
    if first is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")

    async def stream() -> AsyncIterator[str]:
        last = first
        yield f"data: {last.model_dump_json(by_alias=True)}\n\n"
        while last.status in ACTIVE:
            await asyncio.sleep(POLL_SECONDS)
            current = await run_in_threadpool(snapshot)
            if current is None:  # deleted along with its video
                return
            if current != last:
                last = current
                yield f"data: {current.model_dump_json(by_alias=True)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
