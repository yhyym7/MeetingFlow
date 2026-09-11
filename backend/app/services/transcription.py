from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.models import MeetingAudio, MeetingInput, User
from app.permissions import get_managed_meeting
from app.services.audio import audio_path
from app.services.meetings import save_text_input
from app.services.jobs import create_analysis_job
from app.schemas.meetings import TextInputCreate


def latest_input(db, meeting_id):
    return db.scalar(select(MeetingInput.id).where(MeetingInput.meeting_id == meeting_id)
                     .order_by(MeetingInput.version.desc()).limit(1))


def queue_audio(db, actor, record, *, commit=True):
    get_managed_meeting(db, actor, record.meeting_id, for_update=True)
    if get_settings().asr_mode != 'local':
        raise HTTPException(503, '尚未接入录音转写服务，录音已保留。')
    if record.status in ('QUEUED', 'RUNNING', 'SUCCEEDED'):
        return record
    audio_path(record)
    record.base_input_id = latest_input(db, record.meeting_id)
    record.processing_user_id = actor.id
    record.status, record.error_code = 'QUEUED', None
    if commit:
        db.commit()
    return record


def finish_transcription(db, record):
    actor = db.get(User, record.processing_user_id)
    if actor is None:
        raise HTTPException(403, '提交人已不存在')
    db.refresh(actor, with_for_update=True)
    get_managed_meeting(db, actor, record.meeting_id, for_update=True)
    newest_audio = db.scalar(select(MeetingAudio.id).where(MeetingAudio.meeting_id == record.meeting_id)
                            .order_by(MeetingAudio.id.desc()).limit(1))
    if newest_audio != record.id or latest_input(db, record.meeting_id) != record.base_input_id:
        raise RuntimeError('ASR_INPUT_CHANGED')
    payload = TextInputCreate(request_id=uuid5(NAMESPACE_URL, f'meetingflow:audio:{record.id}'), text=record.transcript)
    entry, _ = save_text_input(db, actor, record.meeting_id, payload, commit=False)
    create_analysis_job(db, actor, entry.id, scope='FULL_PIPELINE', commit=False)
    record.input_id, record.status, record.error_code = entry.id, 'SUCCEEDED', None
    db.commit()
