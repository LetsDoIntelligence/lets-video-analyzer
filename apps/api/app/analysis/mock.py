"""Simulated analyzer (server-side port of the web mock).

Counts are deterministic fakes derived from the question and scope. This is replaced by the
real detection + query engine in Phases 3-5; the output shape is the contract either way.
"""

import math
import re
from dataclasses import dataclass

from app.analysis.schemas import (
    AnalyzeRequest,
    ChartBlock,
    ChartPoint,
    Reply,
    ReplyBlock,
    ScopeInfo,
    StatBlock,
    TableBlock,
    TableColumn,
    TimestampsBlock,
)


def _round(x: float) -> int:
    """Round half up, like JavaScript's Math.round (Python's round() is banker's)."""
    return math.floor(x + 0.5)


def format_timecode(total_sec: float) -> str:
    s = max(0, _round(total_sec))
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def parse_timecode(text: str) -> float | None:
    """Parse "95", "95s", "1:35" or "1:02:05" into seconds."""
    t = re.sub(r"s$", "", text.strip().lower())
    if not t:
        return None
    parts = t.split(":")
    if len(parts) > 3 or any(not re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


@dataclass(frozen=True)
class Subject:
    singular: str
    plural: str
    per_minute: float  # rough fake detections per minute


_SUBJECTS: list[tuple[re.Pattern[str], Subject]] = [
    (re.compile(r"\b(trucks?|lorr(?:y|ies))\b"), Subject("truck", "trucks", 2)),
    (re.compile(r"\b(people|persons?|pedestrians?|workers?)\b"), Subject("person", "people", 6)),
    (re.compile(r"\btrees?\b"), Subject("tree", "trees", 0.5)),
    (re.compile(r"\bcars?\b"), Subject("car", "cars", 9)),
]
_DEFAULT_SUBJECT = _SUBJECTS[3][1]
_COLORS = ["red", "blue", "white", "black", "yellow", "green", "silver", "grey", "gray"]


@dataclass(frozen=True)
class ParsedPrompt:
    subject: Subject
    color: str | None
    helmets: bool


def parse_prompt(question: str) -> ParsedPrompt:
    q = question.lower()
    subject = next((s for rx, s in _SUBJECTS if rx.search(q)), _DEFAULT_SUBJECT)
    color = next((c for c in _COLORS if re.search(rf"\b{c}\b", q)), None)
    return ParsedPrompt(subject, color, bool(re.search(r"\bhelmets?\b", q)))


_UNIT = r"(sec(?:ond)?s?|s|min(?:ute)?s?|m)"
_FIRST = re.compile(rf"first\s+(\d+(?:\.\d+)?)\s*{_UNIT}\b")
_BETWEEN = re.compile(
    rf"(?:between|from)\s+(\d+(?::\d+)?)\s*(?:and|to|-)\s*(\d+(?::\d+)?)\s*{_UNIT}?(?![a-z])"
)


def _unit_seconds(unit: str | None) -> float | None:
    if not unit:
        return None
    return 60 if unit.startswith("m") else 1


@dataclass(frozen=True)
class Window:
    start: float
    end: float
    from_prompt: bool


def parse_time_window(question: str, scope: ScopeInfo) -> Window:
    """Understands "first 30 sec", "from 3 to 6 minutes", "between 3:00 and 6:00"."""
    q = question.lower()
    fallback = Window(scope.start, scope.end, False)

    if m := _FIRST.search(q):
        length = float(m.group(1)) * (_unit_seconds(m.group(2)) or 1)
        end = min(scope.start + length, scope.end)
        return Window(scope.start, end, True) if end > scope.start else fallback

    if m := _BETWEEN.search(q):
        unit = _unit_seconds(m.group(3))

        def to_seconds(token: str) -> float | None:
            if ":" in token:
                return parse_timecode(token)
            n = float(token)
            if unit:
                return n * unit
            # No unit: minutes if that fits inside the video, otherwise seconds.
            return n * 60 if n * 60 <= scope.duration else n

        a, b = to_seconds(m.group(1)), to_seconds(m.group(2))
        if a is not None and b is not None and b > a:
            start, end = max(0.0, a), min(scope.duration, b)
            if end > start:
                return Window(start, end, True)
    return fallback


def _hash(text: str) -> int:
    """32-bit FNV-1a."""
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


class _Rng:
    """mulberry32, so the same seed gives the same sequence as the web mock."""

    def __init__(self, seed: int) -> None:
        self.s = seed & 0xFFFFFFFF

    def __call__(self) -> float:
        self.s = (self.s + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.s
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = ((t + ((t ^ (t >> 7)) * (61 | t) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296


_BUCKET_SIZES = [5, 10, 15, 30, 60, 120, 300]


def bucket_size(length_sec: float) -> int:
    """Smallest bucket size that keeps the chart at 12 bars or fewer."""
    return next((b for b in _BUCKET_SIZES if math.ceil(length_sec / b) <= 12), 600)


def histogram(times: list[float], start: float, end: float) -> list[ChartPoint]:
    size = bucket_size(end - start)
    n = max(1, math.ceil((end - start) / size))
    points = [
        ChartPoint(label=format_timecode(start + i * size), start=start + i * size, value=0)
        for i in range(n)
    ]
    for t in times:
        idx = min(n - 1, max(0, math.floor((t - start) / size)))
        points[idx].value += 1
    return points


_WANTS_TABLE = re.compile(r"\b(table|list|breakdown|details?|each|show)\b", re.IGNORECASE)


def build_reply(req: AnalyzeRequest) -> Reply:
    scope = req.scope
    parsed = parse_prompt(req.question)
    win = parse_time_window(req.question, scope)
    length = max(win.end - win.start, 1)
    minutes = length / 60

    helmets = str(parsed.helmets).lower()
    seed = _hash(f"{scope.videoId}|{parsed.subject.plural}|{parsed.color or ''}|{helmets}")
    jitter = 0.75 + (seed % 50) / 100  # 0.75 - 1.24
    count = _round(parsed.subject.per_minute * minutes * jitter)
    if parsed.color:
        count = _round(count * 0.25)
    if parsed.helmets:
        count = _round(count * 0.4)

    noun = parsed.subject.singular if count == 1 else parsed.subject.plural
    if parsed.helmets:
        descriptor = f"{parsed.subject.plural} wearing helmets"
    else:
        descriptor = f"{parsed.color + ' ' if parsed.color else ''}{noun}"

    span = f"{format_timecode(win.start)} – {format_timecode(win.end)}"
    where = span if win.from_prompt or scope.label != "Entire video" else "the entire video"

    text = "\n\n".join(
        [
            f"I counted **{count} {descriptor}** in {scope.videoName} ({where}).",
            "Demo mode: these numbers are simulated. Real detection is connected in a later phase.",
        ]
    )

    rand = _Rng(seed ^ _round(win.start * 1000) ^ _round(win.end * 1000))
    times = sorted(
        _round((win.start + rand() * (win.end - win.start)) * 10) / 10 for _ in range(count)
    )

    blocks: list[ReplyBlock] = [
        StatBlock(label=descriptor, value=count, caption=f"{span} · {scope.videoName}")
    ]
    if length >= 20 and count >= 3:
        title = parsed.subject.plural[0].upper() + parsed.subject.plural[1:]
        blocks.append(
            ChartBlock(title=f"{title} over time", data=histogram(times, win.start, win.end))
        )
    if count >= 1:
        blocks.append(TimestampsBlock(label="Jump to first detections", times=times[:6]))
    if count >= 1 and (_WANTS_TABLE.search(req.question) or parsed.color or parsed.helmets):
        if parsed.helmets:
            label = "person · helmet"
        else:
            label = f"{parsed.color + ' ' if parsed.color else ''}{parsed.subject.singular}"
        blocks.append(
            TableBlock(
                title=f"First detections ({min(count, 8)} of {count})",
                columns=[
                    TableColumn(key="n", label="#", kind="number"),
                    TableColumn(key="time", label="Time", kind="time"),
                    TableColumn(key="object", label="Object"),
                    TableColumn(key="confidence", label="Confidence", kind="percent"),
                ],
                rows=[
                    {
                        "n": i + 1,
                        "time": t,
                        "object": label,
                        "confidence": _round((0.8 + rand() * 0.19) * 100) / 100,
                    }
                    for i, t in enumerate(times[:8])
                ],
            )
        )
    return Reply(text=text, blocks=blocks)
