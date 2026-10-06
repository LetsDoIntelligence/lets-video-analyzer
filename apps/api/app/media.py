"""Reading video metadata and thumbnails (PyAV / FFmpeg)."""

from dataclasses import dataclass
from pathlib import Path

import av
from av.error import FFmpegError


class MediaError(Exception):
    """The file couldn't be read as a video."""


@dataclass(frozen=True)
class ProbeResult:
    duration_sec: float
    fps: float
    width: int
    height: int
    codec: str


def probe(path: Path) -> ProbeResult:
    try:
        with av.open(str(path)) as container:
            stream = next(iter(container.streams.video), None)
            if stream is None:
                raise MediaError("No video track found in that file.")
            ctx = stream.codec_context  # VideoCodecContext at runtime

            duration: float | None = None
            if container.duration:
                duration = container.duration / av.time_base
            elif stream.duration and stream.time_base:
                duration = float(stream.duration * stream.time_base)
            if not duration or duration <= 0:
                raise MediaError("Couldn't determine the video's duration.")

            rate = stream.average_rate or stream.guessed_rate
            return ProbeResult(
                duration_sec=round(duration, 3),
                fps=round(float(rate), 3) if rate else 0.0,
                width=stream.width,
                height=stream.height,
                codec=ctx.name,
            )
    except FFmpegError as e:
        raise MediaError("That file couldn't be read as a video.") from e


def make_thumbnail(path: Path, dest: Path, at_sec: float, max_width: int = 480) -> None:
    """Save a JPEG of the frame at `at_sec` (or the nearest decodable one)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            if at_sec > 0:
                container.seek(int(at_sec / stream.time_base), stream=stream)
            frame = next(container.decode(stream), None)
            if frame is None:
                raise MediaError("Couldn't decode a frame for the thumbnail.")
            image = frame.to_image()  # type: ignore[no-untyped-call]
    except FFmpegError as e:
        raise MediaError("Couldn't decode a frame for the thumbnail.") from e

    if image.width > max_width:
        image = image.resize((max_width, round(image.height * max_width / image.width)))
    image.convert("RGB").save(dest, "JPEG", quality=82)
