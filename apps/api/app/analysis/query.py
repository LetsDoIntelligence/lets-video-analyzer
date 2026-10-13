"""What a question asks for, as data: the `Query` the engine runs.

`parse_query` builds one with simple rules. Phase 5's LLM planner builds the same thing, so
everything after this point (counting, charts, tables) never cares which one was used.
"""

import re
from dataclasses import dataclass

from app.analysis.mock import parse_time_window
from app.analysis.schemas import ScopeInfo
from app.vision.color import COLOR_NAMES
from app.vision.vocab import extract_term, pluralize


@dataclass(frozen=True)
class Subject:
    classes: tuple[str, ...]  # detector classes that count as this subject
    singular: str
    plural: str


_CAR = Subject(("car",), "car", "cars")
_VEHICLE = Subject(("car", "truck", "bus", "motorcycle"), "vehicle", "vehicles")

_SUBJECTS: list[tuple[re.Pattern[str], Subject]] = [
    (re.compile(r"\b(vehicles?|traffic(?! (?:lights?|signs?|cones?)))\b"), _VEHICLE),
    (re.compile(r"\b(trucks?|lorr(?:y|ies))\b"), Subject(("truck",), "truck", "trucks")),
    (re.compile(r"\b(buses|bus)\b"), Subject(("bus",), "bus", "buses")),
    (
        re.compile(r"\b(motorcycles?|motorbikes?|scooters?)\b"),
        Subject(("motorcycle",), "motorcycle", "motorcycles"),
    ),
    (
        re.compile(r"\b(bicycles?|cyclists?|bikes?)\b"),
        Subject(("bicycle",), "bicycle", "bicycles"),
    ),
    (
        re.compile(r"\b(people|persons?|pedestrians?|workers?)\b"),
        Subject(("person",), "person", "people"),
    ),
    (re.compile(r"\b(cars?|automobiles?|suvs?|sedans?|taxis?)\b"), _CAR),
]
# The built-in subjects by name (what the LLM planner picks from).
SUBJECT_BY_NAME: dict[str, Subject] = {
    "car": _CAR,
    "truck": Subject(("truck",), "truck", "trucks"),
    "bus": Subject(("bus",), "bus", "buses"),
    "motorcycle": Subject(("motorcycle",), "motorcycle", "motorcycles"),
    "bicycle": Subject(("bicycle",), "bicycle", "bicycles"),
    "person": Subject(("person",), "person", "people"),
    "vehicle": _VEHICLE,
}
# Words people use for the colors the extractor can name (silver is folded into gray).
_COLOR_WORDS = {name: name for name in COLOR_NAMES} | {"silver": "gray", "grey": "gray"}
_COLOR_RX = re.compile(r"\b(" + "|".join(_COLOR_WORDS) + r")\b")
_WANTS_BREAKDOWN = re.compile(r"\b(by colou?rs?|what colou?rs?|which colou?rs?|colou?rs?)\b")
_HELMET_NO = re.compile(
    r"\b(without|no|not wearing|missing|lacking)\s+(a\s+|any\s+)?(helmets?|hard ?hats?)\b"
)
_HELMET_YES = re.compile(r"\b(helmets?|helmeted|hard ?hats?)\b")
_WANTS_TABLE = re.compile(r"\b(table|list|breakdown|details?|each|show)\b", re.IGNORECASE)
_PEAK = re.compile(
    r"\b(busiest|heaviest|peak|rush hour|most (?:cars|trucks|vehicles|people|traffic))\b"
)
_MOST_COMMON = re.compile(
    r"\b(most (?:common|popular|frequent)|dominant|top)\s+colou?rs?\b"
    r"|\bwhich colou?rs? (?:is|are|was|were) (?:the )?(?:most|more)\b"
    r"|\bcommonest colou?rs?\b"
)
_LAST_N = re.compile(r"\blast\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m)\b")
_LAST_ONE = re.compile(r"\b(?:the\s+)?last\s+(second|minute)\b")
_FIRST_ONE = re.compile(r"\b(?:the\s+)?first\s+(second|minute)\b")
_FIRST_HALF = re.compile(r"\b(?:first|1st)\s+half\b")
_SECOND_HALF = re.compile(r"\b(?:second|2nd|last)\s+half\b")


