from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisRecord, Meeting, MeetingInput, ProcessingJob, User
from app.permissions import get_meeting_or_404, meeting_scope, require_leader, get_managed_meeting


def get_job(db: Session, actor: User, job_id: int) -> ProcessingJob:
    job = db.scalar(select(ProcessingJob).join(Meeting, ProcessingJob.meeting_id == Meeting.id)
                    .where(ProcessingJob.id == job_id, meeting_scope(actor)))
    if job is None:
        raise HTTPException(404, "作业不存在或无权访问")
    return job


def create_analysis_job(db: Session, actor: User, input_id: int, *, scope: str = "ANALYSIS_ONLY",
                         commit: bool = True) -> ProcessingJob:
    require_leader(actor)
    record = db.get(MeetingInput, input_id)
    if record is None:
        raise HTTPException(404, "会议输入不存在")
    get_managed_meeting(db, actor, record.meeting_id, for_update=True)
    existing = db.scalar(select(ProcessingJob).where(ProcessingJob.input_id == input_id).with_for_update())
    if existing:
        return existing
    active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.meeting_id == record.meeting_id,
                       ProcessingJob.status.in_(["QUEUED", "RUNNING"])).with_for_update().limit(1))
    if active:
        raise HTTPException(409, "该会议已有正在处理的作业")
    job = ProcessingJob(input_id=input_id, meeting_id=record.meeting_id, scope=scope)
    db.add(job)
    db.flush()
    if commit:
        db.commit()
    return job


def submit_text_input(db: Session, actor: User, meeting_id: int, payload):
    from app.services.meetings import input_output, save_text_input
    record, _ = save_text_input(db, actor, meeting_id, payload, commit=False)
    create_analysis_job(db, actor, record.id, scope="FULL_PIPELINE", commit=False)
    # Input version and durable queue entry either both commit or both roll back.
    db.commit()
    return input_output(db, record)


def retry_job(db: Session, actor: User, job_id: int) -> ProcessingJob:
    require_leader(actor)
    job = get_job(db, actor, job_id)
    get_managed_meeting(db, actor, job.meeting_id, for_update=True)
    db.refresh(job, with_for_update=True)
    if job.status != "FAILED":
        raise HTTPException(409, "只能重试失败的作业")
    other = db.scalar(select(ProcessingJob.id).where(ProcessingJob.meeting_id == job.meeting_id,
                      ProcessingJob.id != job.id, ProcessingJob.status.in_(["QUEUED", "RUNNING"])).with_for_update().limit(1))
    if other:
        raise HTTPException(409, "该会议已有其他作业正在处理")
    job.status, job.error_code, job.finished_at = "QUEUED", None, None
    db.commit()
    return job


def get_current_analysis(db: Session, actor: User, meeting_id: int) -> AnalysisRecord:
    get_meeting_or_404(db, actor, meeting_id)
    latest = db.scalar(select(MeetingInput.id).where(MeetingInput.meeting_id == meeting_id)
                       .order_by(MeetingInput.version.desc()).limit(1))
    analysis = db.scalar(select(AnalysisRecord).where(AnalysisRecord.input_id == latest)) if latest else None
    if analysis is None:
        raise HTTPException(404, "当前输入尚无分析结果")
    return analysis
