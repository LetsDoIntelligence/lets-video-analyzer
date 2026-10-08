"""Run a detector over a video: sample frames, batch them, yield per-frame detections."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from app.vision.detector import Detection, Detector
from app.vision.frames import SampledFrame, sample_frames


class DetectionCancelled(Exception):
    """Raised between batches when the caller asked to stop."""


@dataclass(frozen=True)
class FrameDetections:
    index: int
    t: float
    width: int
    height: int
    detections: list[Detection]


def detect_video(
    path: Path,
    detector: Detector,
    *,
    fps: float = 5.0,
    batch_size: int = 8,
    start: float = 0.0,
    end: float | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[FrameDetections]:
    """Yield detections for each sampled frame, in time order.

    Frames are decoded lazily and sent to the detector `batch_size` at a time, so memory stays
    bounded however long the video is. `should_cancel` is checked before every batch.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    batch: list[SampledFrame] = []

    def flush() -> Iterator[FrameDetections]:
        if should_cancel is not None and should_cancel():
            raise DetectionCancelled
        results = detector.detect([f.image for f in batch])
        for frame, dets in zip(batch, results, strict=True):
            height, width = frame.image.shape[:2]
            yield FrameDetections(frame.index, frame.t, width, height, dets)
        batch.clear()

    for frame in sample_frames(path, fps, start=start, end=end):
        batch.append(frame)
        if len(batch) >= batch_size:
            yield from flush()
    if batch:
        yield from flush()