def join_subjects(subjects: list[Subject]) -> Subject:
    """Several subjects as one: "cars and trucks" counts both (the reply adds a by-type table)."""
    classes = tuple(dict.fromkeys(c for s in subjects for c in s.classes))
    return Subject(
        classes,
        " or ".join(s.singular for s in subjects),
        " and ".join(s.plural for s in subjects),
    )


def parse_subject(question: str) -> Subject | None:
    """The detected class(es) the question is about; None if it names something we can't see."""
    q = question.lower()
    hits = [(m.start(), s) for rx, s in _SUBJECTS if (m := rx.search(q))]
    if hits:
        if any(s is _VEHICLE for _, s in hits):
            return _VEHICLE  # already everything with wheels
        ordered = [s for _, s in sorted(hits, key=lambda h: h[0])]
        return ordered[0] if len(ordered) == 1 else join_subjects(ordered)
    if extract_term(q) is not None:
        return None  # it names something else; the caller may search for it
    return _CAR  # e.g. "show me everything in the first minute": default to cars


def parse_helmet(question: str) -> bool | None:
    """True for "with helmets", False for "without helmets", None when not asked."""
    q = question.lower()
    if _HELMET_NO.search(q):
        return False
    return True if _HELMET_YES.search(q) else None


def parse_colors(question: str) -> list[str]:
    """Palette colors the question asks for, in order, without repeats ("silver" -> gray)."""
    found = (_COLOR_WORDS[w] for w in _COLOR_RX.findall(question.lower()))
    return list(dict.fromkeys(found))


@dataclass(frozen=True)
class Query:
    """One question, understood.

    `subject` is None when the question names nothing we can look for. `term` is set when the
    subject is an open-vocabulary word ("trees") rather than a built-in detector class.
    """

    subject: Subject | None
    start: float
    end: float
    from_prompt: bool = False  # the time range came from the question, not the video scope
    peak: bool = False  # "busiest minute": name the busiest stretch
    most_common: bool = False  # "most common color": name the top color
    assumed_subject: bool = False  # the question named nothing to count; cars were assumed
    term: str | None = None
    colors: tuple[str, ...] = ()
    helmet: bool | None = None
    breakdown: bool = False  # "what colors...": split the answer by color
    wants_table: bool = False
    silver: bool = False  # the question said "silver" (which we fold into gray)


def relative_window(question: str, duration: float) -> tuple[float, float] | None:
    """ "the last 2 minutes", "the second half" ... resolved against the video length."""
    q = question.lower()
    if m := _LAST_N.search(q):
        n = float(m.group(1)) * (60 if m.group(2).startswith("m") else 1)
    elif m := _LAST_ONE.search(q):
        n = 60.0 if m.group(1) == "minute" else 1.0
    elif m := _FIRST_ONE.search(q):
        return 0.0, min(60.0 if m.group(1) == "minute" else 1.0, duration)
    elif _FIRST_HALF.search(q):
        return 0.0, duration / 2
    elif _SECOND_HALF.search(q):
        return duration / 2, duration
    else:
        return None
    if n <= 0 or n >= duration:
        return None
    return duration - n, duration


def parse_query(question: str, scope: ScopeInfo) -> Query:
    """Rule-based understanding of a question (also the fallback when no LLM is available)."""
    q = question.lower()
    subject = parse_subject(question)
    term: str | None = None
    if subject is None:
        term = extract_term(question)
        if term is not None:
            subject = Subject((term,), term, pluralize(term))
    win = parse_time_window(question, scope)
    start, end, from_prompt = win.start, win.end, win.from_prompt
    if win.beyond is not None:  # asked about a stretch after the video ends: say so, not guess
        start = end = win.beyond
        from_prompt = True
    if not from_prompt and (rel := relative_window(question, scope.duration)):
        start, end, from_prompt = rel[0], rel[1], True
    colors = parse_colors(q)
    most_common = bool(_MOST_COMMON.search(q)) and not colors
    assumed = subject is not None and term is None and not any(rx.search(q) for rx, _ in _SUBJECTS)
    return Query(
        subject=subject,
        start=start,
        end=end,
        from_prompt=from_prompt,
        assumed_subject=assumed,
        peak=bool(_PEAK.search(q)),
        most_common=most_common,
        term=term,
        colors=tuple(colors),
        helmet=parse_helmet(q),
        breakdown=(bool(_WANTS_BREAKDOWN.search(q)) or most_common) and not colors,
        wants_table=bool(_WANTS_TABLE.search(question)),
        silver="silver" in q,
    )
