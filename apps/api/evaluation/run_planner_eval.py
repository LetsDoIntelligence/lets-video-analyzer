"""Score the question planners on evaluation/cases.json.

    python -m evaluation.run_planner_eval          # rules, plus the AI planner if a key is set
    python -m evaluation.run_planner_eval --rules  # offline, no API calls

The AI run makes one OpenAI call per case (about 40) and prints the cost.
"""

import sys
import time

from app.analysis.planner import OpenAIPlanner, PlanError
from app.analysis.query import Query, parse_query
from app.config import Settings

from .compare import SCOPE, Result, evaluate

# gpt-4o-mini list prices, USD per million tokens (used only for the estimate printed here).
PRICE_IN, PRICE_OUT = 0.15, 0.60


def show(name: str, result: Result) -> None:
    print(f"\n== {name}: {result.correct}/{result.total} correct ({result.accuracy:.0%})")
    for question, bad in result.failures:
        print(f"  x {question!r}")
        for line in bad:
            print(f"      {line}")


def main() -> int:
    only_rules = "--rules" in sys.argv
    show("rules", evaluate(lambda q: parse_query(q, SCOPE)))
    settings = Settings()
    if only_rules or not settings.openai_api_key:
        if not only_rules:
            print("\n(no OPENAI_API_KEY: skipped the AI planner)")
        return 0

    planner = OpenAIPlanner(settings.openai_api_key, settings.planner_model)
    times: list[float] = []

    def plan(question: str) -> Query:
        start = time.perf_counter()
        try:
            return planner.plan(question, SCOPE)
        finally:
            times.append(time.perf_counter() - start)

    result = evaluate(plan)
    show(f"AI planner ({settings.planner_model})", result)
    n = max(len(times), 1)
    cost = planner.prompt_tokens / 1e6 * PRICE_IN + planner.completion_tokens / 1e6 * PRICE_OUT
    print(
        f"\nlatency: mean {sum(times) / n:.2f}s, max {max(times, default=0):.2f}s"
        f" | tokens: {planner.prompt_tokens} in / {planner.completion_tokens} out"
        f" | cost: ~${cost:.4f} total, ~${cost / n:.5f} per question"
    )
    _ = PlanError  # imported so a failing call shows up as a wrong answer, not a crash
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
