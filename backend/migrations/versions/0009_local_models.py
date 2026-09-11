"""Durable transcription state and local source vectors."""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('meeting_chunks', sa.Column('embedding', sa.JSON(), nullable=True))
    op.add_column('meeting_chunks', sa.Column('embedding_model', sa.String(100), nullable=True))
    op.add_column('meeting_audio', sa.Column('status', sa.String(30), nullable=False, server_default='AWAITING_TRANSCRIPTION'))
    for name, type_ in [('transcript', sa.Text()), ('error_code', sa.String(80)), ('base_input_id', sa.Integer()),
                        ('input_id', sa.Integer()), ('processing_user_id', sa.Integer())]:
        op.add_column('meeting_audio', sa.Column(name, type_, nullable=True))
    for column, table in [('base_input_id', 'meeting_inputs'), ('input_id', 'meeting_inputs'), ('processing_user_id', 'users')]:
        op.create_foreign_key(f'fk_meeting_audio_{column}_{table}', 'meeting_audio', table, [column], ['id'])
    op.create_unique_constraint('uq_meeting_audio_input_id', 'meeting_audio', ['input_id'])


def downgrade():
    op.drop_constraint('uq_meeting_audio_input_id', 'meeting_audio', type_='unique')
    for column, table in [('base_input_id', 'meeting_inputs'), ('input_id', 'meeting_inputs'), ('processing_user_id', 'users')]:
        op.drop_constraint(f'fk_meeting_audio_{column}_{table}', 'meeting_audio', type_='foreignkey')
    for name in ['status', 'transcript', 'error_code', 'base_input_id', 'input_id', 'processing_user_id']:
        op.drop_column('meeting_audio', name)
    op.drop_column('meeting_chunks', 'embedding_model')
    op.drop_column('meeting_chunks', 'embedding')
