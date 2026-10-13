"""Helmet check for person tracks using a vision language model (OpenAI by default).

Each person track gets a couple of its best crops; the model answers yes / no / unclear for
each and the clear answers vote. This is the only extractor that costs money, so it is off
unless an API key is configured, and `max_calls` caps what one video can spend.
"""

import base64
import io
import json
import logging
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from app.vision.frames import sample_frames
from app.vision.pipeline import DetectionCancelled
from app.vision.tracker import Track

logger = logging.getLogger("lets.helmet")

MIN_HEIGHT = 40  # px; a smaller person is too blurry for the model to judge
MAX_FAILURES = 3  # consecutive failed calls before giving up on the whole video
PAD = 0.15  # context added around the box (heads sit at the edge of detector boxes)
PROMPT = (
    "The image is a crop of one person from a traffic or street camera. Are they wearing a "
    "helmet of any kind (bicycle, motorcycle or hard hat)? Reply with JSON only: "
    '{"helmet": "yes"} or {"helmet": "no"} or {"helmet": "unclear"}. Use "unclear" when the '
    "head is hidden, cut off or too small to tell."
)


class HelmetClassifier(Protocol):
    """Looks at one JPEG crop of a person: True / False, or None when it can't tell."""

    def classify(self, jpeg: bytes) -> bool | None: ...


class OpenAIHelmetClassifier:
    """Calls the OpenAI chat completions API with the crop as an inline image (stdlib only)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self._key = api_key
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout = timeout

    def classify(self, jpeg: bytes) -> bool | None:
        image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        body = {
            "model": self.model,
            "max_tokens": 20,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": image, "detail": "low"}},
                    ],
                }
            ],
        }
        req = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            # Never include the request (it carries the key); the status and reason are enough.
            raise RuntimeError(f"OpenAI request failed: HTTP {e.code} {e.reason}") from None
        return parse_answer(payload["choices"][0]["message"]["content"])


def parse_answer(content: str) -> bool | None:
    """Turn the model's reply into True / False / None; anything odd means unknown."""
    try:
        value = json.loads(content).get("helmet")
    except (ValueError, AttributeError):
        return None
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return {"yes": True, "no": False}.get(value)


def vote(answers: Sequence[bool]) -> bool | None:
    """Majority of the clear answers; a tie is unknown, never a guess."""
    if not answers:
        return None
    counts = Counter(answers)
    if counts[True] == counts[False]:
        return None
    return counts[True] > counts[False]


def encode_crop(image: np.ndarray, box: tuple[float, float, float, float]) -> bytes | None:
    """JPEG-encode a padded crop of a BGR frame, or None when the person is too small."""
    x1, y1, x2, y2 = box
    if y2 - y1 < MIN_HEIGHT:
        return None
    height, width = image.shape[:2]
    px, py = (x2 - x1) * PAD, (y2 - y1) * PAD
    crop = image[
        max(int(y1 - py), 0) : min(int(y2 + py) + 1, height),
        max(int(x1 - px), 0) : min(int(x2 + px) + 1, width),
    ]
    if crop.size == 0:
        return None
    buf = io.BytesIO()
    Image.fromarray(crop[:, :, ::-1]).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class HelmetExtractor:
    """Attribute extractor: sets `attrs["helmet"]` (True/False) on person tracks."""

    name = "helmet"
    classes = frozenset({"person"})

    def __init__(
        self,
        classifier: HelmetClassifier,
        sample_fps: float,
        crops_per_track: int = 2,
        max_calls: int = 150,
    ) -> None:
        self.classifier = classifier
        self.sample_fps = sample_fps
        self.crops_per_track = crops_per_track
        self.max_calls = max_calls

    def extract(
        self, video_path: Path, tracks: Sequence[Track], *, should_cancel: Callable[[], bool]
    ) -> None:
        wanted: dict[float, list[tuple[int, tuple[float, float, float, float]]]] = {}
        # Tallest people first: they are the most readable, and they get the budget first.
        order = sorted(
            range(len(tracks)),
            key=lambda i: -max((p.box[3] - p.box[1] for p in tracks[i].points), default=0),
        )
        calls = 0
        for i in order:
            best = sorted(
                (p for p in tracks[i].points if p.box[3] - p.box[1] >= MIN_HEIGHT),
                key=lambda p: (p.box[3] - p.box[1]) * p.conf,
                reverse=True,
            )[: self.crops_per_track]
            for p in best:
                if calls >= self.max_calls:
                    break
                wanted.setdefault(round(p.t, 3), []).append((i, p.box))
                calls += 1
        if not wanted:
            return
        if calls >= self.max_calls:
            logger.info("helmet check limited to %d crops for this video", self.max_calls)
        last = max(wanted)
        answers: dict[int, list[bool]] = {}
        failures = 0
        for frame in sample_frames(video_path, self.sample_fps):
            if should_cancel():
                raise DetectionCancelled
            if frame.t > last + 1e-3:
                break
            for i, box in wanted.get(round(frame.t, 3), ()):
                jpeg = encode_crop(frame.image, box)
                if jpeg is None:
                    continue
                try:
                    result = self.classifier.classify(jpeg)
                    failures = 0
                except Exception:
                    # One bad call is skipped; a run of them (bad key, no network) stops it.
                    failures += 1
                    if failures >= MAX_FAILURES:
                        raise
                    continue
                if result is not None:
                    answers.setdefault(i, []).append(result)
        for i, results in answers.items():
            verdict = vote(results)
            if verdict is not None:
                tracks[i].attrs["helmet"] = verdict
