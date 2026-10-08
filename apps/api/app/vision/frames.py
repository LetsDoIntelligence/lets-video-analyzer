"""Decode a video and yield frames at a fixed sampling rate."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np


@dataclass(frozen=True)
class SampledFrame:
    index: int  # position among the sampled frames (0, 1, 2, ...)
    t: float  # presentation time in seconds
    image: np.ndarray  # BGR, HxWx3, uint8 (the layout Ultralytics expects for arrays)


def sample_frames(
    path: Path, fps: float, *, start: float = 0.0, end: float | None = None
) -> Iterator[SampledFrame]:
    """Yield about `fps` frames per second from `start` up to (excluding) `end` seconds.

    Each source frame is yielded at most once, so a source slower than `fps` is not duplicated.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    step = 1.0 / fps
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if start > 0:
            # Jump to the keyframe before `start`; earlier frames are skipped below.
            container.seek(int(start / stream.time_base), stream=stream, backward=True)
        next_t = start
        index = 0
        for frame in container.decode(stream):
            t = frame.time
            if t is None:
                continue
            if end is not None and t >= end:
                break
            if t + 1e-6 < next_t:
                continue
            yield SampledFrame(index=index, t=float(t), image=frame.to_ndarray(format="bgr24"))
            index += 1
            while next_t <= t + 1e-6:
                next_t += step
