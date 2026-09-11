"""Shared role/action checks and SQL scopes. Unknown roles are denied."""

from fastapi import HTTPException
from sqlalchemy import and_, exists, false, or_, select, true
from sqlalchemy.orm import Session

from app.models import Meeting, MeetingParticipant, MeetingDepartment, MeetingDepartmentParticipant, Task, TaskCollaborator, User


def require_known_user(user: User) -> None:
    if not user.is_active or user.role not in {"BOSS", "EMPLOYEE", "MANAGER"} or (user.role == "MANAGER" and user.department_id is None):
        raise HTTPException(403, "当前账号无操作权限")


def require_boss(user: User) -> None:
    require_known_user(user)
    if user.role != "BOSS":
        raise HTTPException(403, "只有管理者可以执行此操作")


def can_manage_meeting(user: User, meeting: Meeting) -> bool:
    return user.is_active and (user.role == "BOSS" or (is_manager(user) and meeting.created_by_id == user.id))


def is_manager(user: User) -> bool:
    return user.is_active and user.role == "MANAGER" and user.department_id is not None


def require_leader(user: User) -> None:
    require_known_user(user)
    if user.role not in {"BOSS", "MANAGER"}:
        raise HTTPException(403, "只有 Boss 或部门负责人可以执行此操作")


def meeting_management_scope(user: User):
    if not user.is_active:
        return false()
    return true() if user.role == "BOSS" else Meeting.created_by_id == user.id if is_manager(user) else false()


def task_management_scope(user: User):
    if not user.is_active:
        return false()
    if user.role == "BOSS":
        return Task.deleted_at.is_(None)
    if is_manager(user):
        return and_(Task.deleted_at.is_(None), exists(select(User.id).where(
            User.id == Task.owner_id, User.department_id == user.department_id, User.role != "BOSS",
        )))
    return false()


def can_manage_task(db: Session, user: User, task: Task) -> bool:
    if user.role == "BOSS":
        return user.is_active and task.deleted_at is None
    return db.scalar(select(Task.id).where(Task.id == task.id, task_management_scope(user))) is not None


def require_manage_task(db: Session, user: User, task: Task) -> None:
    if not can_manage_task(db, user, task):
        raise HTTPException(403, "只能管理本部门人员负责的任务")


def require_assign_owner(db: Session, user: User, owner_id: int) -> None:
    require_leader(user)
    if user.role == "BOSS":
        return
    owner = db.scalar(select(User).where(User.id == owner_id).with_for_update().execution_options(populate_existing=True))
    if owner is None or owner.department_id != user.department_id or owner.role == "BOSS":
        raise HTTPException(403, "部门负责人只能向本部门人员派发任务，跨部门负责人请由 Boss 指派")


def get_managed_meeting(db: Session, user: User, meeting_id: int, *, for_update: bool = False) -> Meeting:
    require_leader(user)
    query = select(Meeting).where(Meeting.id == meeting_id, meeting_scope(user))
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    meeting = db.scalar(query)
    if meeting is None:
        raise HTTPException(404, "会议不存在或无权访问")
    if not can_manage_meeting(user, meeting):
        raise HTTPException(403, "只能管理自己创建的会议；参加 Boss 的会议不授予管理权限")
    return meeting


def meeting_scope(user: User):
    if not user.is_active:
        return false()
    if user.role == "BOSS":
        return true()
    if user.role == "EMPLOYEE" or is_manager(user):
        participation = exists(select(MeetingParticipant.meeting_id).where(
            MeetingParticipant.meeting_id == Meeting.id, MeetingParticipant.user_id == user.id,
        ))
        department_participation = exists(select(MeetingDepartmentParticipant.meeting_id).where(
            MeetingDepartmentParticipant.meeting_id == Meeting.id,
            MeetingDepartmentParticipant.user_id == user.id,
            MeetingDepartmentParticipant.department_id == user.department_id,
        ))
        invited_department = exists(select(MeetingDepartment.meeting_id).where(
            MeetingDepartment.meeting_id == Meeting.id, MeetingDepartment.department_id == user.department_id,
        ))
        return or_(participation, department_participation, invited_department, Meeting.created_by_id == user.id) if is_manager(user) else or_(participation, department_participation)
    return false()


def task_scope(user: User):
    if not user.is_active or (user.role not in {"BOSS", "EMPLOYEE"} and not is_manager(user)):
        return false()
    visible = true() if user.role == "BOSS" else or_(
        task_management_scope(user),
        Task.owner_id == user.id,
        exists(select(TaskCollaborator.task_id).where(
            TaskCollaborator.task_id == Task.id, TaskCollaborator.user_id == user.id,
        )),
    )
    return and_(Task.deleted_at.is_(None), visible)


def can_update_task_status(user: User, task: Task, db: Session | None = None) -> bool:
    return (
        user.is_active and task.deleted_at is None
        and (user.role == "BOSS" or ((user.role == "EMPLOYEE" or is_manager(user)) and task.owner_id == user.id)
             or (db is not None and is_manager(user) and can_manage_task(db, user, task)))
    )


def get_meeting_or_404(db: Session, user: User, meeting_id: int) -> Meeting:
    meeting = db.scalar(select(Meeting).where(Meeting.id == meeting_id, meeting_scope(user)))
    if meeting is None:
        raise HTTPException(404, "会议不存在或无权访问")
    return meeting


def get_task_or_404(db: Session, user: User, task_id: int, *, for_update: bool = False) -> Task:
    query = select(Task).where(Task.id == task_id, task_scope(user))
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    task = db.scalar(query)
    if task is None:
        raise HTTPException(404, "任务不存在或无权访问")
    return task


def can_add_task_progress(db: Session, user: User, task: Task) -> bool:
    return db.scalar(select(Task.id).where(Task.id == task.id, task_scope(user))) is not None


def effective_participant_ids(db: Session, meeting_id: int) -> list[int]:
    direct = select(MeetingParticipant.user_id).where(MeetingParticipant.meeting_id == meeting_id)
    delegated = select(MeetingDepartmentParticipant.user_id).join(User, User.id == MeetingDepartmentParticipant.user_id).where(
        MeetingDepartmentParticipant.meeting_id == meeting_id, User.department_id == MeetingDepartmentParticipant.department_id)
    managers = select(User.id).join(MeetingDepartment, MeetingDepartment.department_id == User.department_id).where(
        MeetingDepartment.meeting_id == meeting_id, User.role == "MANAGER", User.is_active.is_(True))
    return sorted(set(db.scalars(direct)) | set(db.scalars(delegated)) | set(db.scalars(managers)))
