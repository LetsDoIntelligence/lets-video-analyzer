"""Attribute storage, filtering and the extractor hook in the indexing job."""

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.jobs.handlers import make_indexing_handler
from app.main import create_app
from app.models import JobKind, TrackRecord
from app.vision import store
from app.vision.attributes import run_extractors
from app.vision.pipeline import DetectionCancelled
from app.vision.tracker import Track

from .test_engine import make_track
from .test_indexing import MovingCarDetector, run_index


class Tagger:
    """Marks every track it is given with a fixed attribute value."""

    def __init__(self, name: str, value: str, classes: frozenset[str]) -> None:
        self.name, self.value, self.classes = name, value, classes
        self.seen: list[int] = []

    def extract(
        self, video_path: Path, tracks: Sequence[Track], *, should_cancel: Callable[[], bool]
    ) -> None:
        for t in tracks:
            self.seen.append(t.track_id)
            t.attrs[self.name] = self.value


class Broken:
    name = "broken"
    classes = frozenset({"car"})

    def extract(
        self, video_path: Path, tracks: Sequence[Track], *, should_cancel: Callable[[], bool]
    ) -> None:
        raise RuntimeError("network down")


def test_extractors_only_see_their_classes() -> None:
    tracks = [make_track(1, "car", 0, 2), make_track(2, "person", 0, 2)]
    colors = Tagger("color", "red", frozenset({"car"}))
    assert run_extractors([colors], Path("x.mp4"), tracks) == []
    assert colors.seen == [1]
    assert tracks[0].attrs == {"color": "red"}
    assert tracks[1].attrs == {}


def test_a_failing_extractor_does_not_stop_the_others() -> None:
    tracks = [make_track(1, "car", 0, 2)]
    ok = Tagger("color", "blue", frozenset({"car"}))
    failed = run_extractors([Broken(), ok], Path("x.mp4"), tracks)
    assert failed == ["broken"]
    assert tracks[0].attrs == {"color": "blue"}


def test_cancellation_propagates() -> None:
    tracks = [make_track(1, "car", 0, 2)]
    with pytest.raises(DetectionCancelled):
        run_extractors(
            [Tagger("color", "red", frozenset({"car"}))],
            Path("x.mp4"),
            tracks,
            should_cancel=lambda: True,
        )


def test_attributes_are_stored_and_filterable(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()["id"]
    red, blue = make_track(1, "car", 0, 3), make_track(2, "car", 5, 8)
    red.attrs["color"], blue.attrs["color"] = "red", "blue"
    plain = make_track(3, "car", 10, 12)  # no attributes: unknown, never matched
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        store.start_index(s, vid, {})
        store.save_index(s, vid, tracks=[red, blue, plain], frames=1, width=64, height=48)
        got = lambda **kw: [r.track_no for r in store.query_tracks(s, vid, **kw)]  # noqa: E731
        assert got() == [1, 2, 3]
        assert got(attrs={"color": "red"}) == [1]
        assert got(attrs={"color": "blue"}, t_from=4) == [2]
        assert got(attrs={"color": "green"}) == []
        assert store.query_tracks(s, vid)[0].attrs == {"color": "red"}


def test_index_params_change_with_extractors() -> None:
    from app.vision.tracker import TrackerConfig

    base = {"model": "m", "sample_fps": 5.0, "conf": 0.25, "tracker": TrackerConfig()}
    a = store.index_params(**base)  # type: ignore[arg-type]
    assert "attributes" not in a  # indexes from before attributes existed stay valid
    b = store.index_params(**base, attributes=["color"])  # type: ignore[arg-type]
    assert b["attributes"] == ["color"] and a != b


@pytest.fixture
def tagger() -> Tagger:
    return Tagger("color", "red", frozenset({"car"}))


@pytest.fixture
def client(settings: Settings, tagger: Tagger) -> Iterator[TestClient]:  # type: ignore[override]
    with TestClient(create_app(settings)) as c:
        c.app.state.jobs.handlers[JobKind.indexing] = make_indexing_handler(  # type: ignore[attr-defined]
            settings,
            c.app.state.session_factory,  # type: ignore[attr-defined]
            detector_factory=lambda: MovingCarDetector(),
            extractors=[tagger],
        )
        yield c


def test_indexing_job_runs_extractors_and_stores_attrs(  # type: ignore[no-untyped-def]
    client: TestClient, upload, tagger: Tagger
) -> None:
    vid = upload().json()["id"]
    assert run_index(client, vid)["status"] == "succeeded"
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        rows = list(s.scalars(select(TrackRecord)))
    assert [r.attrs for r in rows] == [{"color": "red"}]
    assert len(tagger.seen) == 1
