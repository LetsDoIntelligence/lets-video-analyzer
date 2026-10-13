import io
import json
import urllib.error

import pytest

from app.analysis import planner as P
from app.analysis.planner import OpenAIPlanner, PlanError, build_query
from app.analysis.query import SUBJECT_BY_NAME, parse_subject
from app.analysis.schemas import ScopeInfo

SCOPE = ScopeInfo(videoId="v", videoName="Clip", start=0, end=84, duration=84, label="Entire video")

BASE = {
    "subject": "car",
    "term": None,
    "colors": [],
    "helmet": "unspecified",
    "start_sec": None,
    "end_sec": None,
    "last_sec": None,
    "by_color": False,
    "table": False,
}


def plan(**over):
    return build_query({**BASE, **over}, "q", SCOPE)


def test_subjects_match_the_rule_parser():
    # The two lists of built-in subjects must not drift apart.
    for name, subject in SUBJECT_BY_NAME.items():
        assert parse_subject(f"how many {subject.plural}") == subject, name


def test_simple_plan_uses_the_scope():
    q = plan()
    assert q.subject is not None and q.subject.classes == ("car",)
    assert (q.start, q.end, q.from_prompt) == (0, 84, False)


def test_open_vocabulary_term_is_sanitized():
    q = plan(subject="other", term="Red Traffic Lights!")
    assert q.term == "traffic light"
    assert q.subject is not None and q.subject.classes == ("traffic light",)
    with pytest.raises(PlanError):
        plan(subject="other", term=None)
    with pytest.raises(PlanError):
        plan(subject="other", term="x" * 200)


def test_none_subject_is_unsupported_not_an_error():
    assert plan(subject="none").subject is None


@pytest.mark.parametrize("bad", [None, [], "car", 5])
def test_non_object_output_is_rejected(bad):
    with pytest.raises(PlanError):
        build_query(bad, "q", SCOPE)


def test_unknown_subject_is_rejected():
    with pytest.raises(PlanError):
        plan(subject="spaceship")


def test_colors_are_filtered_and_exclusive_with_breakdown():
    q = plan(colors=["red", "pink", "red", "blue"], by_color=True)
    assert q.colors == ("red", "blue")
    assert not q.breakdown  # a color filter wins over a breakdown
    assert plan(by_color=True).breakdown


def test_helmet_mapping():
    assert plan(helmet="with").helmet is True
    assert plan(helmet="without").helmet is False
    assert plan(helmet="maybe").helmet is None


def test_silver_is_noted_from_the_question():
    assert build_query(BASE, "silver cars", SCOPE).silver


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (10, 40, (10, 40, True)),
        (-5, 30, (0, 30, True)),  # clamped to the video
        (60, 500, (60, 84, True)),
        (None, 30, (0, 30, True)),  # open start means the scope start
        (20, None, (20, 84, True)),
        (50, 10, (0, 84, False)),  # backwards: ignore it
        (500, 900, (0, 84, False)),  # entirely outside: ignore it
        (float("nan"), float("nan"), (0, 84, False)),
        ("ten", True, (0, 84, False)),
        (None, None, (0, 84, False)),
    ],
)
def test_window_is_clamped(start, end, expected):
    q = plan(start_sec=start, end_sec=end)
    assert (q.start, q.end, q.from_prompt) == expected


# --- the OpenAI call --------------------------------------------------------


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def reply(content):
    return Resp(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def test_request_is_schema_constrained_and_parsed(monkeypatch):
    seen = {}

    def fake(req, timeout):
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data)
        return reply(json.dumps({**BASE, "colors": ["red"], "start_sec": 0, "end_sec": 30}))

    monkeypatch.setattr(P.urllib.request, "urlopen", fake)
    q = OpenAIPlanner("sk-test", "m").plan("red cars in the first 30 sec", SCOPE)
    assert q.colors == ("red",) and (q.start, q.end, q.from_prompt) == (0, 30, True)
    body = seen["body"]
    assert seen["auth"] == "Bearer sk-test"
    assert body["model"] == "m" and body["temperature"] == 0
    assert body["response_format"]["json_schema"]["strict"] is True
    assert "84 seconds" in body["messages"][1]["content"]
    assert "red cars in the first 30 sec" in body["messages"][1]["content"]


@pytest.mark.parametrize("content", ["not json", "[1, 2]", json.dumps({**BASE, "subject": "x"})])
def test_bad_model_output_raises_plan_error(monkeypatch, content):
    monkeypatch.setattr(P.urllib.request, "urlopen", lambda req, timeout: reply(content))
    with pytest.raises(PlanError):
        OpenAIPlanner("sk-test").plan("q", SCOPE)


def test_http_and_network_errors_become_plan_errors_without_the_key(monkeypatch):
    def deny(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(P.urllib.request, "urlopen", deny)
    with pytest.raises(PlanError) as e:
        OpenAIPlanner("sk-secret").plan("q", SCOPE)
    assert "sk-secret" not in str(e.value) and "401" in str(e.value)

    def down(req, timeout):
        raise TimeoutError("sk-secret leaked?")

    monkeypatch.setattr(P.urllib.request, "urlopen", down)
    with pytest.raises(PlanError) as e2:
        OpenAIPlanner("sk-secret").plan("q", SCOPE)
    assert "sk-secret" not in str(e2.value)


def test_missing_choices_is_a_plan_error(monkeypatch):
    monkeypatch.setattr(P.urllib.request, "urlopen", lambda req, timeout: Resp(b'{"choices": []}'))
    with pytest.raises(PlanError):
        OpenAIPlanner("sk-test").plan("q", SCOPE)


@pytest.mark.parametrize(
    ("last", "expected"),
    [
        (60, (24, 84, True)),
        (10, (74, 84, True)),
        (500, (0, 84, False)),  # longer than the video: the whole video
        (0, (0, 84, False)),
        (-5, (0, 84, False)),
    ],
)
def test_last_n_seconds_is_computed_here_not_by_the_model(last, expected):
    q = plan(last_sec=last)
    assert (q.start, q.end, q.from_prompt) == expected
