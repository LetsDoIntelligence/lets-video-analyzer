# ML environment

Detection and tracking run in the same conda env as the API (`lets-video`, Python 3.12).

## Setup (once)
```powershell
conda activate lets-video
# CUDA build of PyTorch (RTX 40-series, driver supports CUDA 12.8+)
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -m pip install -e "apps/api[dev,ml]"
python ml/tools/check_gpu.py
```
`check_gpu.py` prints the GPU, downloads the YOLO weights to `ml/weights/` (gitignored), runs a timed
test inference and probes the test video in `test_video/` (gitignored).

Without a GPU everything still runs on CPU, just slower.

## Open-vocabulary search (YOLO-World)
Questions about things the fixed detector doesn't know ("how many trees?", "traffic lights?") start
a background search with YOLO-World. One-off setup:
```powershell
python ml/tools/check_gpu.py --world
```
This downloads `yolov8s-worldv2.pt` (25 MB) and its CLIP text encoder (about 340 MB, to
`ml/weights/clip/`; the `clip` Python package is installed automatically from GitHub on first
use, so `git` and internet access are needed once). Both are gitignored. On an RTX 4050 a search of
the 84 s test clip takes about 17 s (8 s of that is loading and encoding the terms). Results are less
precise than the fixed detector, and the reply says so.

