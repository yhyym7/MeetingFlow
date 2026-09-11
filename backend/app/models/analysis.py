from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utc_now


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')", name="status"),
        CheckConstraint("scope IN ('ANALYSIS_ONLY', 'FULL_PIPELINE')", name="scope"),
        Index("ix_processing_jobs_status_id", "status", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    input_id: Mapped[int] = mapped_column(ForeignKey("meeting_inputs.id"), unique=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    stage: Mapped[str] = mapped_column(String(30), default="ANALYZE")
    scope: Mapped[str] = mapped_column(String(30), default="ANALYSIS_ONLY", server_default="ANALYSIS_ONLY")
    attempts: Mapped[int] = mapped_column(default=0)
    analysis_attempts: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    node_trace: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    input_id: Mapped[int] = mapped_column(ForeignKey("meeting_inputs.id"), unique=True)
    mode: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text)
    decisions: Mapped[list] = mapped_column(JSON)
    risks: Mapped[list] = mapped_column(JSON)
    raw_output: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    resolved_candidates: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
