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

from app.analysis.engine import answer
from app.analysis.mock import build_reply
from app.analysis.schemas import (
    AnalyzeEvent,
    AnalyzeRequest,
    BlocksEvent,
    ErrorEvent,
    Reply,
    TextEvent,
)
from app.config import Settings
from app.jobs.runner import JobRunner
from app.models import JobKind, Video

logger = logging.getLogger("lets.api.analyze")
router = APIRouter(tags=["analyze"])


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(_settings)]


def sse(event: BaseModel) -> str:
    return f"data: {event.model_dump_json(exclude_none=True)}\n\n"


def _reply(req: AnalyzeRequest, factory: sessionmaker[Session], runner: JobRunner) -> Reply:
    """Real answer from the video's index; built-in sample videos (not stored) stay simulated."""
    with factory() as session:
        if session.get(Video, req.scope.videoId) is None:
            return build_reply(req)

        def search(video_id: str) -> None:
            runner.submit(video_id, JobKind.search)

        return answer(session, req, search)


async def _events(
    req: AnalyzeRequest, settings: Settings, factory: sessionmaker[Session], runner: JobRunner
) -> AsyncIterator[AnalyzeEvent]:
    think = settings.analyze_think_ms / 1000
    token = settings.analyze_token_ms / 1000
    await asyncio.sleep(think)
    reply = await run_in_threadpool(_reply, req, factory, runner)
    for chunk in re.findall(r"\S+\s*|\s+", reply.text):
        await asyncio.sleep(token)
        yield TextEvent(chunk=chunk)
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

    async def stream() -> AsyncIterator[str]:
        try:
            async for event in _events(req, settings, factory, runner):
                yield sse(event)
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
