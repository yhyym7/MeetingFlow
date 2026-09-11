import hashlib
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, get_settings
from app.models import MeetingAudio, User
from app.permissions import get_managed_meeting, get_meeting_or_404


MEDIA_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}


def storage_directory() -> Path:
    path = get_settings().audio_storage_dir
    return (path if path.is_absolute() else BACKEND_DIR / path).resolve()


def validate_name(name: str) -> str:
    if not name or len(name) > 200 or any(c in name for c in '/\\:') or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "录音文件名无效，请使用不含路径的文件名")
    suffix = Path(name).suffix.lower()
    if suffix not in MEDIA_TYPES:
        raise HTTPException(422, "仅支持 mp3、wav、m4a 录音")
    return suffix


def validate_header(header: bytes, suffix: str):
    # Basic signature validation, not a decoder or an ASR quality check.
    valid = False
    if suffix == ".wav":
        valid = len(header) >= 44 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    elif suffix == ".mp3":
        valid = len(header) >= 10 and (header[:3] == b"ID3" or
                (header[0] == 0xff and header[1] & 0xe0 == 0xe0))
    elif suffix == ".m4a":
        valid = len(header) >= 16 and header[4:8] == b"ftyp" and header[8:12] in (
            b"M4A ", b"M4B ", b"isom", b"iso2", b"mp41", b"mp42")
    if not valid:
        raise HTTPException(422, "文件内容与录音格式不符，或文件已损坏")


def get_audio(db: Session, actor: User, meeting_id: int, audio_id: int) -> MeetingAudio:
    get_meeting_or_404(db, actor, meeting_id)
    record = db.scalar(select(MeetingAudio).where(MeetingAudio.id == audio_id, MeetingAudio.meeting_id == meeting_id))
    if record is None:
        raise HTTPException(404, "录音不存在或无权访问")
    return record


def audio_path(record: MeetingAudio) -> Path:
    root = storage_directory()
    path = (root / record.storage_name).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(404, "录音文件不存在，请联系会议创建人重新上传")
    return path


async def save_audio(db: Session, actor: User, meeting_id: int, request: Request,
                     filename: str, request_id: UUID) -> MeetingAudio:
    get_managed_meeting(db, actor, meeting_id)
    suffix = validate_name(filename)
    limit = get_settings().audio_max_mb * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > limit:
        raise HTTPException(413, f"录音不能超过 {get_settings().audio_max_mb} MB")
    root = storage_directory()
    storage_name = uuid4().hex + suffix
    path, temporary = root / storage_name, root / (storage_name + ".part")
    size, digest, header = 0, hashlib.sha256(), b""
    keep_file = False
    try:
        root.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as stream:
            async for data in request.stream():
                size += len(data)
                if size > limit:
                    raise HTTPException(413, f"录音不能超过 {get_settings().audio_max_mb} MB")
                header = (header + data[:64])[:64] if len(header) < 64 else header
                digest.update(data)
                stream.write(data)
        if not size:
            raise HTTPException(422, "不能上传空录音")
        validate_header(header, suffix)
        # Refresh current role after transfer, then serialize per-meeting saves.
        db.refresh(actor, with_for_update=True)
        get_managed_meeting(db, actor, meeting_id, for_update=True)
        existing = db.scalar(select(MeetingAudio).where(MeetingAudio.meeting_id == meeting_id,
                             MeetingAudio.request_id == str(request_id)).with_for_update())
        if existing:
            if existing.content_hash != digest.hexdigest() or existing.original_name != filename:
                raise HTTPException(409, "同一次上传标识不能对应不同录音，请重新选择文件")
            db.commit()
            return existing
        record = MeetingAudio(meeting_id=meeting_id, request_id=str(request_id), original_name=filename,
                              storage_name=storage_name, media_type=MEDIA_TYPES[suffix], size_bytes=size,
                              content_hash=digest.hexdigest(), created_by_id=actor.id)
        db.add(record)
        db.flush()
        temporary.replace(path)
        if get_settings().asr_mode == 'local':
            from app.services.transcription import queue_audio
            queue_audio(db, actor, record, commit=False)
        db.commit()
        keep_file = True
        return record
    except OSError:
        db.rollback()
        raise HTTPException(503, "录音保存失败，请检查本机存储空间后重试") from None
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
            if not keep_file:
                path.unlink(missing_ok=True)
