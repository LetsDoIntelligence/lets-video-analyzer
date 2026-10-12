"""Color naming: pixel classes, crop voting, and the extractor against a real encoded video."""

from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.vision.color import ColorExtractor, classify_pixels, dominant_color, vote
from app.vision.tracker import Track

# BGR, the order frames use
SWATCHES = {
    "white": (235, 235, 235),
    "black": (15, 15, 15),
    "gray": (128, 128, 128),
    "red": (30, 30, 200),
    "orange": (30, 140, 230),
    "yellow": (30, 220, 230),
    "green": (60, 180, 40),
    "blue": (200, 60, 30),
}


def solid(bgr: tuple[int, int, int], size: tuple[int, int] = (60, 40)) -> np.ndarray:
    return np.full((size[1], size[0], 3), bgr, dtype=np.uint8)


@pytest.mark.parametrize("name", list(SWATCHES))
def test_solid_colors_are_named(name: str) -> None:
    assert dominant_color(solid(SWATCHES[name])) == (name, 1.0)
    assert classify_pixels(solid(SWATCHES[name])).most_common(1)[0][0] == name


def test_dark_windshield_does_not_hide_the_body_color() -> None:
    car = solid(SWATCHES["red"], (100, 80))
    car[10:40, 20:80] = SWATCHES["black"]  # windshield band across the upper middle
    assert dominant_color(car)[0] == "red"  # type: ignore[index]


def test_an_almost_black_car_is_black() -> None:
    car = solid(SWATCHES["black"], (100, 80))
    car[60:70, 40:60] = SWATCHES["gray"]
    assert dominant_color(car)[0] == "black"  # type: ignore[index]


def test_a_real_tint_beats_dull_gray() -> None:
    car = solid(SWATCHES["gray"], (100, 80))
    car[30:80, 20:60] = SWATCHES["blue"]  # a fair patch of blue paint
    assert dominant_color(car)[0] == "blue"  # type: ignore[index]


def test_tiny_crops_are_not_judged() -> None:
    assert dominant_color(solid(SWATCHES["red"], (8, 8))) is None


def test_a_muddle_of_colors_gives_no_answer() -> None:
    rng = np.random.default_rng(1)
    noise = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
    assert dominant_color(noise) is None


def test_vote_weighs_crops() -> None:
    assert vote([("red", 1.0), ("blue", 5.0), ("red", 2.0)]) == "blue"
    assert vote([]) is None


def write_video_with_red_box(path: Path, seconds: int = 2, fps: int = 10) -> None:
    size = (160, 120)
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, fps)
        for _ in range(seconds * fps):
            img = Image.new("RGB", size, (110, 110, 110))
            ImageDraw.Draw(img).rectangle((40, 30, 120, 100), fill=(200, 30, 30))  # RGB red
            for packet in stream.encode(av.VideoFrame.from_image(img)):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def test_extractor_names_a_track_from_the_video(tmp_path: Path) -> None:
    video = tmp_path / "red.mp4"
    write_video_with_red_box(video)
    car, bystander = Track(1), Track(2)
    for i in range(10):  # sampled at 5 fps: 0.0, 0.2, ... 1.8
        car.add(i * 0.2, (40.0, 30.0, 120.0, 100.0), 0.9, "car")
        bystander.add(i * 0.2, (0.0, 0.0, 30.0, 25.0), 0.8, "car")  # plain gray corner
    ColorExtractor(5.0).extract(video, [car, bystander], should_cancel=lambda: False)
    assert car.attrs["color"] == "red"
    assert bystander.attrs["color"] == "gray"


def test_extractor_honours_cancellation(tmp_path: Path) -> None:
    from app.vision.pipeline import DetectionCancelled

    video = tmp_path / "red.mp4"
    write_video_with_red_box(video)
    car = Track(1)
    car.add(0.0, (40.0, 30.0, 120.0, 100.0), 0.9, "car")
    with pytest.raises(DetectionCancelled):
        ColorExtractor(5.0).extract(video, [car], should_cancel=lambda: True)
