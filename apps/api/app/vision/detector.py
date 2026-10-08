"""Object detection behind a small interface, so the pipeline can be tested without a GPU."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

# COCO class ids we care about for traffic / people questions.
TRACKED_CLASSES: dict[str, int] = {
    "person": 0,
    "bicycle": 1,
    "car": 2,
    "motorcycle": 3,
    "bus": 5,
    "truck": 7,
}


@dataclass(frozen=True)
class Detection:
    cls_id: int
    cls: str  # class name, e.g. "car"
    conf: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


class Detector(Protocol):
    def detect(self, images: Sequence[np.ndarray]) -> list[list[Detection]]:
        """Detect objects in each BGR image; returns one list per input image."""
        ...


def resolve_device(device: str) -> str | int:
    """`auto` picks the first CUDA GPU when available, otherwise the CPU."""
    if device != "auto":
        return device
    import torch

    return 0 if torch.cuda.is_available() else "cpu"


class YoloDetector:
    """Ultralytics YOLO11 batched inference, restricted to `classes`."""

    def __init__(
        self,
        weights: Path,
        *,
        device: str = "auto",
        conf: float = 0.25,
        imgsz: int = 640,
        classes: dict[str, int] | None = None,
    ) -> None:
        if not weights.exists():
            raise FileNotFoundError(
                f"YOLO weights not found at {weights}. "
                "Run `python ml/tools/check_gpu.py` to download them."
            )
        from ultralytics import YOLO  # type: ignore[attr-defined]  # heavy import, kept lazy

        self._device = resolve_device(device)
        self._conf = conf
        self._imgsz = imgsz
        self._classes = classes or TRACKED_CLASSES
        self._ids = sorted(self._classes.values())
        self._names = {v: k for k, v in self._classes.items()}
        self._model: Any = YOLO(str(weights))

    def detect(self, images: Sequence[np.ndarray]) -> list[list[Detection]]:
        if not images:
            return []
        results = self._model.predict(
            list(images),
            device=self._device,
            conf=self._conf,
            imgsz=self._imgsz,
            classes=self._ids,
            verbose=False,
        )
        out: list[list[Detection]] = []
        for r in results:
            boxes = r.boxes
            if boxes is None or len(boxes) == 0:
                out.append([])
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            ids = boxes.cls.cpu().numpy().astype(int)
            out.append(
                [
                    Detection(
                        cls_id=int(c),
                        cls=self._names[int(c)],
                        conf=float(p),
                        box=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                    )
                    for b, p, c in zip(xyxy, confs, ids, strict=True)
                ]
            )
        return out
