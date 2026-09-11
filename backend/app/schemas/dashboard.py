from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.meetings import MeetingSummary
from app.schemas.tasks import TaskOut


class TaskStatistics(BaseModel):
    total: int
    todo: int
    in_progress: int
    done: int
    overdue: int
    due_today: int


class DashboardOut(BaseModel):
    role: Literal["BOSS", "EMPLOYEE", "MANAGER"]
    as_of: datetime
    timezone: str
    statistics: TaskStatistics
    upcoming_meetings: list[MeetingSummary]
    due_today_tasks: list[TaskOut]
    overdue_tasks: list[TaskOut]
    in_progress_tasks: list[TaskOut]
    pending_supplement_count: int | None = None
