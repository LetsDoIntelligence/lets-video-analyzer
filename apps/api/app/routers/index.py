from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Video
from app.schemas import IndexOut
from app.vision.status import index_out

router = APIRouter(tags=["index"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/videos/{video_id}/index", response_model=IndexOut)
def get_video_index(video_id: str, session: SessionDep) -> IndexOut:
    """Whether the video's objects have been detected and tracked yet, and how far along."""
    if session.get(Video, video_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    return index_out(session, video_id)
