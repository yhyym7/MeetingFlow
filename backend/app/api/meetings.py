from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from app.models import MeetingChunk
from app.schemas.assistant import Source

from app.api.dependencies import CurrentUser, Database
from app.permissions import get_meeting_or_404
from app.schemas.common import Page, PageNumber, PageSize
from app.schemas.meetings import MeetingCreate, MeetingDetail, MeetingInputOut, MeetingSummary, MeetingUpdate, TextInputCreate, AttendanceUpdate
from app.services import meetings
from app.services import tasks
from app.schemas.tasks import TaskOut
from app.schemas.jobs import AnalysisAdmin, AnalysisPublic
from app.services.jobs import get_current_analysis, submit_text_input


router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("", response_model=Page[MeetingSummary])
def list_meetings(db: Database, actor: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20,
                  q: Annotated[str | None, Query(max_length=200)] = None):
    return meetings.list_meetings(db, actor, page, page_size, q)


@router.post("", response_model=MeetingDetail, status_code=201)
def create_meeting(payload: MeetingCreate, db: Database, actor: CurrentUser):
    return meetings.create_meeting(db, actor, payload)


@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: int, db: Database, actor: CurrentUser):
    return meetings.meeting_detail(db, get_meeting_or_404(db, actor, meeting_id), actor)


@router.patch("/{meeting_id}", response_model=MeetingDetail)
def update_meeting(meeting_id: int, payload: MeetingUpdate, db: Database, actor: CurrentUser):
    return meetings.update_meeting(db, actor, meeting_id, payload)


@router.post("/{meeting_id}/inputs", response_model=MeetingInputOut, status_code=202,
             description="原文与后台作业同时保存，自动分析并发布有效任务；重复提交复用已有版本和作业。")
def submit_text(meeting_id: int, payload: TextInputCreate, db: Database, actor: CurrentUser):
    return submit_text_input(db, actor, meeting_id, payload)


@router.get("/{meeting_id}/inputs/{input_id}", response_model=MeetingInputOut)
def get_input(meeting_id: int, input_id: int, db: Database, actor: CurrentUser):
    return meetings.input_output(db, meetings.get_input(db, actor, meeting_id, input_id))


@router.get("/{meeting_id}/tasks", response_model=Page[TaskOut])
def list_meeting_tasks(meeting_id: int, db: Database, actor: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    get_meeting_or_404(db, actor, meeting_id)
    return tasks.list_tasks(db, actor, page, page_size, meeting_id=meeting_id)


@router.get("/{meeting_id}/inputs/{input_id}/chunks/{chunk_id}", response_model=Source)
def get_source_chunk(meeting_id: int, input_id: int, chunk_id: int, db: Database, actor: CurrentUser):
    record = meetings.get_input(db, actor, meeting_id, input_id)
    chunk = db.scalar(select(MeetingChunk).where(MeetingChunk.id == chunk_id, MeetingChunk.input_id == record.id))
    if chunk is None:
        raise HTTPException(404, "来源片段不存在")
    meeting = get_meeting_or_404(db, actor, meeting_id)
    return Source(kind="meeting", id=meeting_id, title=meeting.title, input_id=record.id,
                  input_version=record.version, chunk_id=chunk.id, excerpt=chunk.text,
                  start_offset=chunk.start_offset, end_offset=chunk.end_offset)


@router.patch("/{meeting_id}/departments/{department_id}/participants", response_model=MeetingDetail)
def arrange_participants(meeting_id: int, department_id: int, payload: AttendanceUpdate, db: Database, actor: CurrentUser):
    from app.services.meeting_attendance import arrange_attendance
    arrange_attendance(db, actor, meeting_id, department_id, payload.participant_ids)
    return meetings.meeting_detail(db, get_meeting_or_404(db, actor, meeting_id), actor)


@router.get("/{meeting_id}/analysis", response_model=AnalysisAdmin | AnalysisPublic)
def get_analysis(meeting_id: int, db: Database, actor: CurrentUser):
    record = get_current_analysis(db, actor, meeting_id)
    schema = AnalysisAdmin if actor.role == "BOSS" else AnalysisPublic
    return schema.model_validate(record)
