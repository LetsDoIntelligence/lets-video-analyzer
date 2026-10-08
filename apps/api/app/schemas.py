import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field
from pydantic.alias_generators import to_camel

from app.models import JobKind, JobStatus, VideoStatus


class CamelModel(BaseModel):
    """JSON uses camelCase to match the web client's types."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class VideoOut(CamelModel):
    id: str
    name: str
    filename: str
    size_bytes: int
    status: VideoStatus
    duration_sec: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    created_at: datetime
    thumbnail_path: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def src(self) -> str:
        """Path (relative to the API origin) the player loads the video from."""
        return f"/v1/videos/{self.id}/file"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def thumbnail_src(self) -> str | None:
        return f"/v1/videos/{self.id}/thumbnail" if self.thumbnail_path else None


class JobOut(CamelModel):
    id: str
    video_id: str
    kind: JobKind
    status: JobStatus
    progress: float
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobCreate(CamelModel):
    kind: JobKind
    # Rebuild the index even if one exists for the current settings (indexing jobs only).
    force: bool = False


class IndexState(enum.StrEnum):
    none = "none"  # never indexed
    queued = "queued"
    running = "running"
    ready = "ready"
    failed = "failed"


class IndexOut(CamelModel):
    """Where a video stands in detection + tracking, for the UI."""

    video_id: str
    state: IndexState
    progress: float = 0.0  # 0..1 while queued/running, 1 when ready
    job_id: str | None = None
    n_tracks: int | None = None
    error: str | None = None


class OverlayTrack(CamelModel):
    id: int
    cls: str
    points: list[list[float]]  # [t, x1, y1, x2, y2] in source pixels


class DetectionsOut(CamelModel):
    """Tracked boxes inside a time window, for drawing over the video."""

    video_id: str
    width: int
    height: int
    start: float
    end: float
    tracks: list[OverlayTrack]
