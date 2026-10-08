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
