from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.ai.resolution import ResolvedCandidate
from app.schemas.meetings import PersonIds, Title
from app.schemas.tasks import TaskPriority, parse_due_at


CandidateStatus = Literal["READY", "NEEDS_INFO", "REJECTED", "DISCUSSION", "REVIEW", "PUBLISHED", "DISMISSED"]


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    analysis_id: int
    position: int
    status: CandidateStatus
    resolved: ResolvedCandidate
    needs_attention: bool
    task_id: int | None = None
    task_deleted: bool = False
    created_at: datetime


class CandidatePublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    description: str | None = Field(default=None, max_length=10000)
    owner_id: int = Field(gt=0)
    collaborator_ids: PersonIds = Field(default_factory=list)
    source_excerpt: str = Field(min_length=1, max_length=10000)
    due_at: AwareDatetime | None = None
    priority: TaskPriority = "NORMAL"
    _parse_due = field_validator("due_at", mode="before")(parse_due_at)


class SupplementCollaborators(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collaborator_ids: PersonIds
