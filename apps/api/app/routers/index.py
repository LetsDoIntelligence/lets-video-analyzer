from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import IndexStatus, Video
from app.schemas import DetectionsOut, IndexOut, OverlayTrack
from app.vision import store
from app.vision.status import index_out

router = APIRouter(tags=["index"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/videos/{video_id}/index", response_model=IndexOut)
def get_video_index(video_id: str, session: SessionDep) -> IndexOut:
    """Whether the video's objects have been detected and tracked yet, and how far along."""
    if session.get(Video, video_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    return index_out(session, video_id)


MAX_OVERLAY_WINDOW = 120.0


@router.get("/videos/{video_id}/detections", response_model=DetectionsOut)
def get_detections(
    video_id: str,
    session: SessionDep,
    start: Annotated[float, Query(ge=0)] = 0,
    end: Annotated[float, Query(ge=0)] = 30,
) -> DetectionsOut:
    """Tracked boxes between start and end seconds (at most two minutes per call)."""
    if session.get(Video, video_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    if end <= start or end - start > MAX_OVERLAY_WINDOW:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Ask for a window of up to {MAX_OVERLAY_WINDOW:.0f} seconds.",
        )
    index = store.get_index(session, video_id)
    if index is None or index.status != IndexStatus.done or not index.frame_width:
        raise HTTPException(status.HTTP_409_CONFLICT, "The video hasn't been analyzed yet.")
    rows = store.query_tracks(session, video_id, t_from=start, t_to=end)
    tracks = [
        OverlayTrack(
            id=r.track_no,
            cls=r.cls,
            points=[[p[0], p[1], p[2], p[3], p[4]] for p in r.points if start <= p[0] <= end],
        )
        for r in rows
    ]
    return DetectionsOut(
        video_id=video_id,
        width=index.frame_width,
        height=index.frame_height or 0,
        start=start,
        end=end,
        tracks=[t for t in tracks if t.points],
    )
