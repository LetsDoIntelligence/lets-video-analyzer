"""Multi-object tracking: turn per-frame detections into tracks with stable ids (ByteTrack)."""

from collections import defaultdict
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import numpy as np

from app.vision.detector import Detection
from app.vision.pipeline import FrameDetections


@dataclass(frozen=True)
class TrackerConfig:
    """ByteTrack settings. Frame counts are derived from seconds, since we track a *sampled*
    stream (e.g. 5 fps) and the same object moves much further between sampled frames."""

    high_thresh: float = 0.25  # detections above this are matched first
    low_thresh: float = 0.1  # weaker detections can still extend an existing track
    new_track_thresh: float = 0.3  # a new track needs at least this confident a detection
    match_thresh: float = 0.8  # association cost limit (1 - IoU); higher = more permissive
    lost_seconds: float = 2.0  # how long a track survives without a detection
    min_hits: int = 3  # tracks seen in fewer sampled frames are discarded as noise


@dataclass
class TrackPoint:
    t: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels
    conf: float


@dataclass
class Track:
    track_id: int
    points: list[TrackPoint] = field(default_factory=list)
    _cls_conf: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    attrs: dict[str, str] = field(default_factory=dict)  # filled by attribute extractors

    def add(self, t: float, box: tuple[float, float, float, float], conf: float, cls: str) -> None:
        self.points.append(TrackPoint(t, box, conf))
        self._cls_conf[cls] += conf

    @property
    def cls(self) -> str:
        """Class by total confidence, so one frame that flickers car->truck doesn't relabel it."""
        return max(self._cls_conf.items(), key=lambda kv: kv[1])[0]

    @property
    def t_in(self) -> float:
        return self.points[0].t

    @property
    def t_out(self) -> float:
        return self.points[-1].t

    @property
    def confidence(self) -> float:
        return sum(p.conf for p in self.points) / len(self.points)


class _Dets:
    """The small slice of Ultralytics' `Boxes` interface that ByteTrack reads."""

    def __init__(self, xywh: np.ndarray, conf: np.ndarray, cls: np.ndarray) -> None:
        self.xywh, self.conf, self.cls = xywh, conf, cls

    def __len__(self) -> int:
        return len(self.conf)

    def __getitem__(self, mask: np.ndarray) -> "_Dets":
        return _Dets(self.xywh[mask], self.conf[mask], self.cls[mask])


def _to_dets(detections: list[Detection]) -> _Dets:
    if not detections:
        return _Dets(np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, np.float32))
    box = np.array([d.box for d in detections], dtype=np.float32)
    xywh = np.stack(
        [
            (box[:, 0] + box[:, 2]) / 2,
            (box[:, 1] + box[:, 3]) / 2,
            box[:, 2] - box[:, 0],
            box[:, 3] - box[:, 1],
        ],
        axis=1,
    )
    conf = np.array([d.conf for d in detections], dtype=np.float32)
    cls = np.array([d.cls_id for d in detections], dtype=np.float32)
    return _Dets(xywh, conf, cls)


class Tracker:
    """Feed frames in time order with `update`, then call `finish` for the tracks.

    Note: Ultralytics keeps the track-id counter global, so run one Tracker at a time
    (the indexing job runner is single-threaded).
    """

    def __init__(self, fps: float, config: TrackerConfig | None = None) -> None:
        from ultralytics.trackers.byte_tracker import BYTETracker

        self._config = config or TrackerConfig()
        args = SimpleNamespace(
            track_high_thresh=self._config.high_thresh,
            track_low_thresh=self._config.low_thresh,
            new_track_thresh=self._config.new_track_thresh,
            track_buffer=max(1, round(self._config.lost_seconds * fps)),
            match_thresh=self._config.match_thresh,
            fuse_score=True,
        )
        self._tracker: Any = BYTETracker(args)  # type: ignore[no-untyped-call]
        self._names: dict[int, str] = {}
        self._tracks: dict[int, Track] = {}

    def update(self, frame: FrameDetections) -> None:
        for det in frame.detections:
            self._names[det.cls_id] = det.cls
        # Always call update, even with no detections, so lost tracks age out correctly.
        rows = self._tracker.update(_to_dets(frame.detections))
        for row in rows:
            x1, y1, x2, y2, track_id, conf, cls_id = (float(v) for v in row[:7])
            track = self._tracks.setdefault(int(track_id), Track(int(track_id)))
            track.add(frame.t, (x1, y1, x2, y2), conf, self._names[int(cls_id)])

    def finish(self) -> list[Track]:
        """Tracks seen in at least `min_hits` sampled frames, ordered by first appearance."""
        kept = [t for t in self._tracks.values() if len(t.points) >= self._config.min_hits]
        return sorted(kept, key=lambda t: (t.t_in, t.track_id))
