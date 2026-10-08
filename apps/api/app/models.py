import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class VideoStatus(enum.StrEnum):
    uploaded = "uploaded"  # file stored, not yet probed
    ready = "ready"  # probed and playable
    failed = "failed"  # unreadable / unsupported


class JobKind(enum.StrEnum):
    probe = "probe"
    indexing = "indexing"  # detection + tracking (Phase 3)


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class IndexStatus(enum.StrEnum):
    running = "running"
    done = "done"
    failed = "failed"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))  # original upload name
    stored_path: Mapped[str] = mapped_column(String(512))  # relative to the data dir
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False, length=20), default=VideoStatus.uploaded
    )
    duration_sec: Mapped[float | None] = mapped_column(Float)
    fps: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    codec: Mapped[str | None] = mapped_column(String(50))
    thumbnail_path: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_video_kind", "video_id", "kind"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    kind: Mapped[JobKind] = mapped_column(Enum(JobKind, native_enum=False, length=20))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=20), default=JobStatus.queued
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    video: Mapped[Video] = relationship(back_populates="jobs")


class VideoIndex(Base):
    """State of the detection/tracking index for one video (one row per video).

    params records what produced the tracks (model, sampling rate, tracker settings), so an
    index is reused only while those still match and rebuilt when they change.
    """

    __tablename__ = "video_indexes"

    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus, native_enum=False, length=20), default=IndexStatus.running
    )
    params: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    frames: Mapped[int] = mapped_column(Integer, default=0)  # sampled frames processed
    frame_width: Mapped[int | None] = mapped_column(Integer)
    frame_height: Mapped[int | None] = mapped_column(Integer)
    n_tracks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrackRecord(Base):
    """One tracked object: what it is, when it was on screen, and where (sparse boxes)."""

    __tablename__ = "tracks"
    __table_args__ = (Index("ix_tracks_video_cls_tin", "video_id", "cls", "t_in"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    track_no: Mapped[int] = mapped_column(Integer)  # id assigned by the tracker
    cls: Mapped[str] = mapped_column(String(32))
    t_in: Mapped[float] = mapped_column(Float)  # first seen (seconds)
    t_out: Mapped[float] = mapped_column(Float)  # last seen (seconds)
    confidence: Mapped[float] = mapped_column(Float)  # mean detection confidence
    # [[t, x1, y1, x2, y2, conf], ...] in source pixels, one entry per sampled frame.
    points: Mapped[list[list[float]]] = mapped_column(JSON)
