"""Job handlers."""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Generic, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.jobs.runner import Handler, JobCancelled, JobContext
from app.models import JobKind, SearchStatus, Video
from app.storage import resolve_inside
from app.vision import store
from app.vision.attributes import AttributeExtractor, run_extractors
from app.vision.color import ColorExtractor
from app.vision.detector import Detector, TermDetector, WorldDetector, YoloDetector
from app.vision.helmet import HelmetExtractor, OpenAIHelmetClassifier
from app.vision.pipeline import DetectionCancelled, detect_video
from app.vision.tracker import Tracker, TrackerConfig

logger = logging.getLogger("lets.indexing")

DetectorFactory = Callable[[], Detector]
TermDetectorFactory = Callable[[], TermDetector]


def make_stub_indexing(steps: int, step_seconds: float) -> Handler:
    """Placeholder that only reports progress (used in tests and for demos without a GPU)."""

    def handler(ctx: JobContext) -> None:
        for i in range(steps):
            time.sleep(step_seconds)
            ctx.report((i + 1) / steps)

    return handler


T = TypeVar("T")


class _LazyDetector(Generic[T]):
    """Loads the YOLO model on first use and keeps it for every later job (it is slow to load
    and holds GPU memory, so one copy is shared by the single worker thread)."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._detector: T | None = None
        self._lock = threading.Lock()

    def get(self) -> T:
        with self._lock:
            if self._detector is None:
                self._detector = self._factory()
            return self._detector


def make_indexing_handler(
    settings: Settings,
    sessions: sessionmaker[Session],
    detector_factory: DetectorFactory | None = None,
    tracker_config: TrackerConfig | None = None,
    extractors: Sequence[AttributeExtractor] = (),
) -> Handler:
    """Detect and track every object in a video, then store the tracks (see app.vision).

    Skips the work when the video already has an index built with the current settings.
    """
    tracker_config = tracker_config or TrackerConfig()
    detector = _LazyDetector(
        detector_factory
        or (
            lambda: YoloDetector(
                settings.detect_weights, device=settings.detect_device, conf=settings.detect_conf
            )
        )
    )
    params = store.index_params(
        model=settings.detect_weights.name,
        sample_fps=settings.detect_fps,
        conf=settings.detect_conf,
        tracker=tracker_config,
        attributes=[e.name for e in extractors],
    )

    def handler(ctx: JobContext) -> None:
        with sessions() as session:
            video = session.get(Video, ctx.video_id)
            if video is None:
                raise LookupError("Video not found.")
            path = resolve_inside(settings.data_dir, video.stored_path)
            duration = video.duration_sec or 0.0

            if store.is_current(session, ctx.video_id, params):
                logger.info("video %s already indexed with these settings", ctx.video_id)
                return

            model = detector.get()  # may raise (missing weights / ultralytics): job fails clearly
            store.start_index(session, ctx.video_id, params)
            try:
                tracker = Tracker(settings.detect_fps, tracker_config)
                frames, width, height, last_reported = 0, None, None, -1.0
                for fd in detect_video(
                    path,
                    model,
                    fps=settings.detect_fps,
                    batch_size=settings.detect_batch_size,
                    should_cancel=lambda: ctx.cancelled,
                ):
                    tracker.update(fd)
                    frames, width, height = frames + 1, fd.width, fd.height
                    progress = min(fd.t / duration, 0.99) if duration else 0.0
                    if progress - last_reported >= 0.01:  # at most ~100 DB writes per video
                        ctx.report(progress)
                        last_reported = progress
                ctx.checkpoint()
                tracks = tracker.finish()
                failed = run_extractors(
                    extractors, path, tracks, should_cancel=lambda: ctx.cancelled
                )
                if failed:
                    logger.warning("video %s: attributes missing (%s)", ctx.video_id, failed)
                store.save_index(
                    session, ctx.video_id, tracks=tracks, frames=frames, width=width, height=height
                )
                logger.info(
                    "video %s indexed: %d frames, %d tracks", ctx.video_id, frames, len(tracks)
                )
            except (JobCancelled, DetectionCancelled):
                store.fail_index(session, ctx.video_id, "Indexing was cancelled.")
                raise JobCancelled from None
            except Exception as e:
                session.rollback()
                store.fail_index(session, ctx.video_id, str(e)[:500] or e.__class__.__name__)
                raise

    return handler


# Things searched for on request are mostly static and scored low, so be more forgiving.
SEARCH_TRACKER = TrackerConfig(
    high_thresh=0.15, low_thresh=0.05, new_track_thresh=0.2, min_hits=2, lost_seconds=3.0
)


def make_search_handler(
    settings: Settings,
    sessions: sessionmaker[Session],
    detector_factory: TermDetectorFactory | None = None,
) -> Handler:
    """Search a video for the terms users asked about that the fixed detector lacks.

    Every pending term of the video is searched in one pass over the footage; terms asked for
    while the job runs are picked up by the next pass.
    """
    detector = _LazyDetector(
        detector_factory
        or (
            lambda: WorldDetector(
                settings.search_weights, device=settings.detect_device, conf=settings.search_conf
            )
        )
    )

    def handler(ctx: JobContext) -> None:
        with sessions() as session:
            video = session.get(Video, ctx.video_id)
            if video is None:
                raise LookupError("Video not found.")
            path = resolve_inside(settings.data_dir, video.stored_path)
            duration = video.duration_sec or 0.0

            while True:
                rows = store.pending_searches(session, ctx.video_id)
                if not rows:
                    return
                terms = [r.term for r in rows]
                store.mark_searches(session, ctx.video_id, terms, SearchStatus.running, None)
                try:
                    model = detector.get()
                    model.set_terms(terms)
                    tracker = Tracker(settings.search_fps, SEARCH_TRACKER)
                    last = -1.0
                    for fd in detect_video(
                        path,
                        model,
                        fps=settings.search_fps,
                        batch_size=settings.detect_batch_size,
                        should_cancel=lambda: ctx.cancelled,
                    ):
                        tracker.update(fd)
                        progress = min(fd.t / duration, 0.99) if duration else 0.0
                        if progress - last >= 0.02:
                            ctx.report(progress)
                            last = progress
                    ctx.checkpoint()
                    tracks = tracker.finish()
                    store.save_search(session, ctx.video_id, terms, tracks)
                    logger.info(
                        "video %s: searched %s, %d tracks", ctx.video_id, terms, len(tracks)
                    )
                except (JobCancelled, DetectionCancelled):
                    session.rollback()
                    store.mark_searches(
                        session, ctx.video_id, terms, SearchStatus.failed, "Search was cancelled."
                    )
                    raise JobCancelled from None
                except Exception as e:
                    session.rollback()
                    store.mark_searches(
                        session,
                        ctx.video_id,
                        terms,
                        SearchStatus.failed,
                        str(e)[:500] or e.__class__.__name__,
                    )
                    raise

    return handler


def default_extractors(settings: Settings) -> list[AttributeExtractor]:
    """The attribute extractors a normal (non-test) indexing job runs."""
    found: list[AttributeExtractor] = []
    if settings.extract_color:
        found.append(ColorExtractor(settings.detect_fps))
    if settings.openai_api_key:
        classifier = OpenAIHelmetClassifier(settings.openai_api_key, settings.vision_model)
        found.append(
            HelmetExtractor(classifier, settings.detect_fps, max_calls=settings.helmet_max_calls)
        )
    return found


def default_handlers(
    settings: Settings,
    sessions: sessionmaker[Session],
    detector_factory: DetectorFactory | None = None,
    extractors: Sequence[AttributeExtractor] | None = None,
    search_detector_factory: TermDetectorFactory | None = None,
) -> dict[JobKind, Handler]:
    if settings.indexing == "stub":
        return {
            JobKind.indexing: make_stub_indexing(
                settings.stub_job_steps, settings.stub_job_step_ms / 1000
            )
        }
    return {
        JobKind.indexing: make_indexing_handler(
            settings,
            sessions,
            detector_factory,
            extractors=default_extractors(settings) if extractors is None else extractors,
        ),
        JobKind.search: make_search_handler(settings, sessions, search_detector_factory),
    }
