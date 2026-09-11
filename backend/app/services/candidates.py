from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.ai.resolution import ResolvedCandidate
from app.models import ActionItem, AnalysisRecord, Meeting, MeetingInput, Task, TaskCollaborator, TaskEvent, User
from app.permissions import get_managed_meeting, require_leader, require_assign_owner, require_manage_task, get_task_or_404, task_scope, meeting_management_scope, can_manage_meeting
from app.schemas.candidates import CandidateOut, CandidatePublish
from app.schemas.common import Page
from app.schemas.tasks import TaskCreate
from app.services.meetings import validate_active_people
from app.services.tasks import insert_task, task_outputs


def current_input_condition():
    newer = MeetingInput.__table__.alias("newer_input")
    return ~exists(select(newer.c.id).where(newer.c.meeting_id == MeetingInput.meeting_id,
                                           newer.c.version > MeetingInput.version))


def pending_count(db: Session, actor: User | None = None) -> int:
    return db.scalar(select(func.count(ActionItem.id)).join(AnalysisRecord).join(MeetingInput)
                     .join(Meeting, Meeting.id == MeetingInput.meeting_id)
                     .where(current_input_condition(), attention_condition(), meeting_management_scope(actor) if actor else True))


def attention_condition():
    return ActionItem.needs_attention.is_(True) & ~exists(select(Task.id).where(
        Task.candidate_id == ActionItem.id, Task.deleted_at.is_not(None)))


def candidate_output(db: Session, row: ActionItem, actor: User | None = None) -> CandidateOut:
    result = CandidateOut.model_validate(row)
    task = db.scalar(select(Task).where(Task.candidate_id == row.id))
    if task and (actor is None or db.scalar(select(Task.id).where(Task.id == task.id, task_scope(actor))) is not None or actor.role == "BOSS"):
        result.task_id, result.task_deleted = task.id, task.deleted_at is not None
    return result


def list_candidates(db: Session, actor: User, meeting_id: int, page: int, page_size: int,
                    *, attention_only: bool = False) -> Page[CandidateOut]:
    require_leader(actor)
    get_managed_meeting(db, actor, meeting_id)
    query = select(ActionItem).join(AnalysisRecord).join(MeetingInput).where(
        MeetingInput.meeting_id == meeting_id, current_input_condition())
    if attention_only:
        query = query.where(attention_condition())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(ActionItem.position).offset((page - 1) * page_size).limit(page_size))
    return Page(items=[candidate_output(db, row, actor) for row in rows], total=total, page=page, page_size=page_size)


def lock_candidate(db: Session, actor: User, candidate_id: int) -> tuple[ActionItem, MeetingInput]:
    require_leader(actor)
    record = db.scalar(select(MeetingInput).join(AnalysisRecord).join(ActionItem)
                       .where(ActionItem.id == candidate_id))
    if record is None:
        raise HTTPException(404, "候选事项不存在")
    # Same lock order as input submission and automatic publication.
    get_managed_meeting(db, actor, record.meeting_id, for_update=True)
    row = db.scalar(select(ActionItem).where(ActionItem.id == candidate_id).with_for_update()
                    .execution_options(populate_existing=True))
    return row, record


def require_current(db: Session, record: MeetingInput):
    latest = db.scalar(select(MeetingInput.id).where(MeetingInput.meeting_id == record.meeting_id)
                       .order_by(MeetingInput.version.desc()).limit(1).with_for_update())
    if latest != record.id:
        raise HTTPException(409, "会议已有新输入，请处理当前版本的候选事项")


def existing_task(db: Session, candidate_id: int) -> Task | None:
    task = db.scalar(select(Task).where(Task.candidate_id == candidate_id).with_for_update()
                     .execution_options(populate_existing=True))
    if task and task.deleted_at is not None:
        raise HTTPException(409, "该候选对应的任务已删除，不会重复创建")
    return task


def insert_candidate_task(db: Session, row: ActionItem, record: MeetingInput, actor_id: int, payload: TaskCreate) -> Task:
    # Shared by automatic publication and Boss correction; commit belongs to caller.
    task = existing_task(db, row.id)
    if task:
        return task
    if not payload.source_excerpt or not payload.source_excerpt.strip() or payload.source_excerpt not in record.text:
        raise HTTPException(422, "来源摘录必须对应当前会议原文")
    task = insert_task(db, actor_id, payload, candidate_id=row.id)
    row.status = "PUBLISHED"
    row.needs_attention = bool(row.resolved.get("unresolved_collaborators"))
    return task


