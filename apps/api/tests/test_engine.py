"""The query engine answers from stored tracks (seeded here, no detector needed)."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.vision import store
from app.vision.tracker import Track


def make_track(tid: int, cls: str, t0: float, t1: float) -> Track:
    tr = Track(tid)
    t = t0
    while t <= t1:
        tr.add(t, (10.0, 10.0, 50.0, 40.0), 0.9, cls)
        t += 0.5
    return tr


TRACKS = [
    make_track(1, "car", 0, 3),
    make_track(2, "car", 10, 14),
    make_track(3, "car", 20, 25),
    make_track(4, "truck", 12, 18),
    make_track(5, "person", 5, 9),
]


def sse(text: str) -> list[dict[str, Any]]:
    return [json.loads(p[6:]) for p in text.split("\n\n") if p.startswith("data: ")]


@pytest.fixture
def vid(client: TestClient, upload) -> str:  # type: ignore[no-untyped-def]
    return str(upload().json()["id"])


def seed(client: TestClient, vid: str) -> None:
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        store.start_index(s, vid, {})
        store.save_index(s, vid, tracks=TRACKS, frames=100, width=64, height=48)


def ask(
    client: TestClient, vid: str, q: str, start: float = 0, end: float = 30
) -> tuple[str, list[dict[str, Any]]]:
    scope = {
        "videoId": vid,
        "videoName": "Clip",
        "start": start,
        "end": end,
        "duration": 30,
        "label": "Entire video",
    }
    res = client.post("/v1/analyze", json={"question": q, "scope": scope})
    assert res.status_code == 200
    ev = sse(res.text)
    text = "".join(e["chunk"] for e in ev if e["type"] == "text")
    blocks = ev[-1]["blocks"] if ev and ev[-1]["type"] == "blocks" else []
    return text, blocks


def stat(blocks: list[dict[str, Any]]) -> float:
    return next(b["value"] for b in blocks if b["type"] == "stat")


def test_counts_unique_cars(client: TestClient, vid: str) -> None:
    seed(client, vid)
    text, blocks = ask(client, vid, "How many cars passed?")
    assert stat(blocks) == 3
    assert "simulated" not in text


def test_question_window_counts_overlap(client: TestClient, vid: str) -> None:
    seed(client, vid)
    _, blocks = ask(client, vid, "How many cars between 0:09 and 0:15?")
    assert stat(blocks) == 1


def test_ui_scope_range(client: TestClient, vid: str) -> None:
    seed(client, vid)
    _, blocks = ask(client, vid, "How many cars?", start=18, end=30)
    assert stat(blocks) == 1


def test_vehicles_has_type_table(client: TestClient, vid: str) -> None:
    seed(client, vid)
    _, blocks = ask(client, vid, "How many vehicles?")
    assert stat(blocks) == 4
    assert any(b["type"] == "table" and b.get("title") == "By type" for b in blocks)


def test_color_question_has_caveat(client: TestClient, vid: str) -> None:
    seed(client, vid)
    text, blocks = ask(client, vid, "How many red cars?")
    assert "colors" in text.lower() or "colours" in text.lower()
    assert stat(blocks) == 3


def test_unknown_subject(client: TestClient, vid: str) -> None:
    seed(client, vid)
    text, blocks = ask(client, vid, "How many trees?")
    assert "can't detect" in text.lower()
    assert blocks == []


def test_empty_window(client: TestClient, vid: str) -> None:
    seed(client, vid)
    text, _ = ask(client, vid, "How many people?", start=20, end=30)
    assert "didn't find any" in text.lower()


def test_table_request(client: TestClient, vid: str) -> None:
    seed(client, vid)
    _, blocks = ask(client, vid, "List the cars in a table")
    assert any(b["type"] == "table" for b in blocks)


def test_not_indexed(client: TestClient, vid: str) -> None:
    text, blocks = ask(client, vid, "How many cars?")
    assert blocks == []
    assert text


def test_running_and_failed(client: TestClient, vid: str) -> None:
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        store.start_index(s, vid, {})
        store.fail_index(s, vid, "boom")
    text, blocks = ask(client, vid, "How many cars?")
    assert blocks == []
    assert text


def test_unknown_video_still_simulated(client: TestClient) -> None:
    text, blocks = ask(client, "nope", "How many cars?")
    assert "simulated" in text
    assert blocks


def test_detections_window(client: TestClient, vid: str) -> None:
    seed(client, vid)
    res = client.get(f"/v1/videos/{vid}/detections", params={"start": 9, "end": 13})
    assert res.status_code == 200
    body = res.json()
    assert (body["width"], body["height"]) == (64, 48)
    by_id = {t["id"]: t for t in body["tracks"]}
    assert set(by_id) == {2, 4, 5}  # cars #2, truck #4 and the person (ends at 9)
    assert all(9 <= p[0] <= 13 and len(p) == 5 for t in body["tracks"] for p in t["points"])


def test_detections_errors(client: TestClient, vid: str) -> None:
    url = f"/v1/videos/{vid}/detections"
    assert client.get(url).status_code == 409  # not analyzed
    seed(client, vid)
    assert client.get(url, params={"start": 5, "end": 5}).status_code == 422
    assert client.get(url, params={"start": 0, "end": 500}).status_code == 422
    assert client.get("/v1/videos/nope/detections").status_code == 404


def test_timestamps_have_no_duplicates(client: TestClient, vid: str) -> None:
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        store.start_index(s, vid, {})
        twins = [
            make_track(1, "car", 10, 14),
            make_track(2, "car", 10, 15),
            make_track(3, "car", 20, 25),
        ]
        store.save_index(s, vid, tracks=twins, frames=100, width=64, height=48)
    _, blocks = ask(client, vid, "How many cars?")
    times = next(b["times"] for b in blocks if b["type"] == "timestamps")
    assert len(times) == len(set(times)) == 2
