from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError

from app.models import Department, Meeting, MeetingParticipant, Task, TaskCollaborator, TaskEvent, User
from app.security import verify_password
from scripts.seed_demo import seed_demo


def counts(db):
    return {model.__tablename__: db.scalar(select(func.count()).select_from(model)) for model in (
        Department, User, Meeting, MeetingParticipant, Task, TaskCollaborator, TaskEvent,
    )}


def demo_people(db):
    seed_demo(db, "T02-test-password")
    return {u.username: u for u in db.scalars(select(User))}


def test_seed_is_repeatable_and_preserves_edits(db):
    people = demo_people(db)
    before = counts(db)
    old_hash = people["zhangsan"].password_hash
    people["zhangsan"].name = "手工修改姓名"
    event = db.scalar(select(TaskEvent).where(TaskEvent.changes["seed_key"].as_string() == "core-demo-v1"))
    task = db.get(Task, event.task_id)
    meeting = db.get(Meeting, task.meeting_id)
    task.title = "手工修改任务标题"
    meeting.title = "手工修改会议标题"
    db.flush()
    result = seed_demo(db, "different-test-password")
    assert result == {"departments": 0, "users": 0, "meetings": 0, "tasks": 0}
    assert counts(db) == before
    db.refresh(people["zhangsan"])
    assert people["zhangsan"].password_hash == old_hash
    assert people["zhangsan"].name == "手工修改姓名"
    assert task.title == "手工修改任务标题"


def test_demo_covers_permission_relationships(db):
    people = demo_people(db)
    event = db.scalar(select(TaskEvent).where(TaskEvent.changes["seed_key"].as_string() == "core-demo-v1"))
    task = db.get(Task, event.task_id)
    participants = set(db.scalars(select(MeetingParticipant.user_id).where(MeetingParticipant.meeting_id == task.meeting_id)))
    collaborators = set(db.scalars(select(TaskCollaborator.user_id).where(TaskCollaborator.task_id == task.id)))
    assert task.owner_id == people["zhangsan"].id
    assert people["lisi"].id in participants
    assert people["lisi"].id not in collaborators
    assert people["wangwu"].id in collaborators
    assert people["wangwu"].id not in participants
    assert people["zhaoliu"].id not in participants | collaborators | {task.owner_id}
    assert people["boss"].role == "BOSS"


def test_new_password_is_hash_only(db):
    user = User(username=f"test_{uuid4().hex[:12]}", name="测试", password_hash="temporary")
    from app.security import hash_password
    password = "test-password-OnlyForT02"
    user.password_hash = hash_password(password)
    db.add(user)
    db.flush()
    db.expire(user)
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)


def test_unique_username_is_enforced_case_insensitively(db):
    people = demo_people(db)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(User(username="BOSS", name="重复", role="EMPLOYEE", password_hash=people["boss"].password_hash))
            db.flush()


def test_foreign_keys_and_membership_uniqueness(db):
    people = demo_people(db)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(MeetingParticipant(meeting_id=2147483647, user_id=people["boss"].id))
            db.flush()
    participant = db.scalar(select(MeetingParticipant).where(MeetingParticipant.user_id == people["boss"].id))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("INSERT INTO meeting_participants (meeting_id,user_id) VALUES (:m,:u)"),
                       {"m": participant.meeting_id, "u": participant.user_id})


def test_aware_time_roundtrip_and_naive_time_rejection(db):
    people = demo_people(db)
    starts = datetime(2026, 9, 7, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    meeting = Meeting(title="时区测试", starts_at=starts, created_by_id=people["boss"].id)
    db.add(meeting)
    db.flush()
    raw = db.execute(text("SELECT starts_at FROM meetings WHERE id=:id"), {"id": meeting.id}).scalar_one()
    assert raw == datetime(2026, 9, 7, 2, 30)
    db.refresh(meeting)
    assert meeting.starts_at == starts.astimezone(UTC)
    assert meeting.starts_at.tzinfo == UTC
    with pytest.raises(StatementError):
        with db.begin_nested():
            db.add(Meeting(title="缺失时区", starts_at=datetime(2026, 9, 7), created_by_id=people["boss"].id))
            db.flush()


def test_invalid_role_and_completion_are_rejected(db):
    people = demo_people(db)
    with pytest.raises(DBAPIError) as invalid_role:
        with db.begin_nested():
            db.add(User(username="invalid_role", name="测试", role="MANAGER", password_hash="not-used"))
            db.flush()
    assert invalid_role.value.orig.args[0] == 3819  # MySQL CHECK constraint violation
    with pytest.raises(DBAPIError) as invalid_completion:
        with db.begin_nested():
            db.add(Task(title="缺少完成时间", description="测试", owner_id=people["zhangsan"].id,
                        created_by_id=people["boss"].id, status="DONE"))
            db.flush()
    assert invalid_completion.value.orig.args[0] == 3819


def test_transaction_rollback_removes_partial_business_write(db):
    people = demo_people(db)
    before = counts(db)
    with pytest.raises(RuntimeError, match="simulated failure"):
        with db.begin_nested():
            task = Task(title="回滚验证", description="测试", owner_id=people["zhangsan"].id,
                        created_by_id=people["boss"].id)
            db.add(task)
            db.flush()
            db.add(TaskEvent(task_id=task.id, actor_id=people["boss"].id, event_type="CREATED"))
            db.flush()
            raise RuntimeError("simulated failure")
    assert counts(db) == before
