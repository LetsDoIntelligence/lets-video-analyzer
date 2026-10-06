import io
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path

import av
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app


def write_test_video(
    path: Path, seconds: int = 2, fps: int = 10, size: tuple[int, int] = (64, 48)
) -> None:
    """Encode a small real MP4 (mpeg4) so probing and thumbnails run on genuine media."""
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, fps)
        for i in range(seconds * fps):
            img = Image.new("RGB", size, (i * 10 % 256, 80, 160))
            frame = av.VideoFrame.from_image(img)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


@pytest.fixture(scope="session")
def video_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    path = tmp_path_factory.mktemp("media") / "clip.mp4"
    write_test_video(path)
    return path.read_bytes()


@pytest.fixture
def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        analyze_think_ms=0,
        analyze_token_ms=0,
        stub_job_steps=5,
        stub_job_step_ms=0,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def upload(client: TestClient, video_bytes: bytes):  # type: ignore[no-untyped-def]
    """Upload a (real, tiny) video through the API."""

    def _upload(name: str = "Road Cam.mp4", data: bytes | None = None, ctype: str = "video/mp4"):  # type: ignore[no-untyped-def]
        body = video_bytes if data is None else data
        return client.post("/v1/videos", files={"file": (name, io.BytesIO(body), ctype)})

    return _upload
