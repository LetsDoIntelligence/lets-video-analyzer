import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app


def test_upload_probes_metadata(upload) -> None:  # type: ignore[no-untyped-def]
    res = upload()
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Road Cam"
    assert body["filename"] == "Road Cam.mp4"
    assert body["status"] == "ready"
    assert body["durationSec"] == pytest.approx(2.0, abs=0.2)
    assert body["fps"] == pytest.approx(10, abs=0.5)
    assert (body["width"], body["height"]) == (64, 48)
    assert body["codec"] == "mpeg4"
    assert body["src"] == f"/v1/videos/{body['id']}/file"
    assert body["thumbnailSrc"] == f"/v1/videos/{body['id']}/thumbnail"
    assert "thumbnailPath" not in body


def test_thumbnail_is_a_jpeg(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()
    res = client.get(vid["thumbnailSrc"])
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(res.content)).size == (64, 48)


def test_unreadable_video_is_rejected_and_not_kept(
    client: TestClient,
    settings: Settings,
    upload,  # type: ignore[no-untyped-def]
) -> None:
    res = upload("broken.mp4", data=b"definitely not a video" * 100)
    assert res.status_code == 422
    assert client.get("/v1/videos").json() == []
    assert list((settings.data_dir / "videos").glob("*")) == []


def test_list_get_and_missing(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    first = upload("a.mp4").json()
    second = upload("b.mp4").json()
    listed = client.get("/v1/videos").json()
    assert [v["id"] for v in listed] == [second["id"], first["id"]]  # newest first
    assert client.get(f"/v1/videos/{first['id']}").json()["name"] == "a"
    assert client.get("/v1/videos/nope").status_code == 404
    assert client.get("/v1/videos/nope/thumbnail").status_code == 404


def test_rejects_non_video(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    assert upload("notes.txt", ctype="text/plain").status_code == 415
    assert upload("fake.mp4", ctype="text/plain").status_code == 415
    assert client.get("/v1/videos").json() == []


def test_rejects_empty_file(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    assert upload(data=b"").status_code == 400
    assert client.get("/v1/videos").json() == []


def test_rejects_oversize_and_cleans_up(tmp_path: Path, video_bytes: bytes) -> None:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{(tmp_path / 't.db').as_posix()}",
        max_upload_bytes=1000,
    )
    with TestClient(create_app(settings)) as c:
        res = c.post("/v1/videos", files={"file": ("a.mp4", io.BytesIO(video_bytes), "video/mp4")})
        assert res.status_code == 413
        assert c.get("/v1/videos").json() == []
    assert list((tmp_path / "videos").glob("*")) == []


def test_filename_is_not_used_as_path(
    client: TestClient,
    settings: Settings,
    upload,  # type: ignore[no-untyped-def]
) -> None:
    body = upload("../../evil.mp4").json()
    assert body["name"] == "evil"
    stored = list((settings.data_dir / "videos").glob("*"))
    assert len(stored) == 1 and stored[0].name.startswith(body["id"])


def test_stream_full_and_range(client: TestClient, upload, video_bytes: bytes) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()
    full = client.get(vid["src"])
    assert full.status_code == 200
    assert full.content == video_bytes
    assert full.headers["accept-ranges"] == "bytes"

    part = client.get(vid["src"], headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.content == video_bytes[100:200]
    assert part.headers["content-range"] == f"bytes 100-199/{len(video_bytes)}"


def test_delete_removes_record_and_files(
    client: TestClient,
    settings: Settings,
    upload,  # type: ignore[no-untyped-def]
) -> None:
    vid = upload().json()
    assert client.delete(f"/v1/videos/{vid['id']}").status_code == 204
    assert client.get(f"/v1/videos/{vid['id']}").status_code == 404
    assert list((settings.data_dir / "videos").glob("*")) == []
    assert list((settings.data_dir / "thumbnails").glob("*")) == []
    assert client.delete(f"/v1/videos/{vid['id']}").status_code == 404
