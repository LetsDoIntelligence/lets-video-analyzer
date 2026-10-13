"""Open-vocabulary search: term parsing, the background job, and how answers use it."""

import threading
from collections.abc import Iterator, Sequence
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analysis.query import parse_subject
from app.config import Settings
from app.jobs.handlers import make_search_handler
from app.main import create_app
from app.models import JobKind, SearchStatus
from app.vision import store
from app.vision.detector import Detection
from app.vision.vocab import extract_term, normalize_term, pluralize, singularize

from .test_engine import TRACKS, ask, stat
from .test_jobs import wait_for

# ---- term parsing -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "term"),
    [
        ("How many trees?", "tree"),
        ("how many trees are there between 0:10 and 0:40", "tree"),
        ("How many traffic lights are in the video?", "traffic light"),
        ("how many street lamps in the first 30 sec", "street lamp"),
        ("How many different buildings can you see", "building"),
        ("Are there any road signs?", "road sign"),
        ("is there a bench", "bench"),
        ("count the umbrellas", "umbrella"),
        ("find all dogs", "dog"),
        ("how many buses passed", "bus"),
        ("How many red umbrellas?", "umbrella"),
    ],
)
def test_terms_are_extracted_and_singularized(question: str, term: str) -> None:
    assert extract_term(question) == term


@pytest.mark.parametrize(
    "question",
    ["How many objects?", "how many are there", "how many things were seen", "hello", "show me"],
)
def test_generic_questions_have_no_term(question: str) -> None:
    assert extract_term(question) is None


def test_overlong_terms_are_rejected() -> None:
    assert normalize_term("extremely long made up thing name here") is None
    assert normalize_term("a" * 40) is None


@pytest.mark.parametrize(
    ("word", "singular"),
    [
        ("trees", "tree"),
        ("buses", "bus"),
        ("boxes", "box"),
        ("puppies", "puppy"),
        ("glass", "glass"),
    ],
)
def test_singularize(word: str, singular: str) -> None:
    assert singularize(word) == singular


@pytest.mark.parametrize(
    ("term", "plural"),
    [
        ("tree", "trees"),
        ("traffic light", "traffic lights"),
        ("box", "boxes"),
        ("puppy", "puppies"),
    ],
)
def test_pluralize(term: str, plural: str) -> None:
    assert pluralize(term) == plural


def test_traffic_lights_are_not_vehicles() -> None:
    assert parse_subject("how many traffic lights?") is None
    assert parse_subject("how much traffic is there?") is not None


# ---- the job and the conversation around it ---------------------------------------------


class FakeWorld:
    """Finds one steady object per term in every frame; can fail or wait on a gate."""

    def __init__(self) -> None:
        self.terms: list[str] = []
        self.error: Exception | None = None
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.runs: list[list[str]] = []

    def set_terms(self, terms: Sequence[str]) -> None:
        self.terms = list(terms)
        self.runs.append(self.terms)

    def detect(self, images: Sequence[np.ndarray]) -> list[list[Detection]]:
        self.started.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.error is not None:
            raise self.error
        return [
            [
                Detection(i, term, 0.6, (5.0 * i, 5.0, 5.0 * i + 20.0, 25.0))
                for i, term in enumerate(self.terms)
            ]
            for _ in images
        ]


@pytest.fixture
def world() -> FakeWorld:
    return FakeWorld()


@pytest.fixture
def searching(settings: Settings, world: FakeWorld) -> Iterator[TestClient]:
    """The app with the real search handler, driven by a fake open-vocabulary detector."""
    with TestClient(create_app(settings)) as c:
        c.app.state.jobs.handlers[JobKind.search] = make_search_handler(  # type: ignore[attr-defined]
            settings,
            c.app.state.session_factory,  # type: ignore[attr-defined]
            detector_factory=lambda: world,
        )
        yield c


def index_video(client: TestClient, upload) -> str:  # type: ignore[no-untyped-def]
    vid = str(upload().json()["id"])
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        store.start_index(s, vid, {})
        store.save_index(s, vid, tracks=TRACKS, frames=100, width=64, height=48)
    return vid


def search_job(client: TestClient, vid: str) -> dict[str, Any]:
    jobs = client.get(f"/v1/videos/{vid}/jobs").json()
    return next(j for j in jobs if j["kind"] == "search")  # type: ignore[no-any-return]


def finish_search(client: TestClient, vid: str) -> dict[str, Any]:
    return wait_for(client, search_job(client, vid)["id"])  # type: ignore[no-any-return]


def test_unknown_term_starts_a_search_then_answers(searching, upload, world) -> None:  # type: ignore[no-untyped-def]
    vid = index_video(searching, upload)
    text, blocks = ask(searching, vid, "How many trees?")
    assert "searching" in text and "trees" in text
    assert blocks == []

    assert finish_search(searching, vid)["status"] == "succeeded"
    assert world.runs == [["tree"]]

    text, blocks = ask(searching, vid, "How many trees?")
    assert "**1 tree**" in text
    assert "open-vocabulary" in text
    assert stat(blocks) == 1


def test_the_built_in_classes_are_unaffected(searching, upload, world) -> None:  # type: ignore[no-untyped-def]
    vid = index_video(searching, upload)
    _, blocks = ask(searching, vid, "How many cars?")
    assert stat(blocks) == 3
    assert world.runs == []  # nothing was searched


def test_search_results_do_not_leak_into_other_answers(searching, upload) -> None:  # type: ignore[no-untyped-def]
    vid = index_video(searching, upload)
    ask(searching, vid, "How many trees?")
    finish_search(searching, vid)
    _, blocks = ask(searching, vid, "How many vehicles?")
    assert stat(blocks) == 4  # trees are not vehicles


