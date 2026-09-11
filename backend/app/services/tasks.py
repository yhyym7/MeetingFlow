from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.orm import Session

from app.models import Meeting, Task, TaskCollaborator, TaskEvent, User
from app.models.base import utc_now
from app.permissions import can_manage_task, can_update_task_status, get_meeting_or_404, get_task_or_404, meeting_scope, require_leader, require_manage_task, require_assign_owner, get_managed_meeting, task_scope
from app.schemas.common import Page
from app.schemas.tasks import TaskCreate, TaskEventOut, TaskOut, TaskUpdate
from app.services.meetings import validate_active_people


def overdue_condition(now: datetime):
    return and_(Task.status != "DONE", Task.due_at.is_not(None), Task.due_at < now)


def task_outputs(db: Session, actor: User, rows: list[Task], now: datetime | None = None) -> list[TaskOut]:
    now = now or utc_now()
    ids = [row.id for row in rows]
    collaborator_map = {task_id: [] for task_id in ids}
    for task_id, user_id in db.execute(select(TaskCollaborator.task_id, TaskCollaborator.user_id)
                                      .where(TaskCollaborator.task_id.in_(ids)).order_by(TaskCollaborator.user_id)):
        collaborator_map[task_id].append(user_id)
    meeting_ids = {row.meeting_id for row in rows if row.meeting_id is not None}
    titles = dict(db.execute(select(Meeting.id, Meeting.title).where(Meeting.id.in_(meeting_ids))).all())
    readable = set(db.scalars(select(Meeting.id).where(Meeting.id.in_(meeting_ids), meeting_scope(actor))))
    results = []
    for row in rows:
        result = TaskOut.model_validate(row)
        result.collaborator_ids = collaborator_map[row.id]
        result.source_meeting_title = titles.get(row.meeting_id)
        result.can_view_meeting = row.meeting_id in readable
        result.can_manage = can_manage_task(db, actor, row)
        result.can_update_status = can_update_task_status(actor, row, db)
        result.is_overdue = row.status != "DONE" and row.due_at is not None and row.due_at < now
        results.append(result)
    return results


def list_tasks(db: Session, actor: User, page: int, page_size: int, *, membership: str = "all",
               status: str | None = None, overdue: bool | None = None, meeting_id: int | None = None) -> Page[TaskOut]:
    filters = [task_scope(actor)]
    if membership == "owned":
        filters.append(Task.owner_id == actor.id)
    elif membership == "collaborating":
        filters.append(exists(select(TaskCollaborator.task_id).where(TaskCollaborator.task_id == Task.id, TaskCollaborator.user_id == actor.id)))
    if status:
        filters.append(Task.status == status)
    now = utc_now()
    if overdue is not None:
        condition = overdue_condition(now)
        filters.append(condition if overdue else ~condition)
    if meeting_id is not None:
        filters.append(Task.meeting_id == meeting_id)
    total = db.scalar(select(func.count()).select_from(Task).where(*filters))
    rows = list(db.scalars(select(Task).where(*filters).order_by(Task.created_at.desc(), Task.id.desc())
                           .offset((page - 1) * page_size).limit(page_size)))
    return Page(items=task_outputs(db, actor, rows, now), total=total, page=page, page_size=page_size)


def get_task(db: Session, actor: User, task_id: int) -> TaskOut:
    return task_outputs(db, actor, [get_task_or_404(db, actor, task_id)])[0]


def create_task(db: Session, actor: User, payload: TaskCreate) -> TaskOut:
    require_leader(actor)
    require_assign_owner(db, actor, payload.owner_id)
    if payload.meeting_id is not None:
        get_managed_meeting(db, actor, payload.meeting_id)
        db.scalar(select(Meeting).where(Meeting.id == payload.meeting_id).with_for_update())
    record = insert_task(db, actor.id, payload)
    db.commit()
    return task_outputs(db, actor, [record])[0]


def insert_task(db: Session, actor_id: int, payload: TaskCreate, *, candidate_id: int | None = None) -> Task:
    """Internal transaction helper; callers authorize and own the commit."""
    validate_active_people(db, [payload.owner_id])
    collaborators = [user_id for user_id in validate_active_people(db, payload.collaborator_ids) if user_id != payload.owner_id]
    record = Task(**payload.model_dump(exclude={"collaborator_ids", "description"}),
                  description=payload.description or payload.title, created_by_id=actor_id, candidate_id=candidate_id)
    db.add(record)
    db.flush()
    db.add_all([TaskCollaborator(task_id=record.id, user_id=user_id) for user_id in collaborators])
    db.add(TaskEvent(task_id=record.id, actor_id=actor_id, event_type="CREATED", body="创建任务",
                     changes={"candidate_id": candidate_id} if candidate_id else None))
    return record


