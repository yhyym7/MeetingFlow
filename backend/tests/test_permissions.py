import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models import Meeting, MeetingParticipant, Task, TaskCollaborator, TaskEvent, User
from app.models.base import utc_now
from app.permissions import (
    can_add_task_progress, can_update_task_status, get_meeting_or_404,
    get_task_or_404, meeting_scope, require_boss, task_scope,
)
from scripts.seed_demo import seed_demo


@pytest.mark.parametrize("username,meeting_visible,task_visible,status_allowed,progress_allowed", [
    ("boss", True, True, True, True),
    ("zhangsan", True, True, True, True),
    ("lisi", True, False, False, False),
    ("wangwu", False, True, False, True),
    ("zhaoliu", False, False, False, False),
])
def test_role_relationship_matrix(db, username, meeting_visible, task_visible, status_allowed, progress_allowed):
    seed_demo(db, "test-password-T04")
    user = db.scalar(select(User).where(User.username == username))
    marker = db.scalar(select(TaskEvent).where(TaskEvent.changes["seed_key"].as_string() == "core-demo-v1"))
    task = db.get(Task, marker.task_id)
    assert bool(db.scalar(select(Meeting.id).where(Meeting.id == task.meeting_id, meeting_scope(user)))) == meeting_visible
    assert bool(db.scalar(select(Task.id).where(Task.id == task.id, task_scope(user)))) == task_visible
    if meeting_visible:
        assert get_meeting_or_404(db, user, task.meeting_id).id == task.meeting_id
    else:
        with pytest.raises(HTTPException) as exc:
            get_meeting_or_404(db, user, task.meeting_id)
        assert exc.value.status_code == 404
    if task_visible:
        assert get_task_or_404(db, user, task.id).id == task.id
    else:
        with pytest.raises(HTTPException) as exc:
            get_task_or_404(db, user, task.id)
        assert exc.value.status_code == 404
    assert can_update_task_status(user, task) == status_allowed
    assert can_add_task_progress(db, user, task) == progress_allowed


@pytest.mark.parametrize("role,active", [("MANAGER", True), ("UNKNOWN", True), ("BOSS", False)])
def test_unknown_roles_and_disabled_accounts_default_deny(db, role, active):
    user = User(id=1, name="未授权身份", username="unknown", role=role, is_active=active)
    assert db.scalar(select(Meeting.id).where(meeting_scope(user)).limit(1)) is None
    assert db.scalar(select(Task.id).where(task_scope(user)).limit(1)) is None
    with pytest.raises(HTTPException) as exc:
        require_boss(user)
    assert exc.value.status_code == 403


def test_membership_removal_and_deleted_tasks_take_effect(db):
    seed_demo(db, "test-password-T04")
    users = {user.username: user for user in db.scalars(select(User))}
    marker = db.scalar(select(TaskEvent).where(TaskEvent.changes["seed_key"].as_string() == "core-demo-v1"))
    task = db.get(Task, marker.task_id)
    db.execute(delete(MeetingParticipant).where(MeetingParticipant.meeting_id == task.meeting_id, MeetingParticipant.user_id == users["zhangsan"].id))
    db.execute(delete(TaskCollaborator).where(TaskCollaborator.task_id == task.id, TaskCollaborator.user_id == users["wangwu"].id))
    with pytest.raises(HTTPException):
        get_meeting_or_404(db, users["zhangsan"], task.meeting_id)
    assert get_task_or_404(db, users["zhangsan"], task.id)
    with pytest.raises(HTTPException):
        get_task_or_404(db, users["wangwu"], task.id)
    task.deleted_at = utc_now()
    db.flush()
    with pytest.raises(HTTPException):
        get_task_or_404(db, users["boss"], task.id)
    assert not can_update_task_status(users["boss"], task)
    assert not can_add_task_progress(db, users["boss"], task)
