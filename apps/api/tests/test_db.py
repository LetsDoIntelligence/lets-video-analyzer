from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import Job, JobKind, JobStatus, Video, VideoStatus


def _session(client: TestClient) -> Session:
    return client.app.state.session_factory()  # type: ignore[attr-defined, no-any-return]


def test_migration_creates_tables(client: TestClient) -> None:
    names = set(inspect(client.app.state.engine).get_table_names())  # type: ignore[attr-defined]
    assert {"videos", "jobs", "alembic_version"} <= names


def test_video_defaults(client: TestClient) -> None:
    with _session(client) as s:
        v = Video(name="Clip", filename="clip.mp4", stored_path="videos/x.mp4", size_bytes=10)
        s.add(v)
        s.commit()
        assert len(v.id) == 32
        assert v.status is VideoStatus.uploaded
        assert v.created_at is not None


def test_deleting_video_cascades_to_jobs(client: TestClient) -> None:
    with _session(client) as s:
        v = Video(name="Clip", filename="clip.mp4", stored_path="videos/x.mp4", size_bytes=10)
        v.jobs.append(Job(kind=JobKind.indexing))
        s.add(v)
        s.commit()
        job = s.scalars(select(Job)).one()
        assert job.status is JobStatus.queued
        assert job.progress == 0.0

        s.delete(v)
        s.commit()
        assert s.scalars(select(Job)).all() == []
