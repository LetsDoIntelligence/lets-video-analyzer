from pathlib import Path

import pytest

from app.vision.detector import TRACKED_CLASSES, Detection, YoloDetector
from app.vision.pipeline import FrameDetections, detect_video
from app.vision.tracker import Tracker, TrackerConfig

ROOT = Path(__file__).resolve().parents[3]
WEIGHTS = ROOT / "ml" / "weights" / "yolo11s.pt"
REAL_VIDEO = ROOT / "test_video" / "Test Video.mp4"

FPS = 5.0


def det(x: float, y: float = 100, cls: str = "car", conf: float = 0.9) -> Detection:
    return Detection(TRACKED_CLASSES[cls], cls, conf, (x, y, x + 60, y + 40))


def frames(per_frame: list[list[Detection]]) -> list[FrameDetections]:
    return [FrameDetections(i, i / FPS, 640, 360, d) for i, d in enumerate(per_frame)]


def track_all(per_frame: list[list[Detection]], **cfg: float) -> list:  # type: ignore[type-arg]
    tracker = Tracker(FPS, TrackerConfig(**cfg))  # type: ignore[arg-type]
    for f in frames(per_frame):
        tracker.update(f)
    return tracker.finish()


def test_one_moving_object_is_one_track() -> None:
    tracks = track_all([[det(10 + 8 * i)] for i in range(20)])
    assert len(tracks) == 1
    assert len(tracks[0].points) == 20
    assert tracks[0].cls == "car"
    assert tracks[0].t_in == 0.0
    assert tracks[0].t_out == pytest.approx(19 / FPS)


def test_two_separate_objects_are_two_tracks() -> None:
    tracks = track_all([[det(10 + 8 * i, y=50), det(400 - 8 * i, y=250)] for i in range(20)])
    assert len(tracks) == 2
    assert tracks[0].track_id != tracks[1].track_id


def test_a_two_frame_blip_is_dropped_as_noise() -> None:
    per_frame = [[det(10 + 8 * i)] for i in range(20)]
    per_frame[5] += [det(500, y=300)]  # false positive that appears for two frames only
    per_frame[6] += [det(504, y=300)]
    assert len(track_all(per_frame)) == 1
    assert len(track_all(per_frame, min_hits=1)) == 2


def test_short_occlusion_keeps_the_same_track() -> None:
    per_frame: list[list[Detection]] = [[det(10 + 8 * i)] for i in range(20)]
    per_frame[8], per_frame[9] = [], []  # detector misses it for 2 frames
    tracks = track_all(per_frame)
    assert len(tracks) == 1
    assert len(tracks[0].points) == 18


def test_object_gone_for_long_is_a_new_track() -> None:
    first = [[det(10 + 4 * i)] for i in range(8)]
    gap: list[list[Detection]] = [[] for _ in range(20)]  # 4 s > lost_seconds (2 s)
    second = [[det(400 - 4 * i, y=250)] for i in range(8)]
    assert len(track_all(first + gap + second)) == 2


def test_class_is_decided_by_total_confidence() -> None:
    per_frame = [[det(10 + 8 * i, cls="car")] for i in range(10)]
    per_frame[4] = [det(10 + 8 * 4, cls="truck", conf=0.95)]  # one flickering frame
    tracks = track_all(per_frame)
    assert len(tracks) == 1
    assert tracks[0].cls == "car"


def test_empty_video_has_no_tracks() -> None:
    assert track_all([[] for _ in range(10)]) == []


@pytest.mark.skipif(
    not (WEIGHTS.exists() and REAL_VIDEO.exists()),
    reason="needs ml/weights/yolo11s.pt and test_video/Test Video.mp4",
)
def test_real_clip_yields_plausible_tracks() -> None:
    detector = YoloDetector(WEIGHTS)
    tracker = Tracker(FPS)
    for f in detect_video(REAL_VIDEO, detector, fps=FPS, end=30.0):
        tracker.update(f)
    tracks = tracker.finish()
    assert 5 <= len(tracks) <= 60
    assert len({t.track_id for t in tracks}) == len(tracks)
    assert all(len(t.points) >= 3 and t.t_in <= t.t_out for t in tracks)
    assert {t.cls for t in tracks} <= set(TRACKED_CLASSES)
    assert sum(t.cls == "car" for t in tracks) > len(tracks) / 2
