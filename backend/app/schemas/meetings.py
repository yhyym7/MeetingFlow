from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.common import PartialUpdate
from app.schemas.audio import AudioOut


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
PersonIds = Annotated[list[Annotated[int, Field(gt=0)]], Field(max_length=100)]


class MeetingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    starts_at: AwareDatetime
    location: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    participant_ids: PersonIds
    department_ids: PersonIds = Field(default_factory=list)


class MeetingUpdate(PartialUpdate):
    nullable_fields = {"location", "description"}
    title: Title | None = None
    starts_at: AwareDatetime | None = None
    location: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    participant_ids: PersonIds | None = None
    department_ids: PersonIds | None = None


class MeetingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    starts_at: datetime
    location: str | None
    created_by_id: int


class TextInputCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    text: str = Field(min_length=1, max_length=100000)

    @field_validator("text")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("会议原文不能为空")
        return value


class MeetingInputOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    meeting_id: int
    version: int
    text: str
    created_at: datetime
    processing_status: Literal["SAVED", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"] = "SAVED"
    job_id: int | None = None


class DepartmentAttendance(BaseModel):
    department_id: int
    participant_ids: list[int]
    can_arrange: bool


class AttendanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_ids: PersonIds


class MeetingDetail(MeetingSummary):
    can_manage: bool = False
    description: str | None
    participant_ids: list[int]
    direct_participant_ids: list[int] = Field(default_factory=list)
    department_ids: list[int] = Field(default_factory=list)
    department_attendance: list[DepartmentAttendance] = Field(default_factory=list)
    current_input: MeetingInputOut | None
    current_audio: AudioOut | None = None
