"""Private audio storage metadata; transcription awaits a real provider."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("meeting_audio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("original_name", sa.String(200), nullable=False),
        sa.Column("storage_name", sa.String(40), nullable=False, unique=True),
        sa.Column("media_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("meeting_id", "request_id", name="uq_meeting_audio_request"),
        sa.CheckConstraint("size_bytes > 0", name="size_positive"))
    op.create_index("ix_meeting_audio_meeting_id", "meeting_audio", ["meeting_id"])


def downgrade():
    op.drop_table("meeting_audio")
