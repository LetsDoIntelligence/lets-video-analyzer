import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
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
