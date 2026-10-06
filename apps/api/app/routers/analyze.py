import asyncio
import logging
import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.analysis.mock import build_reply
from app.analysis.schemas import AnalyzeEvent, AnalyzeRequest, BlocksEvent, ErrorEvent, TextEvent
from app.config import Settings

logger = logging.getLogger("lets.api.analyze")
router = APIRouter(tags=["analyze"])


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(_settings)]


def sse(event: BaseModel) -> str:
    return f"data: {event.model_dump_json(exclude_none=True)}\n\n"


async def _events(req: AnalyzeRequest, settings: Settings) -> AsyncIterator[AnalyzeEvent]:
    think = settings.analyze_think_ms / 1000
    token = settings.analyze_token_ms / 1000
    await asyncio.sleep(think)
    reply = build_reply(req)
    for chunk in re.findall(r"\S+\s*|\s+", reply.text):
        await asyncio.sleep(token)
        yield TextEvent(chunk=chunk)
    if reply.blocks:
        await asyncio.sleep(min(token * 8, 0.3))
        yield BlocksEvent(blocks=reply.blocks)


@router.post("/analyze")
async def analyze(req: AnalyzeRequest, settings: SettingsDep) -> StreamingResponse:
    """Answer a question about a video as a Server-Sent Events stream.

    Currently simulated (see app/analysis/mock.py); the contract is final.
    """

    async def stream() -> AsyncIterator[str]:
        try:
            async for event in _events(req, settings):
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