def test_asking_again_while_searching_does_not_start_another(  # type: ignore[no-untyped-def]
    searching, upload, world
) -> None:
    world.gate = threading.Event()
    vid = index_video(searching, upload)
    ask(searching, vid, "How many trees?")
    assert world.started.wait(5)
    text, _ = ask(searching, vid, "how many trees are there?")
    assert "still searching" in text
    world.gate.set()
    finish_search(searching, vid)
    assert len(searching.get(f"/v1/videos/{vid}/jobs").json()) == 1
    assert world.runs == [["tree"]]


def test_terms_asked_during_a_search_are_searched_next(searching, upload, world) -> None:  # type: ignore[no-untyped-def]
    world.gate = threading.Event()
    vid = index_video(searching, upload)
    ask(searching, vid, "How many trees?")
    assert world.started.wait(5)
    ask(searching, vid, "How many benches?")  # arrives while "tree" is running
    world.gate.set()
    finish_search(searching, vid)
    assert world.runs == [["tree"], ["bench"]]
    _, blocks = ask(searching, vid, "How many benches?")
    assert stat(blocks) == 1


def test_a_failed_search_is_reported_and_retried(searching, upload, world) -> None:  # type: ignore[no-untyped-def]
    world.error = RuntimeError("out of memory")
    vid = index_video(searching, upload)
    ask(searching, vid, "How many trees?")
    assert finish_search(searching, vid)["status"] == "failed"
    with searching.app.state.session_factory() as s:  # type: ignore[attr-defined]
        row = store.get_search(s, vid, "tree")
        assert row is not None and row.status == SearchStatus.failed
        assert row.error == "out of memory"

    world.error = None
    text, _ = ask(searching, vid, "How many trees?")
    assert "failed (out of memory)" in text and "trying again" in text
    assert finish_search(searching, vid)["status"] == "succeeded"
    _, blocks = ask(searching, vid, "How many trees?")
    assert stat(blocks) == 1


def test_reindexing_forgets_searches(searching, upload) -> None:  # type: ignore[no-untyped-def]
    vid = index_video(searching, upload)
    ask(searching, vid, "How many trees?")
    finish_search(searching, vid)
    with searching.app.state.session_factory() as s:  # type: ignore[attr-defined]
        assert store.get_search(s, vid, "tree") is not None
        store.start_index(s, vid, {})
        assert store.get_search(s, vid, "tree") is None
        assert store.query_tracks(s, vid, cls="tree") == []


def test_a_server_without_search_says_it_cannot(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = index_video(client, upload)  # the default test app has no search handler
    text, blocks = ask(client, vid, "How many trees?")
    assert "can't detect that yet" in text
    assert blocks == []
    with client.app.state.session_factory() as s:  # type: ignore[attr-defined]
        assert store.get_search(s, vid, "tree") is None  # no half-made request left behind


def test_window_applies_to_searched_terms(searching, upload) -> None:  # type: ignore[no-untyped-def]
    vid = index_video(searching, upload)
    ask(searching, vid, "How many trees?")
    finish_search(searching, vid)
    text, _ = ask(searching, vid, "How many trees between 0:00 and 0:05?")
    assert "0:00 – 0:05" in text


@pytest.mark.parametrize(
    "question",
    [
        "How many are there?",
        "show me everything in the first minute",
        "list the detections in a table",
        "show me a summary",
        "how many in the first 30 sec",
    ],
)
def test_vague_questions_still_default_to_cars(question: str) -> None:
    subject = parse_subject(question)
    assert subject is not None and subject.classes == ("car",)


def test_how_many_with_trailing_words_is_not_cars() -> None:
    assert parse_subject("how many trees are there?") is None


# ---- answers that wait for the search ---------------------------------------------------


def _client_with_search(settings: Settings, world: FakeWorld, wait: float) -> TestClient:
    s = settings.model_copy(update={"search_wait_s": wait})
    c = TestClient(create_app(s))
    c.__enter__()
    c.app.state.jobs.handlers[JobKind.search] = make_search_handler(  # type: ignore[attr-defined]
        s,
        c.app.state.session_factory,  # type: ignore[attr-defined]
        detector_factory=lambda: world,
    )
    return c


@pytest.fixture
def waiting(settings: Settings, world: FakeWorld) -> Iterator[TestClient]:
    c = _client_with_search(settings, world, wait=15)
    yield c
    c.__exit__(None, None, None)


def test_the_answer_waits_for_the_search(waiting, upload) -> None:  # type: ignore[no-untyped-def]
    vid = index_video(waiting, upload)
    text, blocks = ask(waiting, vid, "How many trees?")
    assert "I don't have a built-in detector for trees" in text
    assert "**1 tree**" in text  # the same reply carries the real answer
    assert "Ask again" not in text
    assert stat(blocks) == 1


def test_a_failed_search_says_so_and_asks_to_retry(waiting, upload, world) -> None:  # type: ignore[no-untyped-def]
    world.error = RuntimeError("boom")
    vid = index_video(waiting, upload)
    text, blocks = ask(waiting, vid, "How many trees?")
    assert "trying again" in text and "Ask again" in text
    assert blocks == []


def test_a_slow_search_falls_back_to_asking_again(settings, world, upload) -> None:  # type: ignore[no-untyped-def]
    world.gate = threading.Event()
    c = _client_with_search(settings, world, wait=0.05)
    try:
        vid = index_video(c, upload)
        text, blocks = ask(c, vid, "How many trees?")
        assert "taking longer than expected" in text and "Ask again" in text
        assert blocks == []
    finally:
        world.gate.set()
        c.__exit__(None, None, None)
