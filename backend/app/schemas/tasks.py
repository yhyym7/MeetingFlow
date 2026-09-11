from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import PartialUpdate
from app.schemas.meetings import PersonIds, Title


TaskStatus = Literal["TODO", "IN_PROGRESS", "DONE"]
TaskPriority = Literal["LOW", "NORMAL", "HIGH"]
Membership = Literal["all", "owned", "collaborating"]


def parse_due_at(value):
    if isinstance(value, str) and len(value) == 10:
        value = date.fromisoformat(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time(23, 59), tzinfo=ZoneInfo("Asia/Shanghai"))
    return value


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    description: str | None = Field(default=None, max_length=10000)
    owner_id: int = Field(gt=0)
    collaborator_ids: PersonIds = Field(default_factory=list)
    meeting_id: int | None = Field(default=None, gt=0)
    source_excerpt: str | None = Field(default=None, max_length=10000)
    due_at: AwareDatetime | None = None
    priority: TaskPriority = "NORMAL"
    _parse_due = field_validator("due_at", mode="before")(parse_due_at)


class TaskUpdate(PartialUpdate):
    nullable_fields = {"due_at", "source_excerpt"}
    title: Title | None = None
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    owner_id: int | None = Field(default=None, gt=0)
    collaborator_ids: PersonIds | None = None
    source_excerpt: str | None = Field(default=None, max_length=10000)
    due_at: AwareDatetime | None = None
    priority: TaskPriority | None = None
    _parse_due = field_validator("due_at", mode="before")(parse_due_at)


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: TaskStatus


class ProgressCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("进展内容不能为空")
        return value


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    owner_id: int
    created_by_id: int
    meeting_id: int | None
    source_excerpt: str | None
    due_at: datetime | None
    priority: TaskPriority
    status: TaskStatus
    completed_at: datetime | None
    created_at: datetime
    collaborator_ids: list[int] = Field(default_factory=list)
    source_meeting_title: str | None = None
    can_view_meeting: bool = False
    can_manage: bool = False
    can_update_status: bool = False
    is_overdue: bool = False


class TaskEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    actor_id: int
    event_type: str
    body: str | None
    changes: dict | None
    created_at: datetime
