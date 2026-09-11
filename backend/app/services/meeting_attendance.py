"""Department invitations are separate from the organizer's direct invitations."""
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Department, Meeting, MeetingDepartment, MeetingDepartmentParticipant, User
from app.permissions import get_meeting_or_404, is_manager, require_leader
from app.schemas.meetings import DepartmentAttendance


def set_departments(db: Session, actor: User, meeting_id: int, ids: list[int]):
    ids = set(ids)
    if is_manager(actor) and ids - {actor.department_id}:
        raise HTTPException(403, "部门负责人只能按部门邀请本部门，跨部门邀请请由 Boss 安排")
    found = set(db.scalars(select(Department.id).where(Department.id.in_(ids))))
    if found != ids:
        raise HTTPException(422, "所选部门不存在")
    existing = set(db.scalars(select(MeetingDepartment.department_id).where(MeetingDepartment.meeting_id == meeting_id)))
    removed = existing - ids
    db.execute(delete(MeetingDepartmentParticipant).where(MeetingDepartmentParticipant.meeting_id == meeting_id, MeetingDepartmentParticipant.department_id.in_(removed)))
    db.execute(delete(MeetingDepartment).where(MeetingDepartment.meeting_id == meeting_id, MeetingDepartment.department_id.in_(removed)))
    db.add_all([MeetingDepartment(meeting_id=meeting_id, department_id=id_) for id_ in sorted(ids - existing)])
    db.flush()


def attendance_output(db: Session, actor: User, meeting_id: int) -> list[DepartmentAttendance]:
    departments = db.scalars(select(MeetingDepartment.department_id).where(MeetingDepartment.meeting_id == meeting_id).order_by(MeetingDepartment.department_id))
    rows = []
    for department_id in departments:
        participants = list(db.scalars(select(MeetingDepartmentParticipant.user_id).join(User, User.id == MeetingDepartmentParticipant.user_id).where(
            MeetingDepartmentParticipant.meeting_id == meeting_id, MeetingDepartmentParticipant.department_id == department_id,
            User.department_id == department_id).order_by(MeetingDepartmentParticipant.user_id)))
        rows.append(DepartmentAttendance(department_id=department_id, participant_ids=participants,
            can_arrange=actor.role == "BOSS" or (is_manager(actor) and actor.department_id == department_id)))
    return rows


def arrange_attendance(db: Session, actor: User, meeting_id: int, department_id: int, ids: list[int]):
    require_leader(actor)
    get_meeting_or_404(db, actor, meeting_id)
    if actor.role != "BOSS" and actor.department_id != department_id:
        raise HTTPException(403, "只能安排自己部门的参会人员")
    db.scalar(select(Meeting).where(Meeting.id == meeting_id).with_for_update())
    invited = db.get(MeetingDepartment, (meeting_id, department_id))
    if invited is None:
        raise HTTPException(404, "该部门未受邀或邀请已撤回")
    people = list(db.scalars(select(User).where(User.id.in_(set(ids))).with_for_update().execution_options(populate_existing=True)))
    if len(people) != len(set(ids)) or any(not p.is_active or p.department_id != department_id or p.role == "BOSS" for p in people):
        raise HTTPException(422, "只能选择本部门启用的员工或部门负责人")
    db.execute(delete(MeetingDepartmentParticipant).where(MeetingDepartmentParticipant.meeting_id == meeting_id, MeetingDepartmentParticipant.department_id == department_id))
    db.add_all([MeetingDepartmentParticipant(meeting_id=meeting_id, department_id=department_id, user_id=id_) for id_ in sorted(set(ids))])
    db.commit()
