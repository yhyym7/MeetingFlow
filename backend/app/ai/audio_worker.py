import asyncio
import logging

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.ai.local_models import transcribe
from app.database import get_engine
from app.models import MeetingAudio
from app.services.audio import audio_path
from app.services.transcription import finish_transcription


class AudioWorker:
    def __init__(self, session_factory=None, transcriber=None):
        self.sessions = session_factory or (lambda: Session(get_engine(), expire_on_commit=False))
        self.transcriber = transcriber or transcribe
        self.stop = asyncio.Event()

    def recover(self):
        with self.sessions() as db:
            db.execute(update(MeetingAudio).where(MeetingAudio.status == 'RUNNING').values(status='QUEUED'))
            db.commit()

    async def run_next(self):
        with self.sessions() as db:
            record = db.scalar(select(MeetingAudio).where(MeetingAudio.status == 'QUEUED')
                               .order_by(MeetingAudio.id).limit(1).with_for_update(skip_locked=True))
            if record is None:
                return False
            record.status = 'RUNNING'
            record_id, transcript = record.id, record.transcript
            db.commit()
        try:
            if not transcript:
                with self.sessions() as db:
                    path = audio_path(db.get(MeetingAudio, record_id))
                transcript = await asyncio.to_thread(self.transcriber, path)
                with self.sessions() as db:
                    db.get(MeetingAudio, record_id).transcript = transcript
                    db.commit()
            with self.sessions() as db:
                finish_transcription(db, db.get(MeetingAudio, record_id))
        except SQLAlchemyError:
            raise
        except Exception as exc:
            code = str(exc) if isinstance(exc, RuntimeError) else 'ASR_PERMISSION_CHANGED' if isinstance(exc, HTTPException) and exc.status_code in (403,404) else 'ASR_FAILED'
            allowed = {'ASR_MODEL_MISSING', 'ASR_TOO_LONG', 'ASR_NO_SPEECH', 'ASR_INPUT_CHANGED', 'ASR_PERMISSION_CHANGED'}
            with self.sessions() as db:
                record = db.get(MeetingAudio, record_id)
                record.status, record.error_code = 'FAILED', code if code in allowed else 'ASR_FAILED'
                db.commit()
        return True

    async def run_forever(self):
        recovery = True
        while not self.stop.is_set():
            try:
                if recovery:
                    self.recover(); recovery = False
                worked = await self.run_next()
                if worked:
                    continue
            except SQLAlchemyError:
                logging.getLogger(__name__).warning('Audio database unavailable')
                recovery = True
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=2)
            except TimeoutError:
                pass