def auto_publish_analysis(db: Session, analysis_id: int):
    analysis = db.get(AnalysisRecord, analysis_id)
    record = db.get(MeetingInput, analysis.input_id)
    db.scalar(select(Meeting).where(Meeting.id == record.meeting_id).with_for_update())
    rows = list(db.scalars(select(ActionItem).where(ActionItem.analysis_id == analysis_id)
                          .order_by(ActionItem.position).with_for_update()))
    if not rows:
        for raw in analysis.resolved_candidates:
            resolved = ResolvedCandidate.model_validate(raw)
            row = ActionItem(analysis_id=analysis_id, position=resolved.index, status=resolved.disposition,
                             resolved=raw, needs_attention=resolved.disposition != "DISCUSSION")
            db.add(row)
            rows.append(row)
        db.flush()
    # Prior published work, including soft-deleted/manual tasks, prevents a new version from reassigning it.
    own_ids = [row.id for row in rows]
    previous_task = db.scalar(select(Task.id).where(Task.meeting_id == record.meeting_id,
        or_(Task.candidate_id.is_(None), Task.candidate_id.not_in(own_ids))).limit(1).with_for_update())
    latest = db.scalar(select(MeetingInput.id).where(MeetingInput.meeting_id == record.meeting_id)
                       .order_by(MeetingInput.version.desc()).limit(1).with_for_update())
    allow_auto = previous_task is None and latest == record.id
    publisher = db.scalar(select(User).where(User.id == record.created_by_id).with_for_update().execution_options(populate_existing=True))
    meeting = db.get(Meeting, record.meeting_id)
    for row in rows:
        if row.status != "READY":
            continue
        if not allow_auto:
            row.status = "REVIEW"
            continue
        resolved = ResolvedCandidate.model_validate(row.resolved)
        item = resolved.candidate
        # Recheck current authority: queued work cannot retain an old role/department grant.
        try:
            if publisher is None or not can_manage_meeting(publisher, meeting):
                raise HTTPException(403, "提交人已无会议管理权限，请由 Boss 处理")
            require_assign_owner(db, publisher, resolved.owner_id)
        except HTTPException as exc:
            row.status = "NEEDS_INFO"
            row.resolved = {**row.resolved, "issues": [*resolved.issues, str(exc.detail)]}
            continue
        # People can be disabled after analysis. A bad candidate must not block its siblings.
        try:
            validate_active_people(db, [resolved.owner_id])
        except HTTPException:
            row.status = "NEEDS_INFO"
            row.resolved = {**row.resolved, "issues": [*resolved.issues, "发布时负责人已停用或不存在"]}
            continue
        active_collaborators = []
        for user_id in resolved.collaborator_ids:
            try:
                validate_active_people(db, [user_id])
                active_collaborators.append(user_id)
            except HTTPException:
                # Preserve the name for Boss correction, without blocking the owner.
                user = db.get(User, user_id)
                row.resolved = {**row.resolved,
                    "unresolved_collaborators": [*row.resolved.get("unresolved_collaborators", []),
                                                 {"name": user.name if user else "已失效人员"}],
                    "issues": [*row.resolved.get("issues", []), "发布时协作人已停用或不存在"]}
        payload = TaskCreate(title=item.title, description=item.description, owner_id=resolved.owner_id,
                             collaborator_ids=active_collaborators, meeting_id=record.meeting_id,
                             source_excerpt=item.source_quote, due_at=resolved.due_at, priority=item.priority)
        insert_candidate_task(db, row, record, record.created_by_id, payload)
    db.commit()


def publish_candidate(db: Session, actor: User, candidate_id: int, payload: CandidatePublish):
    row, record = lock_candidate(db, actor, candidate_id)
    task = existing_task(db, row.id)
    if task is None:
        require_current(db, record)
        require_assign_owner(db, actor, payload.owner_id)
        task = insert_candidate_task(db, row, record, actor.id,
                                     TaskCreate(**payload.model_dump(), meeting_id=record.meeting_id))
        # Explicitly supplied personnel complete the correction; retain original evidence in analyses.
        row.resolved = {**row.resolved, "unresolved_collaborators": []}
        row.needs_attention = False
    get_task_or_404(db, actor, task.id)
    db.commit()
    return task_outputs(db, actor, [task])[0]


def dismiss_candidate(db: Session, actor: User, candidate_id: int):
    row, record = lock_candidate(db, actor, candidate_id)
    require_current(db, record)
    if row.status == "PUBLISHED":
        raise HTTPException(409, "已生成任务，请在任务中修改或删除")
    row.status, row.needs_attention = "DISMISSED", False
    db.commit()
    return candidate_output(db, row, actor)


def supplement_collaborators(db: Session, actor: User, candidate_id: int, ids: list[int]):
    row, record = lock_candidate(db, actor, candidate_id)
    task = existing_task(db, row.id)
    if task is None:
        raise HTTPException(409, "请先补充负责人并生成任务")
    require_manage_task(db, actor, task)
    if row.needs_attention:
        additions = validate_active_people(db, ids)
        existing = set(db.scalars(select(TaskCollaborator.user_id).where(TaskCollaborator.task_id == task.id)))
        added = sorted(set(additions) - existing - {task.owner_id})
        db.add_all([TaskCollaborator(task_id=task.id, user_id=id_) for id_ in added])
        if added:
            db.add(TaskEvent(task_id=task.id, actor_id=actor.id, event_type="UPDATED", body="补充协作人",
                             changes={"collaborator_ids": {"before": sorted(existing), "after": sorted(existing | set(added))}}))
        row.resolved = {**row.resolved, "unresolved_collaborators": []}
        row.needs_attention = False
    get_task_or_404(db, actor, task.id)
    db.commit()
    return task_outputs(db, actor, [task])[0]
