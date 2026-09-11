"""Persist versioned meeting source chunks; backfill with scripts.index_meetings."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("meeting_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("input_id", sa.Integer(), sa.ForeignKey("meeting_inputs.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("input_id", "position", name="uq_meeting_chunks_position"),
        sa.CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="offsets"))


def downgrade():
    op.drop_table("meeting_chunks")
