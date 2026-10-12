"""Name the dominant color of each tracked vehicle (local, no model, no API).

Each track gets a few of its best crops (large and confidently detected). The middle of each
crop is classified pixel by pixel into a small named palette using hue/saturation/brightness,
the most common name wins per crop, and the crops vote for the track.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from app.vision.frames import sample_frames
from app.vision.pipeline import DetectionCancelled
from app.vision.tracker import Track

PALETTE = ("white", "black", "gray", "red", "orange", "yellow", "green", "blue")
COLORS = ("red", "orange", "yellow", "green", "blue")
VEHICLES = frozenset({"car", "truck", "bus", "motorcycle"})

MIN_SIDE = 12  # px; smaller crops are too coarse to judge
MIN_SHARE = 0.35  # the winning color must cover at least this share of the crop
GRAY_YIELDS = 0.25  # a chromatic color with at least this share outranks gray
BLACK_WINS = 0.6  # black is the answer only when it covers at least this share
# Hue bands in degrees: (upper bound, name). Everything from 345 up wraps back to red.
_HUES = ((15.0, "red"), (45.0, "orange"), (70.0, "yellow"), (170.0, "green"), (300.0, "blue"))


def _hsv(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hue (degrees), saturation and value (0..1) for every pixel, without OpenCV."""
    px = bgr.reshape(-1, 3).astype(np.float32) / 255.0
    b, g, r = px[:, 0], px[:, 1], px[:, 2]
    v = px.max(axis=1)
    c = v - px.min(axis=1)
    s = np.divide(c, v, out=np.zeros_like(v), where=v > 0)
    h = np.zeros_like(v)
    nz = c > 1e-6
    rm = nz & (v == r)
    gm = nz & ~rm & (v == g)
    bm = nz & ~rm & ~gm
    h[rm] = ((g[rm] - b[rm]) / c[rm]) % 6
    h[gm] = (b[gm] - r[gm]) / c[gm] + 2
    h[bm] = (r[bm] - g[bm]) / c[bm] + 4
    return h * 60.0, s, v


def classify_pixels(bgr: np.ndarray) -> Counter[str]:
    """How many pixels of the image fall into each palette color."""
    h, s, v = _hsv(bgr)
    names = np.full(h.shape, "", dtype="<U6")
    dark = v < 0.25
    grey = ~dark & ((s < 0.30) | ((s < 0.40) & (v < 0.6)))
    names[dark] = "black"
    names[grey & (v > 0.72)] = "white"
    names[grey & (v < 0.30)] = "black"
    names[grey & (names == "")] = "gray"
    colored = names == ""
    lo = 0.0
    for upper, name in _HUES:
        names[colored & (h >= lo) & (h < upper)] = name
        lo = upper
    names[colored & (h >= 345.0)] = "red"
    names[colored & (h >= 300.0) & (h < 345.0)] = "red"  # magenta / pink reads as red
    return Counter(names.tolist())


def dominant_color(crop: np.ndarray) -> tuple[str, float] | None:
    """(color name, share of the crop it covers), or None when the crop can't be judged."""
    h, w = crop.shape[:2]
    if min(h, w) < MIN_SIDE:
        return None
    inner = crop[int(h * 0.3) : int(h * 0.9), int(w * 0.2) : int(w * 0.8)]
    if inner.size == 0:
        return None
    counts = classify_pixels(inner)
    total = sum(counts.values())
    # Windshields, tires and shadows are dark on every car, so black only wins when it is
    # nearly everything; otherwise the body color is the most common non-black one.
    if counts["black"] < BLACK_WINS * total:
        counts.pop("black", None)
        total = sum(counts.values())
        if total == 0:
            return None
    name, n = counts.most_common(1)[0]
    if name == "gray":
        # Shaded paint, bumpers and road all read as dull gray, so a real color that covers a
        # fair part of the body beats it.
        tint, m = max(((c, counts[c]) for c in COLORS), key=lambda cn: cn[1])
        if m >= GRAY_YIELDS * total:
            name, n = tint, m
    share = n / total
    return (name, share) if share >= MIN_SHARE else None


def vote(results: Sequence[tuple[str, float]]) -> str | None:
    """Combine per-crop (color, weight) results into one answer for the track."""
    if not results:
        return None
    totals: dict[str, float] = {}
    for name, weight in results:
        totals[name] = totals.get(name, 0.0) + weight
    return max(totals, key=lambda n: totals[n])


class ColorExtractor:
    """Attribute extractor: sets `attrs["color"]` on vehicle tracks."""

    name = "color"
    classes = VEHICLES

    def __init__(self, sample_fps: float, crops_per_track: int = 3) -> None:
        self.sample_fps = sample_fps
        self.crops_per_track = crops_per_track

    def extract(
        self, video_path: Path, tracks: Sequence[Track], *, should_cancel: Callable[[], bool]
    ) -> None:
        # time (rounded as stored) -> [(track index, box, weight)]
        wanted: dict[float, list[tuple[int, tuple[float, float, float, float], float]]] = {}
        for i, tr in enumerate(tracks):
            best = sorted(
                tr.points,
                key=lambda p: (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]) * p.conf,
                reverse=True,
            )[: self.crops_per_track]
            for p in best:
                area = (p.box[2] - p.box[0]) * (p.box[3] - p.box[1])
                wanted.setdefault(round(p.t, 3), []).append((i, p.box, area * p.conf))
        if not wanted:
            return
        last = max(wanted)
        found: dict[int, list[tuple[str, float]]] = {}
        for frame in sample_frames(video_path, self.sample_fps):
            if should_cancel():
                raise DetectionCancelled
            if frame.t > last + 1e-3:
                break
            for i, box, weight in wanted.get(round(frame.t, 3), ()):
                x1, y1, x2, y2 = box
                height, width = frame.image.shape[:2]
                crop = frame.image[
                    max(int(y1), 0) : min(int(y2) + 1, height),
                    max(int(x1), 0) : min(int(x2) + 1, width),
                ]
                res = dominant_color(crop)
                if res is not None:
                    found.setdefault(i, []).append((res[0], weight * res[1]))
        for i, results in found.items():
            color = vote(results)
            if color is not None:
                tracks[i].attrs["color"] = color
