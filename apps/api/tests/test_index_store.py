from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import IndexStatus, TrackRecord, Video
from app.vision import store
from app.vision.tracker import Track, TrackerConfig

PARAMS = store.index_params(model="yolo11s.pt", sample_fps=5.0, conf=0.25, tracker=TrackerConfig())


def _session(client: TestClient) -> Session:
    return client.app.state.session_factory()  # type: ignore[attr-defined, no-any-return]


def _video(s: Session) -> Video:
    v = Video(name="Clip", filename="clip.mp4", stored_path="videos/x.mp4", size_bytes=10)
    s.add(v)
    s.commit()
    return v


def _track(track_id: int, cls: str, t0: float, t1: float, n: int = 4) -> Track:
    track = Track(track_id)
    for i in range(n):
        t = t0 + (t1 - t0) * i / (n - 1)
        track.add(t, (10.0 + i, 20.0, 70.0 + i, 60.0), 0.9, cls)
    return track


def test_migration_creates_index_tables(client: TestClient) -> None:
    names = set(inspect(client.app.state.engine).get_table_names())  # type: ignore[attr-defined]
    assert {"video_indexes", "tracks"} <= names


def test_save_and_query_round_trip(client: TestClient) -> None:
    with _session(client) as s:
        v = _video(s)
        store.start_index(s, v.id, PARAMS)
        store.save_index(
            s,
            v.id,
            tracks=[_track(1, "car", 0, 3), _track(2, "truck", 10, 14), _track(3, "car", 20, 25)],
            frames=125,
            width=1280,
            height=720,
        )
        index = store.get_index(s, v.id)
        assert index is not None
        assert index.status is IndexStatus.done
        assert (index.n_tracks, index.frames, index.frame_width) == (3, 125, 1280)
        assert index.finished_at is not None

        everything = store.query_tracks(s, v.id)
        assert [t.track_no for t in everything] == [1, 2, 3]
        first = everything[0]
        assert first.cls == "car"
        assert first.t_in == 0 and first.t_out == 3
        assert first.points[0] == [0.0, 10.0, 20.0, 70.0, 60.0, 0.9]
        assert len(first.points) == 4


def test_query_filters_by_class_and_overlapping_time(client: TestClient) -> None:
    with _session(client) as s:
        v = _video(s)
        store.start_index(s, v.id, PARAMS)
        tracks = [_track(1, "car", 0, 3), _track(2, "truck", 10, 14), _track(3, "car", 20, 25)]
        store.save_index(s, v.id, tracks=tracks, frames=1, width=1, height=1)

        assert [t.track_no for t in store.query_tracks(s, v.id, cls="car")] == [1, 3]
        assert [t.track_no for t in store.query_tracks(s, v.id, cls=["car", "truck"])] == [1, 2, 3]
        # Overlap, not containment: a track partly inside the window counts.
        assert [t.track_no for t in store.query_tracks(s, v.id, t_from=2, t_to=11)] == [1, 2]
        assert [t.track_no for t in store.query_tracks(s, v.id, t_from=4, t_to=9)] == []
        assert [t.track_no for t in store.query_tracks(s, v.id, t_from=24)] == [3]


def test_unfinished_or_failed_index_is_not_queryable(client: TestClient) -> None:
    with _session(client) as s:
        v = _video(s)
        assert store.query_tracks(s, v.id) == []
        store.start_index(s, v.id, PARAMS)
        assert store.query_tracks(s, v.id) == []
        store.fail_index(s, v.id, "GPU out of memory")
        index = store.get_index(s, v.id)
        assert index is not None
        assert index.status is IndexStatus.failed
        assert index.error == "GPU out of memory"
        assert store.query_tracks(s, v.id) == []


def test_is_current_reuses_index_only_when_params_match(client: TestClient) -> None:
    with _session(client) as s:
        v = _video(s)
        assert not store.is_current(s, v.id, PARAMS)
        store.start_index(s, v.id, PARAMS)
        assert not store.is_current(s, v.id, PARAMS)  # still running
        store.save_index(s, v.id, tracks=[], frames=0, width=None, height=None)
        assert store.is_current(s, v.id, PARAMS)

        other = store.index_params(
            model="yolo11s.pt", sample_fps=10.0, conf=0.25, tracker=TrackerConfig()
        )
        assert not store.is_current(s, v.id, other)
        tuned = store.index_params(
            model="yolo11s.pt",
            sample_fps=5.0,
            conf=0.25,
            tracker=TrackerConfig(match_thresh=0.9),
        )
        assert not store.is_current(s, v.id, tuned)


def test_reindex_replaces_old_tracks(client: TestClient) -> None:
    with _session(client) as s:
        v = _video(s)
        store.start_index(s, v.id, PARAMS)
        store.save_index(s, v.id, tracks=[_track(1, "car", 0, 3)], frames=1, width=1, height=1)
        store.start_index(s, v.id, PARAMS)
        assert s.scalars(select(TrackRecord)).all() == []  # cleared as soon as indexing restarts
        store.save_index(s, v.id, tracks=[_track(7, "bus", 1, 4)], frames=1, width=1, height=1)
        assert [(t.track_no, t.cls) for t in store.query_tracks(s, v.id)] == [(7, "bus")]


def test_deleting_the_video_removes_its_index_and_tracks(client: TestClient) -> None:
    with _session(client) as s:
        v = _video(s)
        store.start_index(s, v.id, PARAMS)
        store.save_index(s, v.id, tracks=[_track(1, "car", 0, 3)], frames=1, width=1, height=1)
        s.delete(v)
        s.commit()
        assert s.scalars(select(TrackRecord)).all() == []
        assert store.get_index(s, v.id) is None
