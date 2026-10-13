"""Answer questions from the stored detection/tracking index (no model runs per question).

Question understanding lives in query.py (rules now, an LLM planner in Phase 5, both
producing a `Query`); everything after parsing - counting, charts, tables - is here.
"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.mock import format_timecode, histogram
from app.analysis.query import Query, Subject, parse_query
from app.analysis.schemas import (
    AnalyzeRequest,
    CategoriesBlock,
    CategoryPoint,
    ChartBlock,
    Reply,
    ReplyBlock,
    StatBlock,
    TableBlock,
    TableColumn,
    TimestampsBlock,
)
from app.models import Job, JobKind, SearchStatus, TrackRecord
from app.schemas import IndexState
from app.vision import store
from app.vision.color import VEHICLES
from app.vision.status import index_out
from app.vision.vocab import pluralize

SUPPORTED = "cars, trucks, buses, motorcycles, bicycles, people, or vehicles in general"
OPEN_VOCAB_NOTE = (
    "This comes from an open-vocabulary search, which is less precise than the built-in "
    "detectors, so treat the number as a rough guide."
)
# Asks the server to start searching a video for a new term (raises ValueError if it can't).
Searcher = Callable[[str], None]
HELMET_CAVEAT = (
    "Helmets are judged by an AI vision model from a couple of frames per person, so far-away "
    "or partly hidden people can be missed."
)
COLOR_CAVEAT = (
    "Colors are estimated from the footage, so similar shades (dark blue vs. black, "
    "silver vs. gray) can blur."
)


def _noun(subject: Subject, count: int) -> str:
    return subject.singular if count == 1 else subject.plural


def _round1(x: float) -> float:
    return round(x * 10) / 10


def _color(track: TrackRecord) -> str | None:
    value = (track.attrs or {}).get("color")
    return value if isinstance(value, str) else None


def answer(
    session: Session,
    req: AnalyzeRequest,
    searcher: Searcher | None = None,
    query: Query | None = None,
) -> Reply:
    """Build the reply for a video that exists in the database.

    Things the fixed detector can't see ("trees") are searched for in the background when a
    `searcher` is given; the reply says so, and asking again answers from the stored result.
    `query` is what the question means; when omitted it is worked out with simple rules.
    """
    scope = req.scope
    state = index_out(session, scope.videoId)
    if state.state is not IndexState.ready:
        return Reply(text=_not_ready(state.state, state.progress, state.error), blocks=[])

    query = query or parse_query(req.question, scope)
    subject = query.subject
    if subject is None:
        return _unsupported()
    open_vocab = query.term is not None
    if query.term is not None:
        waiting = _search_status(session, req, query.term, searcher)
        if waiting is not None:
            return waiting

    win = query  # start / end / from_prompt
    tracks = store.query_tracks(
        session, scope.videoId, cls=list(subject.classes), t_from=win.start, t_to=win.end
    )
    notes: list[str] = [OPEN_VOCAB_NOTE] if open_vocab else []

    # Colors only exist for vehicles; ignore them (and say so) for anything else.
    colors, breakdown = list(query.colors), query.breakdown
    colorable = set(subject.classes) <= VEHICLES
    if (colors or breakdown) and not colorable:
        notes.append(f"I only estimate colors for vehicles, so this counts all {subject.plural}.")
        colors, breakdown = [], False

    # Helmets are only judged on people, and only when the helmet check ran on this video.
    helmet = query.helmet
    helmet_notes: list[str] = []
    if helmet is not None:
        if set(subject.classes) != {"person"}:
            helmet_notes.append(
                f"I only check helmets on people, so this counts all {subject.plural}."
            )
            helmet = None
        elif not any("helmet" in (t.attrs or {}) for t in tracks):
            helmet_notes.append(
                "The helmet check isn't available for this video (it needs an OpenAI key and "
                "a re-analysis), so this counts everyone."
            )
            helmet = None

    label = subject.plural
    unknown = 0
    if helmet is not None:
        no_verdict = sum(1 for t in tracks if "helmet" not in (t.attrs or {}))
        tracks = [t for t in tracks if (t.attrs or {}).get("helmet") is helmet]
        label = f"people {'with' if helmet else 'without'} a helmet"
        helmet_notes.append(HELMET_CAVEAT)
        if no_verdict:
            helmet_notes.append(
                f"{no_verdict} other {'person' if no_verdict == 1 else 'people'} were too small "
                "or unclear to judge and are not counted."
            )

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
    notes += helmet_notes

    if count == 0:
        text = f"I didn't find any {label} in {scope.videoName} ({where})."
    else:
        text = f"I counted **{count} {shown_noun(count)}** in {scope.videoName} ({where})."
    paragraphs = [text, *notes]
    if query.silver:
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
        blocks.append(color_chart(tracks, label))
        blocks.append(_by_color(tracks))
    if count and query.wants_table:
        blocks.append(_detections_table(entries, count))
    return Reply(text="\n\n".join(paragraphs), blocks=blocks)


def _unsupported() -> Reply:
    return Reply(
        text=f"I can't detect that yet. Right now I can count {SUPPORTED}.",
        blocks=[],
    )


def _search_status(
    session: Session, req: AnalyzeRequest, term: str, searcher: Searcher | None
) -> Reply | None:
    """Reply for a term that is not searched yet / still being searched; None when it is done."""
    vid, plural = req.scope.videoId, pluralize(term)
    row = store.get_search(session, vid, term)
    if row is not None and row.status == SearchStatus.done:
        return None
    if row is not None and row.status in (SearchStatus.pending, SearchStatus.running):
        job = session.scalars(
            select(Job)
            .where(Job.video_id == vid, Job.kind == JobKind.search)
            .order_by(Job.created_at.desc())
        ).first()
        pct = f" ({round(job.progress * 100)}%)" if job and job.progress else ""
        return Reply(
            text=f"I'm still searching {req.scope.videoName} for {plural}{pct}. "
            "Ask again in a moment.",
            blocks=[],
        )
    if searcher is None:
        return _unsupported()
    previous = row.error if row is not None else None  # a failed earlier attempt
    store.request_search(session, vid, term)
    try:
        searcher(vid)
    except ValueError:  # this server has no open-vocabulary search
        session.delete(store.get_search(session, vid, term))
        session.commit()
        return _unsupported()
    retry = f" The last attempt failed ({previous}); trying again." if previous else ""
    return Reply(
        text=f"I don't have a built-in detector for {plural}, so I'm searching "
        f"{req.scope.videoName} for them now.{retry} This takes a short while, so ask again in "
        "a moment and I'll answer from what it finds.",
        blocks=[],
    )


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


def _color_counts(tracks: list[TrackRecord]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for t in tracks:
        name = _color(t) or "unknown"
        counts[name] = counts.get(name, 0) + 1
    # Unknown goes last whatever its size; the rest by count.
    return sorted(counts.items(), key=lambda kv: (kv[0] == "unknown", -kv[1], kv[0]))


def color_chart(tracks: list[TrackRecord], noun: str) -> CategoriesBlock:
    title = noun[0].upper() + noun[1:]
    return CategoriesBlock(
        title=f"{title} by color",
        data=[CategoryPoint(label=c, value=n) for c, n in _color_counts(tracks)],
    )


def _by_color(tracks: list[TrackRecord]) -> TableBlock:
    total = len(tracks)
    order = _color_counts(tracks)
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
