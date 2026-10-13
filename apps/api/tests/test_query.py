from app.analysis.query import Query, parse_query
from app.analysis.schemas import ScopeInfo

SCOPE = ScopeInfo(
    videoId="v", videoName="Clip", start=0, end=120, duration=120, label="Entire video"
)


def q(text: str) -> Query:
    return parse_query(text, SCOPE)


def test_plain_count_defaults_to_the_whole_scope():
    query = q("How many cars passed?")
    assert query.subject is not None and query.subject.classes == ("car",)
    assert (query.start, query.end, query.from_prompt) == (0, 120, False)
    assert query.term is None and query.colors == () and query.helmet is None
    assert not query.breakdown and not query.wants_table


def test_time_window_comes_from_the_question():
    query = q("cars between 0:10 and 0:40")
    assert (query.start, query.end, query.from_prompt) == (10, 40, True)


def test_colors_and_breakdown_are_exclusive():
    assert q("red or silver cars").colors == ("red", "gray")
    assert q("red or silver cars").silver
    query = q("what colors are the cars?")
    assert query.breakdown and query.colors == ()
    assert not q("how many red cars").breakdown


def test_helmet_direction():
    assert q("people with helmets").helmet is True
    assert q("people without helmets").helmet is False
    assert q("how many people").helmet is None


def test_unknown_noun_becomes_an_open_vocabulary_term():
    query = q("how many trees are there?")
    assert query.term == "tree"
    assert query.subject is not None and query.subject.classes == ("tree",)
    assert query.subject.plural == "trees"


def test_table_request():
    assert q("show a table of all the cars").wants_table
    assert q("SHOW me cars").wants_table


def test_query_is_immutable():
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        q("cars").helmet = True  # type: ignore[misc]
