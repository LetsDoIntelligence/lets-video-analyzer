from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from app.vision.detector import TRACKED_CLASSES, Detection, YoloDetector
from app.vision.frames import sample_frames
from app.vision.pipeline import DetectionCancelled, detect_video

ROOT = Path(__file__).resolve().parents[3]
WEIGHTS = ROOT / "ml" / "weights" / "yolo11s.pt"
REAL_VIDEO = ROOT / "test_video" / "Test Video.mp4"


class FakeDetector:
    """Returns one 'car' per image and records the batch sizes it was given."""

    def __init__(self) -> None:
        self.batches: list[int] = []

    def detect(self, images: Sequence[np.ndarray]) -> list[list[Detection]]:
        self.batches.append(len(images))
        return [[Detection(2, "car", 0.9, (1.0, 2.0, 3.0, 4.0))] for _ in images]


def test_sample_frames_rate_and_layout(make_video) -> None:  # type: ignore[no-untyped-def]
    path = make_video(seconds=3, fps=10, size=(64, 48))
    frames = list(sample_frames(path, fps=2))
    assert [f.index for f in frames] == list(range(len(frames)))
    assert 6 <= len(frames) <= 7
    assert frames[0].t == pytest.approx(0.0, abs=0.01)
    gaps = [b.t - a.t for a, b in zip(frames, frames[1:], strict=False)]
    assert all(0.4 <= g <= 0.6 for g in gaps)
    assert frames[0].image.shape == (48, 64, 3)
    assert frames[0].image.dtype == np.uint8


def test_sample_frames_never_duplicates_a_slow_source(make_video) -> None:  # type: ignore[no-untyped-def]
    path = make_video(seconds=2, fps=10)
    frames = list(sample_frames(path, fps=30))  # faster than the 10 fps source
    assert len(frames) == 20
    assert len({f.t for f in frames}) == 20


def test_sample_frames_window(make_video) -> None:  # type: ignore[no-untyped-def]
    path = make_video(seconds=4, fps=10)
    frames = list(sample_frames(path, fps=2, start=1.0, end=3.0))
    times = [f.t for f in frames]
    assert times[0] >= 0.99
    assert max(times) < 3.0
    assert len(frames) == 4


def test_sample_frames_rejects_bad_fps(make_video) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        list(sample_frames(make_video(), fps=0))


def test_detect_video_batches_and_orders(make_video) -> None:  # type: ignore[no-untyped-def]
    path = make_video(seconds=2, fps=10)  # 20 frames
    fake = FakeDetector()
    out = list(detect_video(path, fake, fps=10, batch_size=8))
    assert fake.batches == [8, 8, 4]
    assert [o.index for o in out] == list(range(20))
    assert all(a.t < b.t for a, b in zip(out, out[1:], strict=False))
    assert (out[0].width, out[0].height) == (64, 48)
    assert out[0].detections[0].cls == "car"


def test_detect_video_cancels_between_batches(make_video) -> None:  # type: ignore[no-untyped-def]
    path = make_video(seconds=2, fps=10)
    fake = FakeDetector()
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 1  # allow the first batch, stop before the second

    with pytest.raises(DetectionCancelled):
        list(detect_video(path, fake, fps=10, batch_size=8, should_cancel=cancel))
    assert fake.batches == [8]


@pytest.mark.skipif(
    not (WEIGHTS.exists() and REAL_VIDEO.exists()),
    reason="needs ml/weights/yolo11s.pt and test_video/Test Video.mp4",
)
def test_yolo_finds_vehicles_in_the_real_clip() -> None:
    detector = YoloDetector(WEIGHTS)
    frames = list(detect_video(REAL_VIDEO, detector, fps=2, batch_size=8, end=10.0))
    assert len(frames) >= 19
    found = {d.cls for f in frames for d in f.detections}
    assert found <= set(TRACKED_CLASSES)
    assert found & {"car", "truck", "bus", "motorcycle"}, f"no vehicles found, saw {found}"
    for f in frames:
        for d in f.detections:
            x1, y1, x2, y2 = d.box
            assert 0 <= x1 < x2 <= f.width + 1 and 0 <= y1 < y2 <= f.height + 1
            assert 0.25 <= d.conf <= 1.0
