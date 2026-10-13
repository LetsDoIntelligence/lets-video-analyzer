"""Check the ML environment: CUDA, YOLO weights, a test inference, and the test video.

Usage (from repo root, env `lets-video` active):
    python ml/tools/check_gpu.py [--model yolo11s.pt] [--video "test_video/Test Video.mp4"] [--world]

`--world` also fetches the open-vocabulary model (YOLO-World, 25 MB) and its CLIP text encoder
(about 340 MB, installed/downloaded on first use) and runs a search for a few example nouns.
"""

import argparse
import time
from pathlib import Path

import av
import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.utils.downloads import attempt_download_asset

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = ROOT / "ml" / "weights"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="yolo11s.pt")
    parser.add_argument("--video", default=str(ROOT / "test_video" / "Test Video.mp4"))
    parser.add_argument("--world", action="store_true", help="also set up open-vocabulary search")
    args = parser.parse_args()

    print(f"torch {torch.__version__}, CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        gb = props.total_memory / 1024**3
        print(f"GPU: {props.name}, {gb:.1f} GB, cuda {torch.version.cuda}")
    device = 0 if torch.cuda.is_available() else "cpu"

    WEIGHTS.mkdir(parents=True, exist_ok=True)
    weights = WEIGHTS / args.model
    if not weights.exists():
        attempt_download_asset(str(weights))
    model = YOLO(str(weights))

    # Warm-up + timed inference on a batch of random frames.
    frames = [np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8) for _ in range(8)]
    model.predict(frames, device=device, verbose=False)
    start = time.perf_counter()
    model.predict(frames, device=device, verbose=False)
    ms = (time.perf_counter() - start) * 1000 / len(frames)
    print(f"{args.model}: {ms:.1f} ms/frame (batch of 8, 720p, device={device})")

    video = Path(args.video)
    if video.exists():
        with av.open(str(video)) as container:
            stream = container.streams.video[0]
            duration = float(container.duration or 0) / av.time_base
            print(
                f"video: {video.name} {stream.codec_context.width}x{stream.codec_context.height} "
                f"{float(stream.average_rate or 0):.2f} fps {duration:.1f}s "
                f"{stream.codec_context.name}"
            )
    else:
        print(f"video not found: {video}")

    if args.world:
        check_world(device)


def check_world(device: int | str) -> None:
    from ultralytics import YOLOWorld
    import ultralytics.nn.text_model as text_model

    weights = WEIGHTS / "yolov8s-worldv2.pt"
    if not weights.exists():
        attempt_download_asset(str(weights))
    text_model.WEIGHTS_DIR = WEIGHTS  # keep the CLIP download next to the other weights
    model = YOLOWorld(str(weights))
    start = time.perf_counter()
    model.set_classes(["tree", "traffic light", "road sign"])
    print(f"yolov8s-worldv2: text encoder ready in {time.perf_counter() - start:.1f} s")
    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    model.predict(frame, device=device, verbose=False)
    start = time.perf_counter()
    model.predict(frame, device=device, verbose=False)
    print(f"yolov8s-worldv2: {(time.perf_counter() - start) * 1000:.0f} ms/frame (720p)")


if __name__ == "__main__":
    main()
