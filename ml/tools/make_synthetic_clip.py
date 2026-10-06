"""Generate a small synthetic 'traffic' clip for UI development.

Not real footage: coloured boxes crossing a road. Lets us exercise the player
and range selector before the lead supplies real videos.

Usage: python ml/tools/make_synthetic_clip.py
"""

from pathlib import Path
import random

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw

W, H, FPS, SECONDS = 640, 360, 15, 60
OUT = Path(__file__).resolve().parents[2] / "apps/web/public/samples/synthetic-traffic.mp4"

random.seed(7)
COLORS = [(200, 50, 50), (50, 90, 200), (230, 230, 230), (40, 40, 40), (220, 180, 40)]
LANES = [120, 170, 220, 270]

vehicles = []  # (t_start, lane_y, speed_px_per_s, direction, color, is_truck)
for _ in range(36):
    vehicles.append(
        (
            random.uniform(0, SECONDS - 6),
            random.choice(LANES),
            random.uniform(110, 220),
            random.choice([1, -1]),
            random.choice(COLORS),
            random.random() < 0.2,
        )
    )

OUT.parent.mkdir(parents=True, exist_ok=True)
writer = imageio.get_writer(OUT, fps=FPS, codec="libx264", quality=6, macro_block_size=None)

for f in range(FPS * SECONDS):
    t = f / FPS
    img = Image.new("RGB", (W, H), (34, 46, 56))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 95, W, 295], fill=(58, 62, 68))
    for y in (145, 195, 245):
        for x in range(0, W, 60):
            d.rectangle([x, y - 1, x + 28, y + 1], fill=(200, 200, 190))
    for t0, y, speed, direction, color, truck in vehicles:
        dt = t - t0
        if dt < 0:
            continue
        x = (-80 + dt * speed) if direction == 1 else (W + 80 - dt * speed)
        w, h = (64, 26) if truck else (42, 20)
        if -w < x < W + w:
            d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], 5, fill=color)
    mins, secs = divmod(int(t), 60)
    d.text((10, 10), f"SYNTHETIC TEST CLIP  {mins}:{secs:02d}", fill=(230, 240, 245))
    writer.append_data(np.asarray(img))

writer.close()
print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
