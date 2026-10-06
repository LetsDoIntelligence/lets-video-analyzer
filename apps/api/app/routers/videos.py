import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.jobs.runner import ACTIVE, JobRunner
from app.media import MediaError, make_thumbnail, probe
from app.models import Video, VideoStatus
from app.schemas import VideoOut
from app.storage import (
    StorageError,
    clean_name,
    resolve_inside,
    save_upload,
    validate_upload,
)

router = APIRouter(prefix="/videos", tags=["videos"])

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")


def _get_or_404(session: Session, video_id: str) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise _NOT_FOUND
    return video


@router.post("", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
async def upload_video(file: UploadFile, session: SessionDep, settings: SettingsDep) -> Video:
    """Store an uploaded video and register it."""
    try:
        ext = validate_upload(file)
        video_id = uuid.uuid4().hex
        relative = f"videos/{video_id}{ext}"
        size = await save_upload(
            file, resolve_inside(settings.data_dir, relative), settings.max_upload_bytes
        )
    except StorageError as e:
        raise HTTPException(e.status_code, e.message) from e

    stored = resolve_inside(settings.data_dir, relative)
    try:
        info = await run_in_threadpool(probe, stored)
    except MediaError as e:
        stored.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e

    thumb_rel = f"thumbnails/{video_id}.jpg"
    thumb_stored: str | None = thumb_rel
    try:
        await run_in_threadpool(
            make_thumbnail,
            stored,
            resolve_inside(settings.data_dir, thumb_rel),
            min(1.0, info.duration_sec / 10),
        )
    except MediaError:
        thumb_stored = None  # a missing thumbnail isn't worth rejecting the upload

    video = Video(
        id=video_id,
        name=clean_name(file.filename or ""),
        filename=Path(file.filename or "").name[:255],
        stored_path=relative,
        thumbnail_path=thumb_stored,
        content_type=file.content_type,
        size_bytes=size,
        status=VideoStatus.ready,
        duration_sec=info.duration_sec,
        fps=info.fps,
        width=info.width,
        height=info.height,
        codec=info.codec,
    )
    session.add(video)
    session.commit()
    return video


@router.get("", response_model=list[VideoOut])
def list_videos(session: SessionDep) -> list[Video]:
    return list(session.scalars(select(Video).order_by(Video.created_at.desc())))


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: str, session: SessionDep) -> Video:
    return _get_or_404(session, video_id)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: str, request: Request, session: SessionDep, settings: SettingsDep
) -> None:
    video = _get_or_404(session, video_id)
    runner: JobRunner = request.app.state.jobs
    for job in video.jobs:
        if job.status in ACTIVE:
            runner.cancel(job.id)
    paths = [video.stored_path, video.thumbnail_path]
    session.delete(video)
    session.commit()
    for rel in filter(None, paths):
        resolve_inside(settings.data_dir, rel).unlink(missing_ok=True)


@router.get("/{video_id}/file")
def stream_video(video_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """Serve the video; supports HTTP Range so the player can seek."""
    video = _get_or_404(session, video_id)
    path = resolve_inside(settings.data_dir, video.stored_path)
    if not path.is_file():
        raise _NOT_FOUND
    return FileResponse(path, media_type=video.content_type or "video/mp4")


@router.get("/{video_id}/thumbnail")
def video_thumbnail(video_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    video = _get_or_404(session, video_id)
    if not video.thumbnail_path:
        raise _NOT_FOUND
    path = resolve_inside(settings.data_dir, video.thumbnail_path)
    if not path.is_file():
        raise _NOT_FOUND
    return FileResponse(path, media_type="image/jpeg")
