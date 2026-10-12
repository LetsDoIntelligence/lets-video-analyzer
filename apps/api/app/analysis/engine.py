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
from app.vision.color import COLOR_NAMES, VEHICLES
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
# Words people use for the colors the extractor can name (silver is folded into gray).
_COLOR_WORDS = {name: name for name in COLOR_NAMES} | {"silver": "gray", "grey": "gray"}
_COLOR_RX = re.compile(r"\b(" + "|".join(_COLOR_WORDS) + r")\b")
_WANTS_BREAKDOWN = re.compile(r"\b(by colou?rs?|what colou?rs?|which colou?rs?|colou?rs?)\b")
_WANTS_TABLE = re.compile(r"\b(table|list|breakdown|details?|each|show)\b", re.IGNORECASE)

SUPPORTED = "cars, trucks, buses, motorcycles, bicycles, people, or vehicles in general"
COLOR_CAVEAT = (
    "Colors are estimated from the footage, so similar shades (dark blue vs. black, "
    "silver vs. gray) can blur."
)


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


def parse_colors(question: str) -> list[str]:
    """Palette colors the question asks for, in order, without repeats ("silver" -> gray)."""
    found = (_COLOR_WORDS[w] for w in _COLOR_RX.findall(question.lower()))
    return list(dict.fromkeys(found))


def _noun(subject: Subject, count: int) -> str:
    return subject.singular if count == 1 else subject.plural


def _round1(x: float) -> float:
    return round(x * 10) / 10


def _color(track: TrackRecord) -> str | None:
    return (track.attrs or {}).get("color")


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
    q = req.question.lower()
    notes: list[str] = []

    # Colors only exist for vehicles; ignore them (and say so) for anything else.
    colors = parse_colors(q)
    breakdown = bool(_WANTS_BREAKDOWN.search(q)) and not colors
    colorable = set(subject.classes) <= VEHICLES
    if (colors or breakdown) and not colorable:
        notes.append(f"I only estimate colors for vehicles, so this counts all {subject.plural}.")
        colors, breakdown = [], False

    label = subject.plural
    unknown = 0
    if colors:
        unknown = sum(1 for t in tracks if _color(t) is None)
        tracks = [t for t in tracks if _color(t) in colors]
        label = " or ".join(colors) + " " + subject.plural

    def shown_noun(n: int) -> str:
        return label if n != 1 else label.replace(subject.plural, subject.singular)

    # A track that was already on screen when the window opened "enters" at the window start.
    entries = [(max(t.t_in, win.start), t) for t in tracks]
    entries.sort(key=lambda e: e[0])
    times = [_round1(e[0]) for e in entries]
    count = len(entries)

    span = f"{format_timecode(win.start)} – {format_timecode(win.end)}"
    where = span if win.from_prompt or scope.label != "Entire video" else "the entire video"
    notes += _limitations(q)

    if count == 0:
        text = f"I didn't find any {label} in {scope.videoName} ({where})."
    else:
        text = f"I counted **{count} {shown_noun(count)}** in {scope.videoName} ({where})."
    paragraphs = [text, *notes]
    if "silver" in q:
        paragraphs.append("Silver and gray are treated as one color (gray).")
    if unknown:
        paragraphs.append(
            f"{unknown} other {subject.plural} in this window had no clear color and are not "
            "counted."
        )
    if colors or breakdown:
        paragraphs.append(COLOR_CAVEAT)
    if count:
        paragraphs.append(
            "Each one is detected and tracked once; if something is hidden for a while and "
            "reappears it can occasionally be counted twice."
        )

    blocks: list[ReplyBlock] = [
        StatBlock(label=shown_noun(count), value=count, caption=f"{span} · {scope.videoName}")
    ]
    if count and win.end - win.start >= 20 and count >= 3:
        title = label[0].upper() + label[1:]
        blocks.append(
            ChartBlock(title=f"{title} over time", data=histogram(times, win.start, win.end))
        )
    if count:
        blocks.append(
            TimestampsBlock(label="Jump to first detections", times=list(dict.fromkeys(times))[:6])
        )
    if count and len(subject.classes) > 1:
        blocks.append(_by_type(tracks))
    if count and (breakdown or len(colors) > 1):
        blocks.append(_by_color(tracks))
    if count and _WANTS_TABLE.search(req.question):
        blocks.append(_detections_table(entries, count))
    return Reply(text="\n\n".join(paragraphs), blocks=blocks)


def _limitations(q: str) -> list[str]:
    """Be upfront about filters we can't apply yet instead of silently ignoring them."""
    notes = []
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


def _by_color(tracks: list[TrackRecord]) -> TableBlock:
    counts: dict[str, int] = {}
    for t in tracks:
        name = _color(t) or "unknown"
        counts[name] = counts.get(name, 0) + 1
    total = len(tracks)
    # Unknown goes last whatever its size; the rest by count.
    order = sorted(counts.items(), key=lambda kv: (kv[0] == "unknown", -kv[1], kv[0]))
    return TableBlock(
        title="By color",
        columns=[
            TableColumn(key="color", label="Color"),
            TableColumn(key="count", label="Count", kind="number"),
            TableColumn(key="share", label="Share", kind="percent"),
        ],
        rows=[{"color": c, "count": n, "share": round(n / total, 2)} for c, n in order],
    )


def _detections_table(entries: list[tuple[float, TrackRecord]], count: int) -> TableBlock:
    shown = entries[:8]
    with_color = any(_color(t) for _, t in shown)
    columns = [
        TableColumn(key="n", label="#", kind="number"),
        TableColumn(key="time", label="Time", kind="time"),
        TableColumn(key="object", label="Object"),
    ]
    if with_color:
        columns.append(TableColumn(key="color", label="Color"))
    columns.append(TableColumn(key="confidence", label="Confidence", kind="percent"))
    rows: list[dict[str, str | float]] = []
    for i, (entry, track) in enumerate(shown):
        row: dict[str, str | float] = {
            "n": i + 1,
            "time": _round1(entry),
            "object": track.cls,
        }
        if with_color:
            row["color"] = _color(track) or "—"
        row["confidence"] = round(track.confidence, 2)
        rows.append(row)
    return TableBlock(
        title=f"First detections ({len(shown)} of {count})", columns=columns, rows=rows
    )
