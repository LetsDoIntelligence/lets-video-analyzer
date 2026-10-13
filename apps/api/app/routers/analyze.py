import asyncio
import logging
import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.engine import PendingReply, answer
from app.analysis.mock import build_reply
from app.analysis.planner import PlanError
from app.analysis.schemas import (
    AnalyzeEvent,
    AnalyzeRequest,
    BlocksEvent,
    ErrorEvent,
    Reply,
    TextEvent,
)
from app.analysis.service import FALLBACK_NOTE, Planned, QueryPlanner
from app.config import Settings
from app.jobs.runner import JobRunner
from app.models import JobKind, SearchStatus, Video
from app.schemas import IndexState
from app.vision import store
from app.vision.status import index_out

logger = logging.getLogger("lets.api.analyze")
router = APIRouter(tags=["analyze"])


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(_settings)]


def sse(event: BaseModel) -> str:
    return f"data: {event.model_dump_json(exclude_none=True)}\n\n"


def _reply(
    req: AnalyzeRequest,
    factory: sessionmaker[Session],
    runner: JobRunner,
    planner: QueryPlanner,
) -> Reply:
    """Real answer from the video's index; built-in sample videos (not stored) stay simulated."""
    with factory() as session:
        if session.get(Video, req.scope.videoId) is None:
            return build_reply(req)

        def search(video_id: str) -> None:
            runner.submit(video_id, JobKind.search)

        planned: Planned | None = None
        # Only ask the AI planner when there is something to answer from.
        if index_out(session, req.scope.videoId).state is IndexState.ready:
            try:
                planned = planner.plan(req.question, req.scope)
            except PlanError:
                return Reply(
                    text="I couldn't work out that question just now. Please try again.",
                    blocks=[],
                )
        reply = answer(session, req, search, planned.query if planned else None)
        if planned is not None and planned.fallback:
            reply = Reply(text=f"{reply.text}\n\n{FALLBACK_NOTE}", blocks=reply.blocks)
        return reply


ASK_AGAIN = " Ask again in a moment and I'll answer from what it finds."
SLOW_SEARCH = "\n\nThe search is taking longer than expected." + ASK_AGAIN
POLL_SECONDS = 1.0


def _search_over(factory: sessionmaker[Session], video_id: str, term: str) -> bool:
    """True once the background search for `term` has finished (successfully or not)."""
    with factory() as session:
        row = store.get_search(session, video_id, term)
        return row is None or row.status in (SearchStatus.done, SearchStatus.failed)


def _chunks(text: str) -> list[str]:
    return re.findall(r"\S+\s*|\s+", text)


async def _events(
    req: AnalyzeRequest,
    settings: Settings,
    factory: sessionmaker[Session],
    runner: JobRunner,
    planner: QueryPlanner,
) -> AsyncIterator[AnalyzeEvent | None]:
    """The answer as events; `None` is a keep-alive while a background search is awaited."""
    think = settings.analyze_think_ms / 1000
    token = settings.analyze_token_ms / 1000
    await asyncio.sleep(think)
    reply = await run_in_threadpool(_reply, req, factory, runner, planner)
    for chunk in _chunks(reply.text):
        await asyncio.sleep(token)
        yield TextEvent(chunk=chunk)

    if isinstance(reply, PendingReply):
        # A new word is being searched for. Hold the answer open until the search ends
        # instead of making the user ask twice.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settings.search_wait_s
        over = False
        while not over and loop.time() < deadline:
            await asyncio.sleep(POLL_SECONDS)
            yield None
            over = await run_in_threadpool(_search_over, factory, req.scope.videoId, reply.term)
        if not over:
            yield TextEvent(chunk=SLOW_SEARCH if settings.search_wait_s > 0 else ASK_AGAIN)
            return
        yield TextEvent(chunk="\n\n")
        reply = await run_in_threadpool(_reply, req, factory, runner, planner)
        for chunk in _chunks(reply.text):
            await asyncio.sleep(token)
            yield TextEvent(chunk=chunk)
        if isinstance(reply, PendingReply):  # a failed search was restarted
            yield TextEvent(chunk=ASK_AGAIN)
            return

    if reply.blocks:
        await asyncio.sleep(min(token * 8, 0.3))
        yield BlocksEvent(blocks=reply.blocks)


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest, request: Request, settings: SettingsDep
) -> StreamingResponse:
    """Answer a question about a video as a Server-Sent Events stream.

    Uploaded videos are answered from their detection/tracking index (app/analysis/engine.py);
    built-in sample videos have no footage and get simulated answers (app/analysis/mock.py).
    """
    factory: sessionmaker[Session] = request.app.state.session_factory
    runner: JobRunner = request.app.state.jobs
    planner: QueryPlanner = request.app.state.planner

    async def stream() -> AsyncIterator[str]:
        try:
            async for event in _events(req, settings, factory, runner, planner):
                yield ": keep-alive\n\n" if event is None else sse(event)
        except asyncio.CancelledError:
            raise  # client went away
        except Exception:
            logger.exception("analyze failed")
            yield sse(ErrorEvent(message="Something went wrong while analysing this video."))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
