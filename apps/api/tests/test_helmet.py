import io
import json
import urllib.error
from pathlib import Path

import numpy as np
import pytest

from app.config import Settings
from app.jobs.handlers import default_extractors
from app.vision import helmet as H
from app.vision import store
from app.vision.helmet import HelmetExtractor, encode_crop, parse_answer, vote
from app.vision.tracker import Track

from .test_engine import ask, make_track, stat


def test_parse_answer():
    assert parse_answer('{"helmet": "yes"}') is True
    assert parse_answer('{"helmet": " No "}') is False
    assert parse_answer('{"helmet": "unclear"}') is None
    assert parse_answer("not json") is None
    assert parse_answer("[1]") is None
    assert parse_answer('{"helmet": true}') is None


def test_vote_majority_and_tie():
    assert vote([True, True, False]) is True
    assert vote([False, False, True]) is False
    assert vote([True, False]) is None
    assert vote([]) is None


def test_encode_crop_skips_small_people_and_makes_jpeg():
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    assert encode_crop(img, (10, 10, 30, 30)) is None
    jpeg = encode_crop(img, (10, 10, 60, 120))
    assert jpeg is not None and jpeg[:2] == b"\xff\xd8"


class FakeClassifier:
    def __init__(self, answers=None, fail=False):
        self.answers = answers if answers is not None else [True]
        self.fail = fail
        self.calls = 0

    def classify(self, jpeg: bytes):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return self.answers[(self.calls - 1) % len(self.answers)]


def person(tid: int, height: float = 80.0) -> Track:
    tr = Track(tid)
    for t in (0.0, 0.2, 0.4, 0.6):
        tr.add(t, (10.0, 10.0, 40.0, 10.0 + height), 0.9, "person")
    return tr


@pytest.fixture
def video(tmp_path: Path) -> Path:
    import av

    path = tmp_path / "v.mp4"
    with av.open(str(path), "w") as out:
        stream = out.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 160, 120, "yuv420p"
        for _ in range(10):
            frame = av.VideoFrame.from_ndarray(np.zeros((120, 160, 3), np.uint8), format="rgb24")
            for p in stream.encode(frame):
                out.mux(p)
        for p in stream.encode():
            out.mux(p)
    return path


def run(video: Path, tracks, classifier, **kw):
    HelmetExtractor(classifier, 5.0, **kw).extract(video, tracks, should_cancel=lambda: False)


def test_extractor_sets_helmet_flag(video):
    tracks = [person(1), person(2)]
    run(video, tracks, FakeClassifier([True]))
    assert [t.attrs["helmet"] for t in tracks] == [True, True]


def test_extractor_leaves_unclear_tracks_unset(video):
    tracks = [person(1)]
    run(video, tracks, FakeClassifier([None]))
    assert "helmet" not in tracks[0].attrs


def test_extractor_respects_call_cap(video):
    tracks = [person(i) for i in range(5)]
    c = FakeClassifier([False])
    run(video, tracks, c, max_calls=3)
    assert c.calls == 3


def test_extractor_skips_tiny_people(video):
    c = FakeClassifier()
    run(video, [person(1, height=20)], c)
    assert c.calls == 0


def test_extractor_gives_up_after_repeated_failures(video):
    c = FakeClassifier(fail=True)
    with pytest.raises(RuntimeError):
        run(video, [person(i) for i in range(5)], c)
    assert c.calls == H.MAX_FAILURES


def test_openai_classifier_builds_request_and_hides_key(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data)
        return Resp(
            json.dumps({"choices": [{"message": {"content": '{"helmet":"yes"}'}}]}).encode()
        )

    monkeypatch.setattr(H.urllib.request, "urlopen", fake_urlopen)
    assert H.OpenAIHelmetClassifier("sk-test", "m").classify(b"jpg") is True
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "m"

    def deny(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(H.urllib.request, "urlopen", deny)
    with pytest.raises(RuntimeError) as e:
        H.OpenAIHelmetClassifier("sk-secret", "m").classify(b"jpg")
    assert "sk-secret" not in str(e.value) and "401" in str(e.value)


def test_helmet_extractor_only_enabled_with_a_key(tmp_path):
    base = {"data_dir": tmp_path, "database_url": f"sqlite:///{tmp_path / 'x.db'}"}
    assert "helmet" not in [e.name for e in default_extractors(Settings(**base))]
    keyed = Settings(**base, openai_api_key="sk-test")
    assert "helmet" in [e.name for e in default_extractors(keyed)]
    assert "sk-test" not in repr(keyed)


# --- engine -----------------------------------------------------------------


@pytest.fixture
def vid(client, upload) -> str:
    return str(upload().json()["id"])


def seed_tracks(client, vid, tracks):
    with client.app.state.session_factory() as s:
        store.start_index(s, vid, {})
        store.save_index(s, vid, tracks=tracks, frames=10, width=64, height=48)


def helmet_tracks():
    out = []
    for tid, value in ((1, True), (2, True), (3, False), (4, None)):
        tr = make_track(tid, "person", tid * 5, tid * 5 + 3)
        if value is not None:
            tr.attrs["helmet"] = value
        out.append(tr)
    return out


def test_engine_counts_people_with_and_without_helmets(client, vid):
    seed_tracks(client, vid, helmet_tracks())
    text, blocks = ask(client, vid, "How many people with helmets?")
    assert stat(blocks) == 2
    assert "too small or unclear" in text
    assert "AI vision model" in text
    _, blocks = ask(client, vid, "how many people without helmets")
    assert stat(blocks) == 1


def test_engine_says_when_helmet_check_is_unavailable(client, vid):
    seed_tracks(client, vid, [make_track(1, "person", 0, 3), make_track(2, "person", 5, 8)])
    text, blocks = ask(client, vid, "How many people wearing a helmet?")
    assert stat(blocks) == 2
    assert "isn't available" in text


def test_engine_helmets_on_non_people_are_ignored_with_a_note(client, vid):
    seed_tracks(client, vid, [make_track(1, "car", 0, 3)])
    text, blocks = ask(client, vid, "How many cars with helmets?")
    assert stat(blocks) == 1
    assert "only check helmets on people" in text
