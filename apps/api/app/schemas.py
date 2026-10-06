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
