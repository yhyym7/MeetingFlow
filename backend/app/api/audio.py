from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.api.dependencies import CurrentUser, Database
from app.permissions import get_managed_meeting
from app.schemas.audio import AudioOut
from app.services.audio import audio_path, get_audio, save_audio


router = APIRouter(prefix="/meetings", tags=["audio"])


@router.post("/{meeting_id}/audio", response_model=AudioOut, status_code=201,
             description="上传原始音频字节；文件名及 UUID 提交标识放在查询参数。尚未接入转写服务。",
             openapi_extra={"requestBody": {"required": True, "content": {
                 "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def upload_audio(meeting_id: int, request: Request, db: Database, actor: CurrentUser,
                       filename: Annotated[str, Query(min_length=1, max_length=200)], request_id: UUID):
    return await save_audio(db, actor, meeting_id, request, filename, request_id)


@router.get("/{meeting_id}/audio/{audio_id}/download")
def download_audio(meeting_id: int, audio_id: int, db: Database, actor: CurrentUser):
    record = get_audio(db, actor, meeting_id, audio_id)
    return FileResponse(audio_path(record), media_type=record.media_type, filename=record.original_name,
                        headers={"X-Content-Type-Options": "nosniff"})


@router.post("/{meeting_id}/audio/{audio_id}/transcribe", response_model=AudioOut)
def transcribe_audio(meeting_id: int, audio_id: int, db: Database, actor: CurrentUser):
    get_managed_meeting(db, actor, meeting_id)
    from app.services.transcription import queue_audio
    return queue_audio(db, actor, get_audio(db, actor, meeting_id, audio_id))
