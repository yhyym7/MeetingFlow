"""Allow a department manager role without introducing an organization tree."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users DROP CHECK ck_users_role, ADD CONSTRAINT ck_users_role CHECK (role IN ('BOSS', 'EMPLOYEE', 'MANAGER')), ADD CONSTRAINT ck_users_manager_department CHECK (role != 'MANAGER' OR department_id IS NOT NULL)")
    op.create_table("meeting_departments",
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id"), primary_key=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), primary_key=True))
    op.create_table("meeting_department_participants",
        sa.Column("meeting_id", sa.Integer(), primary_key=True),
        sa.Column("department_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.ForeignKeyConstraint(["meeting_id", "department_id"], ["meeting_departments.meeting_id", "meeting_departments.department_id"], name="fk_meeting_department_participants_invitation"))


def downgrade():
    # Refuse downgrade with managers instead of silently demoting user accounts.
    op.execute("ALTER TABLE users DROP CHECK ck_users_role, DROP CHECK ck_users_manager_department, ADD CONSTRAINT ck_users_role CHECK (role IN ('BOSS', 'EMPLOYEE'))")
    op.drop_table("meeting_department_participants")
    op.drop_table("meeting_departments")
