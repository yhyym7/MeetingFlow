import hashlib

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Meeting, MeetingAudio, MeetingInput, MeetingParticipant, ProcessingJob, User
from app.permissions import can_manage_meeting, get_meeting_or_404, meeting_scope, require_leader, get_managed_meeting, effective_participant_ids
from app.schemas.common import Page
from app.services.meeting_attendance import attendance_output, set_departments
from app.schemas.meetings import MeetingCreate, MeetingDetail, MeetingInputOut, MeetingSummary, MeetingUpdate, TextInputCreate


def validate_active_people(db: Session, ids: list[int]) -> list[int]:
    unique_ids = sorted(set(ids))
    found = set(db.scalars(select(User.id).where(User.id.in_(unique_ids), User.is_active.is_(True))))
    if found != set(unique_ids):
        raise HTTPException(422, "所选人员不存在或已停用")
    return unique_ids


def meeting_detail(db: Session, meeting: Meeting, actor: User) -> MeetingDetail:
    participants = list(db.scalars(select(MeetingParticipant.user_id)
                                   .where(MeetingParticipant.meeting_id == meeting.id).order_by(MeetingParticipant.user_id)))
    current = db.scalar(select(MeetingInput).where(MeetingInput.meeting_id == meeting.id)
                        .order_by(MeetingInput.version.desc()).limit(1))
    attendance = attendance_output(db, actor, meeting.id)
    audio = db.scalar(select(MeetingAudio).where(MeetingAudio.meeting_id == meeting.id)
                      .order_by(MeetingAudio.id.desc()).limit(1))
    return MeetingDetail(
        **MeetingSummary.model_validate(meeting).model_dump(), description=meeting.description,
        participant_ids=effective_participant_ids(db, meeting.id), direct_participant_ids=participants,
        department_ids=[row.department_id for row in attendance], department_attendance=attendance, current_input=input_output(db, current) if current else None,
        can_manage=can_manage_meeting(actor, meeting),
        current_audio=audio,
    )


def input_output(db: Session, record: MeetingInput) -> MeetingInputOut:
    result = MeetingInputOut.model_validate(record)
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.input_id == record.id))
    if job:
        result.job_id, result.processing_status = job.id, job.status
    return result


def list_meetings(db: Session, actor: User, page: int, page_size: int, q: str | None = None) -> Page[MeetingSummary]:
    filters = [meeting_scope(actor)]
    if q:
        filters.append(Meeting.title.contains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(Meeting).where(*filters))
    rows = db.scalars(select(Meeting).where(*filters).order_by(Meeting.starts_at.desc(), Meeting.id.desc())
                      .offset((page - 1) * page_size).limit(page_size))
    return Page(items=[MeetingSummary.model_validate(row) for row in rows], total=total, page=page, page_size=page_size)


def create_meeting(db: Session, actor: User, payload: MeetingCreate) -> MeetingDetail:
    require_leader(actor)
    participants = validate_active_people(db, payload.participant_ids)
    meeting = Meeting(**payload.model_dump(exclude={"participant_ids", "department_ids"}), created_by_id=actor.id)
    db.add(meeting)
    db.flush()
    db.add_all([MeetingParticipant(meeting_id=meeting.id, user_id=user_id) for user_id in participants])
    set_departments(db, actor, meeting.id, payload.department_ids)
    db.commit()
    return meeting_detail(db, meeting, actor)


def update_meeting(db: Session, actor: User, meeting_id: int, payload: MeetingUpdate) -> MeetingDetail:
    require_leader(actor)
    meeting = get_managed_meeting(db, actor, meeting_id, for_update=True)
    changes = payload.model_dump(exclude_unset=True)
    if "department_ids" in changes:
        set_departments(db, actor, meeting.id, changes.pop("department_ids"))
    if "participant_ids" in changes:
        participants = validate_active_people(db, changes.pop("participant_ids"))
        db.execute(delete(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting.id))
        db.add_all([MeetingParticipant(meeting_id=meeting.id, user_id=user_id) for user_id in participants])
    for key, value in changes.items():
        setattr(meeting, key, value)
    db.commit()
    return meeting_detail(db, meeting, actor)


def save_text_input(db: Session, actor: User, meeting_id: int, payload: TextInputCreate,
                    *, commit: bool = True) -> tuple[MeetingInput, bool]:
    require_leader(actor)
    # A parent row lock serializes per-meeting version allocation.
    meeting = get_managed_meeting(db, actor, meeting_id, for_update=True)
    request_id = str(payload.request_id)
    digest = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
    existing = db.scalar(select(MeetingInput).where(
        MeetingInput.meeting_id == meeting_id, MeetingInput.request_id == request_id,
    ).with_for_update())
    if existing:
        if existing.content_hash != digest:
            raise HTTPException(409, "同一次提交标识不能对应不同内容，请使用新的提交标识")
        if commit:
            db.commit()
        return existing, False
    active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.meeting_id == meeting_id,
                       ProcessingJob.status.in_(["QUEUED", "RUNNING"])).limit(1).with_for_update())
    if active:
        raise HTTPException(409, "该会议已有正在处理的作业，请等待结束后提交新内容")
    previous_version = db.scalar(select(MeetingInput.version).where(MeetingInput.meeting_id == meeting_id)
                                 .order_by(MeetingInput.version.desc()).limit(1).with_for_update())
    record = MeetingInput(meeting_id=meeting_id, version=(previous_version or 0) + 1,
                          request_id=request_id, text=payload.text, content_hash=digest, created_by_id=actor.id)
    db.add(record)
    db.flush()
    from app.services.knowledge import index_input
    index_input(db, record)
    if commit:
        db.commit()
    return record, True


def get_input(db: Session, actor: User, meeting_id: int, input_id: int) -> MeetingInput:
    get_meeting_or_404(db, actor, meeting_id)
    record = db.scalar(select(MeetingInput).where(MeetingInput.id == input_id, MeetingInput.meeting_id == meeting_id))
    if record is None:
        raise HTTPException(404, "会议输入不存在")
    return record
