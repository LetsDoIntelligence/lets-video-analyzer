"""Answer questions from the stored detection/tracking index (no model runs per question).

Question understanding is rule-based for now (Phase 5 replaces it with an LLM planner that
produces the same `Query`); everything after parsing - counting, charts, tables - is final.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.analysis.mock import format_timecode, histogram, parse_time_window
from app.analysis.schemas import (
    AnalyzeRequest,
    ChartBlock,
    Reply,
    ReplyBlock,
    StatBlock,
    TableBlock,
    TableColumn,
    TimestampsBlock,
)
from app.models import TrackRecord
from app.schemas import IndexState
from app.vision import store
from app.vision.status import index_out


@dataclass(frozen=True)
class Subject:
    classes: tuple[str, ...]  # detector classes that count as this subject
    singular: str
    plural: str


_CAR = Subject(("car",), "car", "cars")
_VEHICLE = Subject(("car", "truck", "bus", "motorcycle"), "vehicle", "vehicles")

_SUBJECTS: list[tuple[re.Pattern[str], Subject]] = [
    (re.compile(r"\b(vehicles?|traffic)\b"), _VEHICLE),
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
_HOW_MANY = re.compile(r"\bhow many (?:\w+ )?(\w+)")
_GENERIC = {"objects", "things", "items", "times", "of", "are", "were", "in"}
_COLORS = ["red", "blue", "white", "black", "yellow", "green", "silver", "grey", "gray"]
_WANTS_TABLE = re.compile(r"\b(table|list|breakdown|details?|each|show)\b", re.IGNORECASE)

SUPPORTED = "cars, trucks, buses, motorcycles, bicycles, people, or vehicles in general"


def parse_subject(question: str) -> Subject | None:
    """Which detected class the question is about; None if it asks about something we can't see."""
    q = question.lower()
    for rx, subject in _SUBJECTS:
        if rx.search(q):
            return subject
    m = _HOW_MANY.search(q)
    if m and m.group(1) not in _GENERIC:
        return None
    return _CAR  # e.g. "show me everything in the first minute": default to cars


def _noun(subject: Subject, count: int) -> str:
    return subject.singular if count == 1 else subject.plural


def _round1(x: float) -> float:
    return round(x * 10) / 10


def answer(session: Session, req: AnalyzeRequest) -> Reply:
    """Build the reply for a video that exists in the database."""
    scope = req.scope
    state = index_out(session, scope.videoId)
    if state.state is not IndexState.ready:
        return Reply(text=_not_ready(state.state, state.progress, state.error), blocks=[])

    subject = parse_subject(req.question)
    if subject is None:
        return Reply(
            text=f"I can't detect that yet. Right now I can count {SUPPORTED}.",
            blocks=[],
        )

    win = parse_time_window(req.question, scope)
    tracks = store.query_tracks(
        session, scope.videoId, cls=list(subject.classes), t_from=win.start, t_to=win.end
    )
    # A track that was already on screen when the window opened "enters" at the window start.
    entries = [(max(t.t_in, win.start), t) for t in tracks]
    entries.sort(key=lambda e: e[0])
    times = [_round1(e[0]) for e in entries]
    count = len(entries)

    span = f"{format_timecode(win.start)} – {format_timecode(win.end)}"
    where = span if win.from_prompt or scope.label != "Entire video" else "the entire video"
    q = req.question.lower()
    notes = _limitations(q, subject)

    if count == 0:
        text = f"I didn't find any {subject.plural} in {scope.videoName} ({where})."
    else:
        text = f"I counted **{count} {_noun(subject, count)}** in {scope.videoName} ({where})."
    paragraphs = [text, *notes]
    if count:
        paragraphs.append(
            "Each one is detected and tracked once; if something is hidden for a while and "
            "reappears it can occasionally be counted twice."
        )

    blocks: list[ReplyBlock] = [
        StatBlock(label=_noun(subject, count), value=count, caption=f"{span} · {scope.videoName}")
    ]
    if count and win.end - win.start >= 20 and count >= 3:
        title = subject.plural[0].upper() + subject.plural[1:]
        blocks.append(
            ChartBlock(title=f"{title} over time", data=histogram(times, win.start, win.end))
        )
    if count:
        blocks.append(TimestampsBlock(label="Jump to first detections", times=times[:6]))
    if count and len(subject.classes) > 1:
        blocks.append(_by_type(tracks))
    if count and _WANTS_TABLE.search(req.question):
        blocks.append(_detections_table(entries, count))
    return Reply(text="\n\n".join(paragraphs), blocks=blocks)


def _limitations(q: str, subject: Subject) -> list[str]:
    """Be upfront about filters we can't apply yet instead of silently ignoring them."""
    notes = []
    if any(re.search(rf"\b{c}\b", q) for c in _COLORS):
        notes.append(f"I can't tell colors apart yet, so this counts all {subject.plural}.")
    if re.search(r"\bhelmets?\b", q):
        notes.append("I can't check for helmets yet, so this counts everyone.")
    return notes


def _not_ready(state: IndexState, progress: float, error: str | None) -> str:
    if state in (IndexState.queued, IndexState.running):
        pct = round(progress * 100)
        return f"This video is still being analyzed ({pct}%). Ask again in a moment."
    if state is IndexState.failed:
        reason = f" ({error})" if error else ""
        return (
            f"The analysis of this video failed{reason}. "
            "Use the retry button next to the video's status to run it again."
        )
    return (
        "This video hasn't been analyzed yet. Analysis starts automatically after upload; "
        "use the analyze button next to the video's status to start it."
    )


def _by_type(tracks: list[TrackRecord]) -> TableBlock:
    counts: dict[str, int] = {}
    for t in tracks:
        counts[t.cls] = counts.get(t.cls, 0) + 1
    rows = [{"type": cls, "count": n} for cls, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    return TableBlock(
        title="By type",
        columns=[
            TableColumn(key="type", label="Type"),
            TableColumn(key="count", label="Count", kind="number"),
        ],
        rows=rows,
    )


def _detections_table(entries: list[tuple[float, TrackRecord]], count: int) -> TableBlock:
    shown = entries[:8]
    return TableBlock(
        title=f"First detections ({len(shown)} of {count})",
        columns=[
            TableColumn(key="n", label="#", kind="number"),
            TableColumn(key="time", label="Time", kind="time"),
            TableColumn(key="object", label="Object"),
            TableColumn(key="confidence", label="Confidence", kind="percent"),
        ],
        rows=[
            {
                "n": i + 1,
                "time": _round1(entry),
                "object": track.cls,
                "confidence": round(track.confidence, 2),
            }
            for i, (entry, track) in enumerate(shown)
        ],
    )