def update_task(db: Session, actor: User, task_id: int, payload: TaskUpdate) -> TaskOut:
    require_leader(actor)
    record = get_task_or_404(db, actor, task_id, for_update=True)
    require_manage_task(db, actor, record)
    changes = payload.model_dump(exclude_unset=True)
    old_collaborators = list(db.scalars(select(TaskCollaborator.user_id).where(TaskCollaborator.task_id == task_id).order_by(TaskCollaborator.user_id)))
    collaborators = old_collaborators
    if "owner_id" in changes:
        require_assign_owner(db, actor, changes["owner_id"])
        validate_active_people(db, [changes["owner_id"]])
    if "collaborator_ids" in changes:
        collaborators = validate_active_people(db, changes.pop("collaborator_ids"))
    owner_id = changes.get("owner_id", record.owner_id)
    collaborators = [user_id for user_id in collaborators if user_id != owner_id]
    event_changes = {}
    for key, value in changes.items():
        previous = getattr(record, key)
        if previous != value:
            if key == "source_excerpt":
                # A correction may remove sensitive text; do not expose the removed excerpt via history.
                event_changes[key] = {"changed": True}
            else:
                encode = lambda item: item.isoformat() if isinstance(item, datetime) else item
                event_changes[key] = {"before": encode(previous), "after": encode(value)}
            setattr(record, key, value)
    if collaborators != old_collaborators:
        db.execute(delete(TaskCollaborator).where(TaskCollaborator.task_id == task_id))
        db.add_all([TaskCollaborator(task_id=task_id, user_id=user_id) for user_id in collaborators])
        event_changes["collaborator_ids"] = {"before": old_collaborators, "after": collaborators}
    if event_changes:
        db.add(TaskEvent(task_id=task_id, actor_id=actor.id, event_type="UPDATED", body="更新任务信息", changes=event_changes))
    db.commit()
    return task_outputs(db, actor, [record])[0]


def change_status(db: Session, actor: User, task_id: int, status: str) -> TaskOut:
    record = get_task_or_404(db, actor, task_id, for_update=True)
    if not can_update_task_status(actor, record, db):
        raise HTTPException(403, "只有任务负责人或管理者可以修改状态")
    if record.status != status:
        previous = record.status
        record.status = status
        record.completed_at = utc_now() if status == "DONE" else None
        db.add(TaskEvent(task_id=task_id, actor_id=actor.id, event_type="STATUS_CHANGED",
                         changes={"status": {"before": previous, "after": status}}))
    db.commit()
    return task_outputs(db, actor, [record])[0]


def delete_task(db: Session, actor: User, task_id: int) -> None:
    require_leader(actor)
    record = get_task_or_404(db, actor, task_id, for_update=True)
    require_manage_task(db, actor, record)
    record.deleted_at = utc_now()
    db.add(TaskEvent(task_id=task_id, actor_id=actor.id, event_type="DELETED", body="删除错误任务"))
    db.commit()


def event_output(row: TaskEvent) -> TaskEventOut:
    result = TaskEventOut.model_validate(row)
    if result.changes:
        result.changes = {key: value for key, value in result.changes.items() if key != "seed_key"} or None
    return result


def list_events(db: Session, actor: User, task_id: int, page: int, page_size: int) -> Page[TaskEventOut]:
    get_task_or_404(db, actor, task_id)
    filters = [TaskEvent.task_id == task_id]
    total = db.scalar(select(func.count()).select_from(TaskEvent).where(*filters))
    rows = db.scalars(select(TaskEvent).where(*filters).order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
                      .offset((page - 1) * page_size).limit(page_size))
    return Page(items=[event_output(row) for row in rows], total=total, page=page, page_size=page_size)


def add_progress(db: Session, actor: User, task_id: int, body: str) -> TaskEventOut:
    # Reading through the common task scope authorizes Boss, owner or collaborator.
    get_task_or_404(db, actor, task_id, for_update=True)
    event = TaskEvent(task_id=task_id, actor_id=actor.id, event_type="PROGRESS", body=body)
    db.add(event)
    db.commit()
    return event_output(event)
