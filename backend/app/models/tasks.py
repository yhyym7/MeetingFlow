from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime, utc_now


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('TODO', 'IN_PROGRESS', 'DONE')", name="status"),
        CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH')", name="priority"),
        CheckConstraint(
            "(status = 'DONE' AND completed_at IS NOT NULL) OR "
            "(status <> 'DONE' AND completed_at IS NULL)", name="completion",
        ),
        Index("ix_tasks_owner_id_status", "owner_id", "status"),
        Index("ix_tasks_deleted_at_due_at", "deleted_at", "due_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id"), index=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("action_candidates.id"), unique=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL")
    status: Mapped[str] = mapped_column(String(20), default="TODO")
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class TaskCollaborator(Base):
    __tablename__ = "task_collaborators"

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_id_created_at", "task_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    body: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
