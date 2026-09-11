import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.contracts import ActionCandidate, AnalysisResult, PersonReference
from app.models import Department, User
from app.permissions import effective_participant_ids


SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DirectoryPerson:
    id: int
    name: str
    department: str | None
    participant: bool = False


class ResolvedCandidate(BaseModel):
    index: int
    disposition: Literal["READY", "NEEDS_INFO", "REJECTED", "DISCUSSION"]
    candidate: ActionCandidate | None
    owner_id: int | None = None
    collaborator_ids: list[int] = Field(default_factory=list)
    unresolved_collaborators: list[PersonReference] = Field(default_factory=list)
    due_at: datetime | None = None
    source_start: int | None = None
    source_end: int | None = None
    issues: list[str] = Field(default_factory=list)


def load_directory(db: Session, meeting_id: int) -> list[DirectoryPerson]:
    participants = set(effective_participant_ids(db, meeting_id))
    rows = db.execute(select(User.id, User.name, Department.name).outerjoin(Department, User.department_id == Department.id)
                      .where(User.is_active.is_(True), User.role.in_(["BOSS", "EMPLOYEE", "MANAGER"]))).all()
    return [DirectoryPerson(id=id_, name=name, department=department, participant=id_ in participants)
            for id_, name, department in rows]


def resolve_person(reference: PersonReference | None, people: list[DirectoryPerson]) -> tuple[int | None, str | None]:
    if reference is None:
        return None, "没有明确负责人"
    matches = [person for person in people if person.name == reference.name
               and (reference.department is None or person.department == reference.department)]
    preferred = [person for person in matches if person.participant]
    candidates = preferred or matches
    if len(candidates) == 1:
        return candidates[0].id, None
    if len(candidates) > 1:
        return None, f"姓名“{reference.name}”存在多个匹配，需补充部门或具体人员"
    return None, f"未找到启用人员“{reference.name}”"


def resolve_deadline(raw: str | None, meeting_at: datetime) -> tuple[datetime | None, str | None]:
    if not raw or not raw.strip():
        return None, None
    if meeting_at.tzinfo is None or meeting_at.utcoffset() is None:
        raise ValueError("Meeting datetime must include a timezone")
    text = raw.strip()
    base = meeting_at.astimezone(SHANGHAI).date()
    try:
        # Explicit ISO timestamps with an offset retain their exact instant.
        if "T" in text:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(UTC), None
            return None, "具体时间缺少时区，保留原表述"
        hour, minute = 23, 59
        clock = re.search(r"\s*(\d{1,2}):(\d{2})$", text)
        if clock:
            hour, minute = int(clock[1]), int(clock[2])
            text = text[:clock.start()].strip()
        clock_time = time(hour, minute)
        target = None
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
            year, month, day = map(int, text.split("-"))
            target = date(year, month, day)
        elif match := re.fullmatch(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]", text):
            target = date(int(match[1]) if match[1] else base.year, int(match[2]), int(match[3]))
            if not match[1] and target < base:
                return None, "缺少年份且日期已过，保留原表述"
        elif text in {"今天", "明天", "后天"}:
            target = base + timedelta(days={"今天": 0, "明天": 1, "后天": 2}[text])
        elif match := re.fullmatch(r"(\d{1,3}|一|二|两|三|四|五|六|七|八|九|十)天后", text):
            chinese = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            days = int(match[1]) if match[1].isdigit() else chinese[match[1]]
            target = base + timedelta(days=days)
        elif match := re.fullmatch(r"(本|下|下下)?(?:周|星期)([一二三四五六日天])", text):
            weekday = "一二三四五六日".index(match[2].replace("天", "日"))
            offset = {None: 0, "本": 0, "下": 1, "下下": 2}[match[1]]
            target = base - timedelta(days=base.weekday()) + timedelta(weeks=offset, days=weekday)
            if match[1] is None and target < base:
                return None, "星期表述存在跨周歧义，保留原表述"
        if target is not None:
            return datetime.combine(target, clock_time, tzinfo=SHANGHAI).astimezone(UTC), None
    except (ValueError, OverflowError):
        return None, "日期或时间不合法，保留原表述"
    return None, "期限表述不够明确，保留原表述"


def resolve_candidates(result: AnalysisResult, text: str, meeting_at: datetime,
                       people: list[DirectoryPerson]) -> list[ResolvedCandidate]:
    resolved = []
    for parsed in result.candidates:
        candidate = parsed.value
        row = ResolvedCandidate(index=parsed.index, disposition="REJECTED", candidate=candidate)
        if candidate is None:
            row.issues.append(parsed.error or "候选结构错误")
            resolved.append(row)
            continue
        start = text.find(candidate.source_quote)
        if start < 0 or not candidate.source_quote.strip():
            row.issues.append("来源摘录无法对应会议原文")
            resolved.append(row)
            continue
        row.source_start, row.source_end = start, start + len(candidate.source_quote)
        if candidate.kind == "DISCUSSION":
            row.disposition = "DISCUSSION"
            row.issues.append("只有讨论或建议，不自动派发")
            resolved.append(row)
            continue
        row.owner_id, owner_issue = resolve_person(candidate.owner, people)
        row.disposition = "READY" if row.owner_id is not None else "NEEDS_INFO"
        if owner_issue:
            row.issues.append(owner_issue)
        for reference in candidate.collaborators:
            person_id, issue = resolve_person(reference, people)
            if person_id is None:
                row.unresolved_collaborators.append(reference)
                row.issues.append(f"协作人待补充：{issue}")
            elif person_id != row.owner_id and person_id not in row.collaborator_ids:
                row.collaborator_ids.append(person_id)
        row.due_at, deadline_issue = resolve_deadline(candidate.deadline_text, meeting_at)
        if deadline_issue:
            row.issues.append(deadline_issue)
        resolved.append(row)
    return resolved
