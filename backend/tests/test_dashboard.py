from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Meeting, MeetingParticipant, Task, TaskCollaborator, User
from app.services.dashboard import get_dashboard
from test_auth_people import login, user_id
from test_meetings import create_meeting
from test_tasks import create_task


@pytest.mark.parametrize("username", ["boss", "zhangsan", "wangwu", "lisi", "zhaoliu"])
def test_dashboard_totals_equal_authorized_task_lists(client, db, existing_pending, username):
    login(client)
    create_task(client, db, due_at="2000-01-01")
    login(client, username)
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    stats = response.json()["statistics"]
    assert stats["total"] == client.get("/api/tasks").json()["total"]
    assert stats["overdue"] == client.get("/api/tasks?overdue=true").json()["total"]
    assert stats["total"] == stats["todo"] + stats["in_progress"] + stats["done"]
    assert response.json()["pending_supplement_count"] == (existing_pending if username == "boss" else None)
    for card in response.json()["overdue_tasks"]:
        assert client.get(f"/api/tasks/{card['id']}").status_code == 200


def test_shanghai_day_boundaries_no_deadline_done_and_deleted(db):
    from scripts.seed_demo import seed_demo
    seed_demo(db, "test-password-T07")
    users = {user.username: user for user in db.scalars(select(User))}
    now = datetime(2026, 9, 7, 16, 30, tzinfo=UTC)  # Shanghai Sep 8 00:30
    owner = users["zhaoliu"]  # no pre-existing tasks in the demo
    cases = [
        (now - timedelta(hours=1), "TODO", None, None),      # previous local day, overdue
        (now - timedelta(minutes=30), "TODO", None, None), # local midnight, today + overdue
        (datetime(2026, 9, 8, 15, 59, tzinfo=UTC), "TODO", None, None),
        (datetime(2026, 9, 8, 16, 0, tzinfo=UTC), "TODO", None, None), # next local day
        (None, "IN_PROGRESS", None, None),
        (now, "DONE", now, None),
        (now, "TODO", None, now),
    ]
    for due, status, completed, deleted in cases:
        db.add(Task(title="日期边界", description="测试", owner_id=owner.id, created_by_id=users["boss"].id,
                    due_at=due, status=status, completed_at=completed, deleted_at=deleted))
    db.flush()
    result = get_dashboard(db, owner, now)
    assert result.statistics.total == 6
    assert result.statistics.due_today == 2
    assert result.statistics.overdue == 2
    assert result.statistics.done == 1
    assert len(result.in_progress_tasks) == 1 and result.in_progress_tasks[0].due_at is None


def test_upcoming_meeting_permissions_and_limit(client, db):
    login(client)
    for i in range(7):
        create_meeting(client, db, title=f"未来会议{i}", starts_at=f"2099-01-{i+1:02d}T10:00:00+08:00")
    login(client, "zhangsan")
    rows = client.get("/api/dashboard").json()["upcoming_meetings"]
    assert len(rows) == 5
    assert rows == sorted(rows, key=lambda row: (row["starts_at"], row["id"]))
    login(client, "wangwu")
    assert client.get("/api/dashboard").json()["upcoming_meetings"] == []


def test_empty_employee_dashboard_and_same_department_isolation(client, db):
    colleague = db.get(User, user_id(db, "lisi"))
    # Demo employees can acquire real tasks. Keep this empty-user case isolated.
    username = "empty_" + uuid4().hex[:16]
    db.add(User(username=username, name="空首页测试人员", department_id=colleague.department_id,
                role="EMPLOYEE", is_active=True, password_hash=colleague.password_hash))
    db.commit()
    login(client, username)
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["statistics"]["total"] == 0
    assert dashboard["overdue_tasks"] == []
    assert dashboard["due_today_tasks"] == []
    assert dashboard["in_progress_tasks"] == []
