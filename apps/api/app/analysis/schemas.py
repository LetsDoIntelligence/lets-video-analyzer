"""Pydantic mirror of the analyzer contract (apps/web/src/lib/api/schemas.ts).

Field names are camelCase on purpose: they are the wire format, not Python style.
"""

# ruff: noqa: N815
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class ScopeInfo(BaseModel):
    videoId: str = Field(min_length=1)
    videoName: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)
    label: str

    @model_validator(mode="after")
    def _ordered(self) -> "ScopeInfo":
        if self.end < self.start:
            raise ValueError("scope.end must not be before scope.start")
        return self


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    scope: ScopeInfo

    @model_validator(mode="after")
    def _strip(self) -> "AnalyzeRequest":
        self.question = self.question.strip()
        if not self.question:
            raise ValueError("question must not be blank")
        return self


class StatBlock(BaseModel):
    type: Literal["stat"] = "stat"
    label: str
    value: float
    caption: str | None = None


class ChartPoint(BaseModel):
    label: str
    start: float
    value: float


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    title: str
    data: list[ChartPoint]


class TableColumn(BaseModel):
    key: str
    label: str
    kind: Literal["text", "number", "time", "percent"] | None = None


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[TableColumn]
    rows: list[dict[str, str | float]]


class TimestampsBlock(BaseModel):
    type: Literal["timestamps"] = "timestamps"
    label: str
    times: list[float]


ReplyBlock = Annotated[
    StatBlock | ChartBlock | TableBlock | TimestampsBlock, Field(discriminator="type")
]


class TextEvent(BaseModel):
    type: Literal["text"] = "text"
    chunk: str


class BlocksEvent(BaseModel):
    type: Literal["blocks"] = "blocks"
    blocks: list[ReplyBlock]


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


AnalyzeEvent = TextEvent | BlocksEvent | ErrorEvent


class Reply(BaseModel):
    text: str
    blocks: list[ReplyBlock]
