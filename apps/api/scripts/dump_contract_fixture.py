"""Regenerate the contract fixture the web tests validate against the Zod schemas.

python scripts/dump_contract_fixture.py
"""

import json
from pathlib import Path

from app.analysis.mock import build_reply
from app.analysis.schemas import AnalyzeRequest, BlocksEvent, ScopeInfo, TextEvent

OUT = Path(__file__).resolve().parents[2] / "web/src/lib/api/fixtures/analyze-events.json"
QUESTIONS = [
    "how many cars are in the video?",
    "how many red cars between 1:00 and 2:30? show a table",
    "how many people with helmets in the first 30 sec",
    "how many trees",
]

scope = ScopeInfo(
    videoId="sample-1",
    videoName="Synthetic traffic",
    start=0,
    end=600,
    duration=600,
    label="Entire video",
)
streams = []
for q in QUESTIONS:
    reply = build_reply(AnalyzeRequest(question=q, scope=scope))
    events = [TextEvent(chunk=reply.text).model_dump(mode="json")]
    if reply.blocks:
        events.append(BlocksEvent(blocks=reply.blocks).model_dump(mode="json", exclude_none=True))
    streams.append({"question": q, "events": events})

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(streams, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT}")
