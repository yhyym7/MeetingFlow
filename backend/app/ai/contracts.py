from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PersonReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ShortText
    department: ShortText | None = None


class AnalysisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    meeting_at: AwareDatetime
    participants: list[PersonReference] = Field(default_factory=list)


class ActionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: ShortText
    description: str | None = Field(default=None, max_length=10000)
    kind: Literal["COMMITTED", "DISCUSSION"]
    owner: PersonReference | None = None
    collaborators: list[PersonReference] = Field(default_factory=list, max_length=100)
    deadline_text: str | None = Field(default=None, max_length=200)
    priority: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    source_quote: str = Field(min_length=1, max_length=10000)


class AnalysisEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=10000)
    decisions: list[str] = Field(max_length=100)
    risks: list[str] = Field(max_length=100)
    # Parse candidates individually: one malformed item must not erase valid work.
    actions: list[Any] = Field(max_length=100)


class ParsedCandidate(BaseModel):
    index: int
    raw: Any
    value: ActionCandidate | None = None
    error: str | None = None


class AnalysisResult(BaseModel):
    mode: str
    summary: str
    decisions: list[str]
    risks: list[str]
    candidates: list[ParsedCandidate]
    raw_output: str
    repaired: bool = False
