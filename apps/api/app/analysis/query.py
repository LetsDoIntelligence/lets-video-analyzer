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
    (re.compile(r"\bcars?\b"), _CAR),
]
# Words people use for the colors the extractor can name (silver is folded into gray).
_COLOR_WORDS = {name: name for name in COLOR_NAMES} | {"silver": "gray", "grey": "gray"}
_COLOR_RX = re.compile(r"\b(" + "|".join(_COLOR_WORDS) + r")\b")
_WANTS_BREAKDOWN = re.compile(r"\b(by colou?rs?|what colou?rs?|which colou?rs?|colou?rs?)\b")
_HELMET_NO = re.compile(
    r"\b(without|no|not wearing|missing|lacking)\s+(a\s+|any\s+)?(helmets?|hard ?hats?)\b"
)
_HELMET_YES = re.compile(r"\b(helmets?|helmeted|hard ?hats?)\b")
_WANTS_TABLE = re.compile(r"\b(table|list|breakdown|details?|each|show)\b", re.IGNORECASE)


def parse_subject(question: str) -> Subject | None:
    """Which detected class the question is about; None if it asks about something we can't see."""
    q = question.lower()
    for rx, subject in _SUBJECTS:
        if rx.search(q):
            return subject
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
    term: str | None = None
    colors: tuple[str, ...] = ()
    helmet: bool | None = None
    breakdown: bool = False  # "what colors...": split the answer by color
    wants_table: bool = False
    silver: bool = False  # the question said "silver" (which we fold into gray)


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
    colors = parse_colors(q)
    return Query(
        subject=subject,
        start=win.start,
        end=win.end,
        from_prompt=win.from_prompt,
        term=term,
        colors=tuple(colors),
        helmet=parse_helmet(q),
        breakdown=bool(_WANTS_BREAKDOWN.search(q)) and not colors,
        wants_table=bool(_WANTS_TABLE.search(question)),
        silver="silver" in q,
    )
