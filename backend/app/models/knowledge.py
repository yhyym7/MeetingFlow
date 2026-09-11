from sqlalchemy import JSON, String, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"
    __table_args__ = (
        UniqueConstraint("input_id", "position", name="uq_meeting_chunks_position"),
        CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="offsets"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    input_id: Mapped[int] = mapped_column(ForeignKey("meeting_inputs.id"))
    position: Mapped[int]
    start_offset: Mapped[int]
    end_offset: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
