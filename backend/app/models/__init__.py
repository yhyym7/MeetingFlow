"""Register models here so Alembic sees the complete implemented schema."""

from app.models.auth import AuthSession
from app.models.analysis import AnalysisRecord, ProcessingJob
from app.models.base import Base
from app.models.candidates import ActionItem
from app.models.meetings import Meeting, MeetingInput, MeetingParticipant, MeetingDepartment, MeetingDepartmentParticipant
from app.models.people import Department, User
from app.models.tasks import Task, TaskCollaborator, TaskEvent
from app.models.knowledge import MeetingChunk
from app.models.audio import MeetingAudio

__all__ = [
    "AuthSession", "Base", "Department", "Meeting", "MeetingInput", "MeetingParticipant",
    "Task", "TaskCollaborator", "TaskEvent", "User", "AnalysisRecord", "ProcessingJob", "ActionItem",
    "MeetingDepartment", "MeetingDepartmentParticipant",
    "MeetingChunk",
    "MeetingAudio",
]
