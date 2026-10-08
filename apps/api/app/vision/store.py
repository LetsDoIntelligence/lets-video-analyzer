"""Persist and query the detection/tracking index (`video_indexes` + `tracks` tables)."""

from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import IndexStatus, TrackRecord, VideoIndex
from app.vision.tracker import Track, TrackerConfig


def index_params(
    *, model: str, sample_fps: float, conf: float, tracker: TrackerConfig
) -> dict[str, object]:
    """What an index was built with. A stored index is reused only while this is unchanged."""
    return {"model": model, "sample_fps": sample_fps, "conf": conf, "tracker": asdict(tracker)}


def get_index(session: Session, video_id: str) -> VideoIndex | None:
    return session.get(VideoIndex, video_id)


def invalidate(session: Session, video_id: str) -> None:
    """Forget the index entirely (tracks and state), forcing a rebuild on the next job."""
    session.execute(delete(TrackRecord).where(TrackRecord.video_id == video_id))
    session.execute(delete(VideoIndex).where(VideoIndex.video_id == video_id))
    session.commit()
    session.expire_all()  # bulk deletes bypass the identity map; don't serve stale rows


def is_current(session: Session, video_id: str, params: dict[str, object]) -> bool:
    """True when the video already has a finished index built with exactly these params."""
    index = get_index(session, video_id)
    return index is not None and index.status == IndexStatus.done and index.params == params


def start_index(session: Session, video_id: str, params: dict[str, object]) -> VideoIndex:
    """Mark the video as being (re)indexed and drop the old tracks, so readers never see a mix."""
    session.execute(delete(TrackRecord).where(TrackRecord.video_id == video_id))
    index = get_index(session, video_id)
    if index is None:
        index = VideoIndex(video_id=video_id)
        session.add(index)
    index.status = IndexStatus.running
    index.params = params
    index.frames = 0
    index.n_tracks = 0
    index.error = None
    index.created_at = datetime.now(UTC)
    index.finished_at = None
    session.commit()
    return index


def save_index(
    session: Session,
    video_id: str,
    *,
    tracks: Sequence[Track],
    frames: int,
    width: int | None,
    height: int | None,
) -> VideoIndex:
    """Store the finished tracks and mark the index done, in one transaction."""
    index = get_index(session, video_id)
    if index is None:
        raise LookupError(f"no index started for video {video_id}")
    session.execute(delete(TrackRecord).where(TrackRecord.video_id == video_id))
    session.add_all(
        TrackRecord(
            video_id=video_id,
            track_no=t.track_id,
            cls=t.cls,
            t_in=t.t_in,
            t_out=t.t_out,
            confidence=round(t.confidence, 3),
            points=[
                [round(p.t, 3), *(round(v, 1) for v in p.box), round(p.conf, 2)] for p in t.points
            ],
        )
        for t in tracks
    )
    index.status = IndexStatus.done
    index.frames = frames
    index.frame_width = width
    index.frame_height = height
    index.n_tracks = len(tracks)
    index.error = None
    index.finished_at = datetime.now(UTC)
    session.commit()
    return index


def fail_index(session: Session, video_id: str, error: str) -> None:
    index = get_index(session, video_id)
    if index is None:
        return
    index.status = IndexStatus.failed
    index.error = error
    index.finished_at = datetime.now(UTC)
    session.commit()


def query_tracks(
    session: Session,
    video_id: str,
    *,
    cls: str | Sequence[str] | None = None,
    t_from: float | None = None,
    t_to: float | None = None,
) -> list[TrackRecord]:
    """Tracks of a finished index that were on screen at any point in [t_from, t_to]."""
    index = get_index(session, video_id)
    if index is None or index.status != IndexStatus.done:
        return []
    stmt = select(TrackRecord).where(TrackRecord.video_id == video_id)
    if cls is not None:
        names = [cls] if isinstance(cls, str) else list(cls)
        stmt = stmt.where(TrackRecord.cls.in_(names))
    if t_from is not None:
        stmt = stmt.where(TrackRecord.t_out >= t_from)
    if t_to is not None:
        stmt = stmt.where(TrackRecord.t_in <= t_to)
    return list(session.scalars(stmt.order_by(TrackRecord.t_in, TrackRecord.track_no)))
