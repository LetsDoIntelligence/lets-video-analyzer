"""Question-understanding evaluation: compare a planner's `Query` with what we expect.

Each case in cases.json names only the fields it cares about; the rest are not checked.
Cases are written for a video that is 84 seconds long, entire video selected.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.analysis.query import Query
from app.analysis.schemas import ScopeInfo

CASES = Path(__file__).with_name("cases.json")
SCOPE = ScopeInfo(
    videoId="eval", videoName="Eval clip", start=0, end=84, duration=84, label="Entire video"
)


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(CASES.read_text(encoding="utf-8"))
    return cases


def mismatches(query: Query, case: dict[str, Any]) -> list[str]:
    """What differs between `query` and the case's expectations (empty list = correct)."""
    bad: list[str] = []

    def check(name: str, got: object, want: object) -> None:
        if got != want:
            bad.append(f"{name}: got {got!r}, want {want!r}")

    if "subject" in case:
        want = case["subject"]
        got = list(query.subject.classes) if query.subject else None
        check("subject", got, want)
    if "term" in case:
        check("term", query.term, case["term"])
    if "colors" in case:
        check("colors", list(query.colors), case["colors"])
    if "helmet" in case:
        check("helmet", query.helmet, case["helmet"])
    window = case.get("window")
    got_window = [query.start, query.end] if query.from_prompt else None
    if "window" in case or query.from_prompt:
        check("window", got_window, window)
    for flag, got in (
        ("peak", query.peak),
        ("most_common", query.most_common),
        ("breakdown", query.breakdown),
        ("table", query.wants_table),
        ("assumed", query.assumed_subject),
    ):
        if flag in case or got:  # a flag nobody asked for is wrong too
            check(flag, got, case.get(flag, False))
    return bad


@dataclass
class Result:
    correct: int = 0
    total: int = 0
    failures: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def evaluate(plan: Callable[[str], Query], cases: list[dict[str, Any]] | None = None) -> Result:
    result = Result()
    for case in cases if cases is not None else load_cases():
        result.total += 1
        try:
            bad = mismatches(plan(case["q"]), case)
        except Exception as e:  # a planner that errors counts as wrong
            bad = [f"raised {type(e).__name__}: {e}"]
        if bad:
            result.failures.append((case["q"], bad))
        else:
            result.correct += 1
    return result
