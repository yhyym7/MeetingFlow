from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, utc_now


class Meeting(TimestampMixin, Base):
    __tablename__ = "meetings"
    __table_args__ = (Index("ix_meetings_starts_at", "starts_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime())
    location: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"

    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)


class MeetingDepartment(Base):
    __tablename__ = "meeting_departments"
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), primary_key=True)


class MeetingDepartmentParticipant(Base):
    __tablename__ = "meeting_department_participants"
    __table_args__ = (ForeignKeyConstraint(
        ["meeting_id", "department_id"], ["meeting_departments.meeting_id", "meeting_departments.department_id"],
        name="fk_meeting_department_participants_invitation",
    ),)
    meeting_id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class MeetingInput(Base):
    __tablename__ = "meeting_inputs"
    __table_args__ = (
        UniqueConstraint("meeting_id", "version", name="uq_meeting_inputs_version"),
        UniqueConstraint("meeting_id", "request_id", name="uq_meeting_inputs_request"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    version: Mapped[int]
    request_id: Mapped[str] = mapped_column(String(36))
    text: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
