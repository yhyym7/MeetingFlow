from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Meeting, MeetingChunk, MeetingInput, User
from app.permissions import meeting_scope, require_known_user
from app.schemas.assistant import AssistantAnswer, Source
from app.services.candidates import current_input_condition
from app.services.dashboard import get_dashboard
from app.services.meetings import list_meetings
from app.services.tasks import list_tasks


def query_tasks(db: Session, actor: User, *, overdue: bool = False) -> AssistantAnswer:
    result = list_tasks(db, actor, 1, 5, overdue=True if overdue else None)
    title = "逾期任务" if overdue else "相关任务"
    return AssistantAnswer(answer=f"你的授权范围内共有 {result.total} 项{title}。" + ("下方展示最多 5 项。" if result.total else "当前没有匹配事项。"),
                           sources=[Source(kind="task", id=row.id, title=row.title) for row in result.items], tool_calls=1)


def query_meetings(db: Session, actor: User) -> AssistantAnswer:
    dashboard = get_dashboard(db, actor)
    rows = dashboard.upcoming_meetings
    return AssistantAnswer(answer="以下是你有权查看的近期会议（最多 5 场）。" if rows else "当前没有你有权查看的即将开始的会议。",
                           sources=[Source(kind="meeting", id=row.id, title=row.title) for row in rows], tool_calls=1)


def query_statistics(db: Session, actor: User) -> AssistantAnswer:
    stats = get_dashboard(db, actor).statistics
    return AssistantAnswer(answer=f"你的授权范围内共有 {stats.total} 项任务：待开始 {stats.todo} 项，进行中 {stats.in_progress} 项，已完成 {stats.done} 项。其中未完成且逾期 {stats.overdue} 项，今日到期 {stats.due_today} 项。", tool_calls=1)


def search_meetings(db: Session, actor: User, keyword: str) -> AssistantAnswer:
    require_known_user(actor)
    # Permission and latest-version filtering happen in SQL, before reading any text.
    rows = db.execute(select(Meeting.id, Meeting.title, MeetingInput.id, MeetingInput.version, MeetingChunk)
        .select_from(Meeting)
        .join(MeetingInput, MeetingInput.meeting_id == Meeting.id)
        .join(MeetingChunk, MeetingChunk.input_id == MeetingInput.id)
        .where(meeting_scope(actor), current_input_condition(), MeetingChunk.text.contains(keyword, autoescape=True))
        .order_by(Meeting.starts_at.desc(), Meeting.id.desc(), MeetingChunk.position).limit(5)).all()
    sources = []
    for meeting_id, title, input_id, version, chunk in rows:
        sources.append(Source(kind="meeting", id=meeting_id, title=title, excerpt=chunk.text,
                              input_id=input_id, input_version=version, chunk_id=chunk.id,
                              start_offset=chunk.start_offset, end_offset=chunk.end_offset))
    return AssistantAnswer(answer=f"在当前有权查看的会议原文中找到 {len(sources)} 个相关片段（最多 5 个）。" if sources else "在当前有权查看的会议原文中没有找到该关键词。",
                           sources=sources, search_mode="keyword", tool_calls=1)
