from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Meeting, Task, User
from app.models.base import utc_now
from app.permissions import meeting_scope, require_known_user, task_scope
from app.schemas.dashboard import DashboardOut, TaskStatistics
from app.schemas.meetings import MeetingSummary
from app.services.tasks import overdue_condition, task_outputs
from app.services.candidates import pending_count


def get_dashboard(db: Session, actor: User, now: datetime | None = None) -> DashboardOut:
    require_known_user(actor)
    now = now or utc_now()
    local_day = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    start = datetime.combine(local_day, time.min, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(UTC)
    end = start + timedelta(days=1)
    due_today = (Task.due_at >= start) & (Task.due_at < end) & (Task.status != "DONE")
    overdue = overdue_condition(now)
    values = db.execute(select(
        func.count(Task.id),
        func.coalesce(func.sum(case((Task.status == "TODO", 1), else_=0)), 0),
        func.coalesce(func.sum(case((Task.status == "IN_PROGRESS", 1), else_=0)), 0),
        func.coalesce(func.sum(case((Task.status == "DONE", 1), else_=0)), 0),
        func.coalesce(func.sum(case((overdue, 1), else_=0)), 0),
        func.coalesce(func.sum(case((due_today, 1), else_=0)), 0),
    ).where(task_scope(actor))).one()
    statistics = TaskStatistics(**dict(zip(("total", "todo", "in_progress", "done", "overdue", "due_today"), map(int, values))))
    meetings = list(db.scalars(select(Meeting).where(meeting_scope(actor), Meeting.starts_at >= now)
                               .order_by(Meeting.starts_at, Meeting.id).limit(5)))

    def task_cards(condition):
        rows = list(db.scalars(select(Task).where(task_scope(actor), condition)
                              .order_by(Task.due_at.is_(None), Task.due_at, Task.id).limit(5)))
        return task_outputs(db, actor, rows, now)

    return DashboardOut(
        role=actor.role, as_of=now, timezone="Asia/Shanghai", statistics=statistics,
        upcoming_meetings=[MeetingSummary.model_validate(meeting) for meeting in meetings],
        due_today_tasks=task_cards(due_today), overdue_tasks=task_cards(overdue),
        in_progress_tasks=task_cards(Task.status == "IN_PROGRESS"),
        pending_supplement_count=pending_count(db, actor) if actor.role in {"BOSS", "MANAGER"} else None,
    )
