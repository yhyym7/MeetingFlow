from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    input_id: int
    meeting_id: int
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]
    stage: str
    attempts: int
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    scope: Literal["ANALYSIS_ONLY", "FULL_PIPELINE"]


class AnalysisPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    input_id: int
    mode: str
    summary: str
    decisions: list[str]
    risks: list[str]


class AnalysisAdmin(AnalysisPublic):
    raw_output: str
    resolved_candidates: list[dict]
