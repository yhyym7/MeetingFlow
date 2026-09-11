from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ActionItem(TimestampMixin, Base):
    __tablename__ = "action_candidates"
    __table_args__ = (
        UniqueConstraint("analysis_id", "position"),
        CheckConstraint("status IN ('READY', 'NEEDS_INFO', 'REJECTED', 'DISCUSSION', 'REVIEW', 'PUBLISHED', 'DISMISSED')", name="status"),
        Index("ix_action_candidates_needs_attention", "needs_attention"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    position: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20))
    resolved: Mapped[dict] = mapped_column(JSON)
    needs_attention: Mapped[bool] = mapped_column(default=False)
