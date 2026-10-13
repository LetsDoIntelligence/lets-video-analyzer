import pytest
from fastapi.testclient import TestClient

from app.analysis.planner import PlanError
from app.analysis.query import SUBJECT_BY_NAME, Query
from app.analysis.schemas import ScopeInfo
from app.analysis.service import FALLBACK_NOTE, QueryPlanner, make_planner
from app.config import Settings

from .test_engine import ask, seed_colored, stat, vid  # noqa: F401

SCOPE = ScopeInfo(videoId="v", videoName="Clip", start=0, end=30, duration=30, label="Entire video")


class FakePlanner:
    def __init__(self, query: Query | None = None, fail: bool = False) -> None:
        self.query = query
        self.fail = fail
        self.calls = 0

    def plan(self, question: str, scope: ScopeInfo) -> Query:
        self.calls += 1
        if self.fail or self.query is None:
            raise PlanError("down")
        return self.query


def red_cars() -> Query:
    return Query(subject=SUBJECT_BY_NAME["car"], start=0, end=30, colors=("red",))


def test_rules_mode_never_calls_the_llm():
    fake = FakePlanner(red_cars())
    p = QueryPlanner("rules", fake)
    assert not p.uses_llm
    planned = p.plan("how many cars", SCOPE)
    assert fake.calls == 0 and not planned.fallback
    assert planned.query.subject is not None and planned.query.subject.classes == ("car",)


def test_auto_uses_the_llm_and_caches():
    fake = FakePlanner(red_cars())
    p = QueryPlanner("auto", fake)
    assert p.plan("How many reds?", SCOPE).query.colors == ("red",)
    assert p.plan("  how many REDS? ", SCOPE).query.colors == ("red",)  # same question
    assert fake.calls == 1
    p.plan("how many reds?", SCOPE.model_copy(update={"end": 20}))  # different range
    assert fake.calls == 2


def test_cache_is_bounded():
    fake = FakePlanner(red_cars())
    p = QueryPlanner("auto", fake, cache_size=2)
    for q in ("a", "b", "c"):
        p.plan(q, SCOPE)
    p.plan("a", SCOPE)  # evicted, asks again
    assert fake.calls == 4


def test_auto_falls_back_to_rules_and_does_not_cache_the_failure():
    fake = FakePlanner(fail=True)
    p = QueryPlanner("auto", fake)
    planned = p.plan("how many trucks", SCOPE)
    assert planned.fallback
    assert planned.query.subject is not None and planned.query.subject.classes == ("truck",)
    p.plan("how many trucks", SCOPE)
    assert fake.calls == 2


def test_llm_mode_raises_on_failure():
    with pytest.raises(PlanError):
        QueryPlanner("llm", FakePlanner(fail=True)).plan("cars", SCOPE)


def test_make_planner_follows_settings(tmp_path):
    base = {"data_dir": tmp_path, "database_url": f"sqlite:///{tmp_path / 'x.db'}"}
    assert not make_planner(Settings(**base, openai_api_key="", planner="auto")).uses_llm
    assert make_planner(Settings(**base, openai_api_key="sk-t", planner="auto")).uses_llm
    assert make_planner(Settings(**base, openai_api_key="sk-t", planner="llm")).uses_llm
    assert not make_planner(Settings(**base, openai_api_key="sk-t", planner="rules")).uses_llm


# --- through the API ----------------------------------------------------------


def use(client: TestClient, planner: QueryPlanner) -> None:
    client.app.state.planner = planner  # type: ignore[attr-defined]


def test_answer_follows_the_planned_query(client: TestClient, vid: str) -> None:  # noqa: F811
    seed_colored(client, vid)
    use(client, QueryPlanner("auto", FakePlanner(red_cars())))
    # The question text says nothing about color; the planner's Query does.
    text, blocks = ask(client, vid, "how many of the crimson ones")
    assert stat(blocks) == 2
    assert "red cars" in text and FALLBACK_NOTE not in text


def test_fallback_is_announced(client: TestClient, vid: str) -> None:  # noqa: F811
    seed_colored(client, vid)
    use(client, QueryPlanner("auto", FakePlanner(fail=True)))
    text, blocks = ask(client, vid, "how many red cars?")
    assert stat(blocks) == 2  # the rules still answer it
    assert FALLBACK_NOTE in text


def test_llm_only_failure_asks_to_retry(client: TestClient, vid: str) -> None:  # noqa: F811
    seed_colored(client, vid)
    use(client, QueryPlanner("llm", FakePlanner(fail=True)))
    text, blocks = ask(client, vid, "how many cars?")
    assert "try again" in text and blocks == []


def test_planner_is_not_called_before_the_video_is_analyzed(
    client: TestClient,
    vid: str,  # noqa: F811
) -> None:
    fake = FakePlanner(red_cars())
    use(client, QueryPlanner("auto", fake))
    text, _ = ask(client, vid, "how many cars?")
    assert "analy" in text.lower()
    assert fake.calls == 0
