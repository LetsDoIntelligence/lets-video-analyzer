import threading
import time
from collections.abc import Iterator, Sequence
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.jobs.handlers import make_indexing_handler
from app.main import create_app
from app.models import JobKind, TrackRecord
from app.vision.detector import Detection

from .test_jobs import wait_for


class MovingCarDetector:
    """Reports one car that drifts right a little on every frame it is shown.

    `error` makes it raise; `gate` makes it wait (so a test can act while a job is running).
    """

    def __init__(self) -> None:
        self.frames = 0
        self.calls = 0
        self.error: Exception | None = None
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def detect(self, images: Sequence[np.ndarray]) -> list[list[Detection]]:
        self.calls += 1
        self.started.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.error is not None:
            raise self.error
        out = []
        for _ in images:
            x = 4.0 * self.frames
            self.frames += 1
            out.append([Detection(2, "car", 0.9, (x, 10.0, x + 20.0, 30.0))])
        return out


@pytest.fixture
def detector() -> MovingCarDetector:
    return MovingCarDetector()


@pytest.fixture
def client(settings: Settings, detector: MovingCarDetector) -> Iterator[TestClient]:  # type: ignore[override]
    """The app with the real indexing handler, driven by a fake detector (no GPU needed)."""
    with TestClient(create_app(settings)) as c:
        c.app.state.jobs.handlers[JobKind.indexing] = make_indexing_handler(  # type: ignore[attr-defined]
            settings,
            c.app.state.session_factory,  # type: ignore[attr-defined]
            detector_factory=lambda: detector,
        )
        yield c


def index_of(client: TestClient, video_id: str) -> dict[str, Any]:
    res = client.get(f"/v1/videos/{video_id}/index")
    assert res.status_code == 200
    return res.json()  # type: ignore[no-any-return]


def run_index(client: TestClient, video_id: str, **body: object) -> dict[str, Any]:
    res = client.post(f"/v1/videos/{video_id}/jobs", json={"kind": "indexing", **body})
    assert res.status_code in (200, 202), res.text
    return wait_for(client, res.json()["id"])  # type: ignore[no-any-return]


def test_a_new_video_has_no_index(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()["id"]
    assert index_of(client, vid) == {
        "videoId": vid,
        "state": "none",
        "progress": 0.0,
        "jobId": None,
        "nTracks": None,
        "error": None,
    }


def test_index_for_unknown_video_is_404(client: TestClient) -> None:
    assert client.get("/v1/videos/nope/index").status_code == 404


def test_indexing_job_detects_tracks_and_stores_them(  # type: ignore[no-untyped-def]
    client: TestClient, upload, detector: MovingCarDetector
) -> None:
    vid = upload().json()["id"]  # 2 s at 10 fps; sampled at 5 fps -> 10 frames
    job = run_index(client, vid)
    assert job["status"] == "succeeded"
    assert job["progress"] == 1.0

    state = index_of(client, vid)
    assert state["state"] == "ready"
    assert state["nTracks"] == 1
    assert state["progress"] == 1.0
    assert state["jobId"] == job["id"]

    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        tracks = list(s.scalars(select(TrackRecord)))
    assert [(t.cls, len(t.points)) for t in tracks] == [("car", 10)]
    assert detector.frames == 10


def test_a_current_index_is_reused(client: TestClient, upload, detector: MovingCarDetector) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()["id"]
    run_index(client, vid)
    calls = detector.calls
    again = run_index(client, vid)
    assert again["status"] == "succeeded"
    assert detector.calls == calls  # nothing was re-detected
    assert index_of(client, vid)["state"] == "ready"


def test_force_rebuilds_the_index(client: TestClient, upload, detector: MovingCarDetector) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()["id"]
    run_index(client, vid)
    calls = detector.calls
    run_index(client, vid, force=True)
    assert detector.calls > calls
    state = index_of(client, vid)
    assert (state["state"], state["nTracks"]) == ("ready", 1)


def test_upload_starts_indexing_automatically(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    client.app.state.settings.auto_index = True  # type: ignore[attr-defined]
    vid = upload().json()["id"]
    deadline = time.monotonic() + 5
    while index_of(client, vid)["state"] != "ready":
        assert time.monotonic() < deadline, index_of(client, vid)
        time.sleep(0.02)


def test_a_failure_is_reported_with_its_reason(  # type: ignore[no-untyped-def]
    client: TestClient, upload, detector: MovingCarDetector
) -> None:
    detector.error = RuntimeError("CUDA out of memory")
    vid = upload().json()["id"]
    assert run_index(client, vid)["status"] == "failed"
    state = index_of(client, vid)
    assert state["state"] == "failed"
    assert "CUDA out of memory" in state["error"]

    # Retrying after the cause is fixed works, and the failed attempt left nothing behind.
    detector.error = None
    assert run_index(client, vid)["status"] == "succeeded"
    assert index_of(client, vid)["state"] == "ready"


def test_a_missing_model_fails_the_job_clearly(settings: Settings, upload) -> None:  # type: ignore[no-untyped-def]
    # Real handler with real (missing) weights: the job fails with an actionable message.
    settings.detect_weights = settings.data_dir / "nope" / "yolo11s.pt"
    with TestClient(create_app(settings)) as client:
        c_upload = client.post(
            "/v1/videos",
            files={"file": ("a.mp4", _tiny_mp4(settings), "video/mp4")},
        )
        vid = c_upload.json()["id"]
        client.app.state.jobs.handlers[JobKind.indexing] = make_indexing_handler(  # type: ignore[attr-defined]
            settings,
            client.app.state.session_factory,  # type: ignore[attr-defined]
        )
        assert run_index(client, vid)["status"] == "failed"
        error = index_of(client, vid)["error"]
        assert "weights not found" in error


def _tiny_mp4(settings: Settings) -> bytes:
    from .conftest import write_test_video

    path = settings.data_dir / "tiny.mp4"
    write_test_video(path)
    return path.read_bytes()


def test_cancelling_stops_indexing_and_leaves_no_index(  # type: ignore[no-untyped-def]
    client: TestClient, upload, detector: MovingCarDetector
) -> None:
    detector.gate = threading.Event()
    vid = upload().json()["id"]
    job = client.post(f"/v1/videos/{vid}/jobs", json={"kind": "indexing"}).json()
    assert detector.started.wait(5)
    assert index_of(client, vid)["state"] == "running"

    assert client.post(f"/v1/jobs/{job['id']}/cancel").status_code == 202
    detector.gate.set()
    assert wait_for(client, job["id"])["status"] == "cancelled"

    state = index_of(client, vid)
    assert state["state"] == "failed"
    assert "cancelled" in state["error"]
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        assert s.scalars(select(TrackRecord)).all() == []
