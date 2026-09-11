"""Initialize small, fictional demo data without overwriting existing records."""

import argparse
import getpass
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import set_key
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Department, Meeting, MeetingParticipant, Task, TaskCollaborator, TaskEvent, User
from app.security import hash_password


DEMO_USERS = (
    ("boss", "王总", "BOSS", None),
    ("zhangsan", "张三", "EMPLOYEE", "技术部"),
    ("lisi", "李四", "EMPLOYEE", "技术部"),
    ("wangwu", "王五", "EMPLOYEE", "产品部"),
    ("zhaoliu", "赵六", "EMPLOYEE", "产品部"),
)
DEMO_MEETING_TITLE = "[演示] 产品迭代启动会"
DEMO_TASK_TITLE = "[演示] 整理接口联调清单"


def seed_demo(session: Session, password: str) -> dict[str, int]:
    """Caller owns the transaction; repeated runs preserve human edits/passwords."""
    created = {"departments": 0, "users": 0, "meetings": 0, "tasks": 0}
    departments = {}
    for name in ("技术部", "产品部"):
        department = session.scalar(select(Department).where(Department.name == name))
        if department is None:
            department = Department(name=name)
            session.add(department)
            session.flush()
            created["departments"] += 1
        departments[name] = department

    users = {}
    for username, name, role, department_name in DEMO_USERS:
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username, name=name, role=role,
                department_id=departments[department_name].id if department_name else None,
                password_hash=hash_password(password),
            )
            session.add(user)
            session.flush()
            created["users"] += 1
        users[username] = user

    marker = session.scalar(select(TaskEvent.id).where(
        TaskEvent.changes["seed_key"].as_string() == "core-demo-v1",
    ).limit(1))
    if marker is not None:
        return created

    meeting = session.scalar(select(Meeting).where(Meeting.title == DEMO_MEETING_TITLE))
    if meeting is None:
        starts_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
            hour=10, minute=0, second=0, microsecond=0,
        )
        meeting = Meeting(
            title=DEMO_MEETING_TITLE, starts_at=starts_at, location="会议室 A",
            description="虚构演示数据，非 AI 分析结果。",
            created_by_id=users["boss"].id,
        )
        session.add(meeting)
        session.flush()
        for username in ("boss", "zhangsan", "lisi"):
            session.add(MeetingParticipant(meeting_id=meeting.id, user_id=users[username].id))
        created["meetings"] += 1

    task = session.scalar(select(Task).where(Task.meeting_id == meeting.id, Task.title == DEMO_TASK_TITLE))
    if task is None:
        task = Task(
            title=DEMO_TASK_TITLE, description="整理本轮接口清单，与产品同事核对字段含义。",
            owner_id=users["zhangsan"].id, created_by_id=users["boss"].id,
            meeting_id=meeting.id,
            source_excerpt="张三整理接口联调清单，王五协助核对产品字段。",
            due_at=(meeting.starts_at + timedelta(days=2)).astimezone(ZoneInfo("Asia/Shanghai")).replace(
                hour=23, minute=59, second=0, microsecond=0,
            ),
        )
        session.add(task)
        session.flush()
        session.add(TaskCollaborator(task_id=task.id, user_id=users["wangwu"].id))
        session.add(TaskEvent(
            task_id=task.id, actor_id=users["boss"].id, event_type="CREATED",
            body="初始化脚本创建的演示任务，非 AI 生成。",
            changes={"seed_key": "core-demo-v1"},
        ))
        created["tasks"] += 1
    session.flush()
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--random-password", action="store_true", help="Generate a password and save it in local .env.demo")
    args = parser.parse_args()
    password = secrets.token_urlsafe(12) if args.random_password else getpass.getpass("Demo password (hidden): ")
    if len(password) < 8 or len(password) > 256:
        parser.error("Demo password must contain 8 to 256 characters")
    with Session(get_engine()) as session, session.begin():
        result = seed_demo(session, password)
        if result["users"] and args.random_password:
            set_key(Path(__file__).resolve().parents[1] / ".env.demo", "DEMO_PASSWORD", password)
    print("Created:", result)
    print("Accounts: boss, zhangsan, lisi, wangwu, zhaoliu")
    if result["users"] and args.random_password:
        print("Password for newly created demo accounts saved in backend/.env.demo (hidden).")
    elif not result["users"]:
        print("Existing account passwords were preserved.")


if __name__ == "__main__":
    main()
