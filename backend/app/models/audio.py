from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utc_now


class MeetingAudio(Base):
    __tablename__ = "meeting_audio"
    __table_args__ = (
        UniqueConstraint("meeting_id", "request_id", name="uq_meeting_audio_request"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    original_name: Mapped[str] = mapped_column(String(200))
    storage_name: Mapped[str] = mapped_column(String(40), unique=True)
    media_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    status: Mapped[str] = mapped_column(String(30), default="AWAITING_TRANSCRIPTION", server_default="AWAITING_TRANSCRIPTION")
    transcript: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(80))
    base_input_id: Mapped[int | None] = mapped_column(ForeignKey("meeting_inputs.id"))
    input_id: Mapped[int | None] = mapped_column(ForeignKey("meeting_inputs.id"), unique=True)
    processing_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
