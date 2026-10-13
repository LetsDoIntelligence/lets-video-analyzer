"""Pluggable attribute extractors: add properties (color, helmet...) to finished tracks."""

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from app.vision.pipeline import DetectionCancelled
from app.vision.tracker import Track

logger = logging.getLogger("lets.attributes")


class AttributeExtractor(Protocol):
    """Looks at the video around each track and sets `track.attrs[self.name]`.

    It only receives tracks whose class is in `classes`. It may leave a track without the
    attribute when it can't tell (queries treat that as unknown, never as a guess). Long
    extractors should call `should_cancel()` and raise `DetectionCancelled` when it is true.
    """

    name: str
    classes: frozenset[str]

    def extract(
        self, video_path: Path, tracks: Sequence[Track], *, should_cancel: Callable[[], bool]
    ) -> None: ...


def run_extractors(
    extractors: Sequence[AttributeExtractor],
    video_path: Path,
    tracks: Sequence[Track],
    *,
    should_cancel: Callable[[], bool] = lambda: False,
) -> list[str]:
    """Run each extractor over the tracks it applies to; returns the names that failed.

    One failing extractor (say a network call) must not throw away the detections, so its
    error is logged and the others still run. Cancellation always propagates.
    """
    failed: list[str] = []
    for ex in extractors:
        if should_cancel():
            raise DetectionCancelled
        subset = [t for t in tracks if t.cls in ex.classes]
        if not subset:
            continue
        try:
            ex.extract(video_path, subset, should_cancel=should_cancel)
        except DetectionCancelled:
            raise
        except Exception:
            logger.exception("attribute extractor %r failed; continuing without it", ex.name)
            failed.append(ex.name)
    return failed
