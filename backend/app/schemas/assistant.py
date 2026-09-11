from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AssistantQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)


class Source(BaseModel):
    kind: Literal["task", "meeting"]
    id: int
    title: str
    excerpt: str | None = None
    input_id: int | None = None
    input_version: int | None = None
    chunk_id: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None


class AssistantAnswer(BaseModel):
    mode: Literal["demo", "deepseek"] = "demo"
    search_mode: Literal["keyword", "semantic"] | None = None
    answer: str
    sources: list[Source] = Field(default_factory=list)
    tool_calls: int = 0
    trace: list[str] = Field(default_factory=list)
