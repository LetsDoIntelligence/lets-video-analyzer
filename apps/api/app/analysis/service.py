"""Picks how a question is understood: the AI planner when available, else simple rules."""

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

from app.analysis.planner import OpenAIPlanner, PlanError, Planner
from app.analysis.query import Query, parse_query
from app.analysis.schemas import ScopeInfo
from app.config import Settings

logger = logging.getLogger("lets.planner")

FALLBACK_NOTE = (
    "The AI question planner wasn't available just now, so I read your question with a simpler "
    "method. It can miss unusual wording."
)

CacheKey = tuple[str, str, float, float, float]


@dataclass(frozen=True)
class Planned:
    query: Query
    fallback: bool = False  # the AI planner was expected but failed; rules were used instead


class QueryPlanner:
    """Turns questions into `Query`s.

    - `rules`: the simple parser only.
    - `auto`: the AI planner when configured; on any failure fall back to the rules.
    - `llm`: the AI planner only; failures raise `PlanError`.

    Successful AI plans are cached (the same question over the same video and range is
    answered the same way, and costs nothing the second time).
    """

    def __init__(self, mode: str, llm: Planner | None = None, cache_size: int = 256) -> None:
        self.mode = mode
        self.llm = None if mode == "rules" else llm
        self._cache: OrderedDict[CacheKey, Query] = OrderedDict()
        self._size = cache_size
        self._lock = threading.Lock()

    @property
    def uses_llm(self) -> bool:
        return self.llm is not None

    def plan(self, question: str, scope: ScopeInfo) -> Planned:
        if self.llm is None:
            return Planned(parse_query(question, scope))
        key: CacheKey = (
            question.strip().lower(),
            scope.videoId,
            scope.start,
            scope.end,
            scope.duration,
        )
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return Planned(hit)
        try:
            query = self.llm.plan(question, scope)
        except PlanError as e:
            logger.warning("planner failed (%s); mode=%s", e, self.mode)
            if self.mode == "llm":
                raise
            return Planned(parse_query(question, scope), fallback=True)
        with self._lock:
            self._cache[key] = query
            while len(self._cache) > self._size:
                self._cache.popitem(last=False)
        return Planned(query)


def make_planner(settings: Settings) -> QueryPlanner:
    """The planner for this server's settings (the AI one needs `OPENAI_API_KEY`)."""
    llm: Planner | None = None
    if settings.planner != "rules":
        if settings.openai_api_key:
            llm = OpenAIPlanner(
                settings.openai_api_key, settings.planner_model, timeout=settings.planner_timeout
            )
        else:
            logger.info("no OPENAI_API_KEY: questions are read with the simple parser")
    return QueryPlanner(settings.planner, llm)
