import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.analysis.mock import (
    bucket_size,
    build_reply,
    format_timecode,
    parse_prompt,
    parse_time_window,
    parse_timecode,
)
from app.analysis.schemas import AnalyzeEvent, AnalyzeRequest, ScopeInfo

EVENT = TypeAdapter(AnalyzeEvent)


def scope(start: float = 0, end: float = 600, duration: float = 600, label: str = "Entire video"):  # type: ignore[no-untyped-def]
    return ScopeInfo(
        videoId="v1", videoName="Clip", start=start, end=end, duration=duration, label=label
    )


def body(question: str, **kw: Any) -> dict[str, Any]:
    return {"question": question, "scope": scope(**kw).model_dump()}


def read_sse(text: str) -> list[dict[str, Any]]:
    return [json.loads(p[len("data: ") :]) for p in text.split("\n\n") if p.startswith("data: ")]


# ---- HTTP contract -------------------------------------------------------------------------


def test_stream_follows_contract(client: TestClient) -> None:
    res = client.post("/v1/analyze", json=body("how many red cars? show a table"))
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = read_sse(res.text)
    for e in events:
        EVENT.validate_python(e)  # every event matches the contract
    assert events[0]["type"] == "text"
    assert events[-1]["type"] == "blocks"
    text = "".join(e["chunk"] for e in events if e["type"] == "text")
    assert "red car" in text and "simulated" in text
    kinds = {b["type"] for b in events[-1]["blocks"]}
    assert {"stat", "table"} <= kinds


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "", "scope": scope().model_dump()},
        {"question": "   ", "scope": scope().model_dump()},
        {"question": "x" * 1001, "scope": scope().model_dump()},
        {"question": "hi"},
        {"question": "hi", "scope": {**scope().model_dump(), "start": 50, "end": 10}},
        {"question": "hi", "scope": {**scope().model_dump(), "videoId": ""}},
    ],
)
def test_invalid_requests_are_422(client: TestClient, payload: dict[str, Any]) -> None:
    assert client.post("/v1/analyze", json=payload).status_code == 422


def test_cors_preflight(client: TestClient) -> None:
    res = client.options(
        "/v1/analyze",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200


def test_error_event_when_analysis_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_: AnalyzeRequest):  # type: ignore[no-untyped-def]
        raise RuntimeError("model exploded")

    monkeypatch.setattr("app.routers.analyze.build_reply", boom)
    events = read_sse(client.post("/v1/analyze", json=body("cars?")).text)
    assert events == [
        {"type": "error", "message": "Something went wrong while analysing this video."}
    ]


# ---- Analyzer logic (mirrors the web mock's tests) -----------------------------------------


def test_timecodes() -> None:
    assert parse_timecode("1:35") == 95
    assert parse_timecode("95s") == 95
    assert parse_timecode("1:02:05") == 3725
    assert parse_timecode("abc") is None
    assert format_timecode(95) == "1:35"
    assert format_timecode(3725) == "1:02:05"


def test_parse_prompt() -> None:
    p = parse_prompt("How many red trucks?")
    assert p.subject.singular == "truck" and p.color == "red" and not p.helmets
    assert parse_prompt("people with helmets").helmets
    assert parse_prompt("anything").subject.singular == "car"


def test_time_windows() -> None:
    s = scope()
    w = parse_time_window("cars in the first 30 sec", s)
    assert (w.start, w.end, w.from_prompt) == (0, 30, True)
    w = parse_time_window("cars from 3 to 6 minutes", s)
    assert (w.start, w.end) == (180, 360)
    w = parse_time_window("between 1:00 and 2:30", s)
    assert (w.start, w.end) == (60, 150)
    w = parse_time_window("how many cars", scope(start=10, end=50))
    assert (w.start, w.end, w.from_prompt) == (10, 50, False)
    w = parse_time_window("cars between 9 and 4", s)  # reversed: ignored
    assert not w.from_prompt


def test_first_n_is_relative_to_scope_and_clamped() -> None:
    w = parse_time_window("first 5 min", scope(start=100, end=160, duration=600))
    assert (w.start, w.end) == (100, 160)


def test_reply_is_deterministic_and_scales_with_window() -> None:
    req = AnalyzeRequest(question="how many cars", scope=scope())
    assert build_reply(req) == build_reply(req)
    short = build_reply(AnalyzeRequest(question="cars in the first 30 sec", scope=scope()))
    full = build_reply(req)
    assert short.blocks[0].value < full.blocks[0].value  # type: ignore[union-attr]


def test_chart_only_for_long_enough_windows() -> None:
    long = build_reply(AnalyzeRequest(question="cars", scope=scope()))
    short = build_reply(AnalyzeRequest(question="cars in the first 5 sec", scope=scope()))
    assert any(b.type == "chart" for b in long.blocks)
    assert not any(b.type == "chart" for b in short.blocks)


def test_bucket_size() -> None:
    assert bucket_size(30) == 5
    assert bucket_size(600) == 60
    assert bucket_size(100000) == 600
