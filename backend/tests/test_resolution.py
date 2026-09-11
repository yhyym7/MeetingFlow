import asyncio
import json
from datetime import UTC, datetime

import pytest

from app.ai.adapters import FixtureAnalysisAdapter
from app.ai.analysis import analyze_text
from app.ai.contracts import PersonReference
from app.ai.resolution import DirectoryPerson, load_directory, resolve_candidates, resolve_deadline, resolve_person
from test_analysis import fixture, request


PEOPLE = [DirectoryPerson(1, "张三", "技术部", True), DirectoryPerson(2, "张三", "产品部"),
          DirectoryPerson(3, "王五", "产品部"), DirectoryPerson(4, "同名", "技术部"), DirectoryPerson(5, "同名", "产品部")]


def test_person_resolution_prefers_participants_then_explicit_department():
    assert resolve_person(PersonReference(name="张三"), PEOPLE)[0] == 1
    assert resolve_person(PersonReference(name="张三", department="产品部"), PEOPLE)[0] == 2
    assert resolve_person(PersonReference(name="同名"), PEOPLE)[0] is None
    assert resolve_person(PersonReference(name="张山"), PEOPLE)[0] is None
    assert resolve_person(None, PEOPLE)[0] is None
    assert resolve_person(PersonReference(name="张三", department="未知部"), PEOPLE)[0] is None


@pytest.mark.parametrize("text,expected", [
    ("明天", "2026-09-08T15:59:00+00:00"),
    ("后天", "2026-09-09T15:59:00+00:00"),
    ("三天后", "2026-09-10T15:59:00+00:00"),
    ("下周一", "2026-09-14T15:59:00+00:00"),
    ("本周五", "2026-09-11T15:59:00+00:00"),
    ("明天 14:30", "2026-09-08T06:30:00+00:00"),
    ("2026年9月10日", "2026-09-10T15:59:00+00:00"),
    ("9月10日", "2026-09-10T15:59:00+00:00"),
    ("2026-09-10T18:00:00+08:00", "2026-09-10T10:00:00+00:00"),
])
def test_deadlines_are_based_on_meeting_date(text, expected):
    value, issue = resolve_deadline(text, datetime(2026, 9, 7, 2, tzinfo=UTC))
    assert value.isoformat() == expected and issue is None


@pytest.mark.parametrize("text", ["尽快", "有空时", "2026-02-30", "明天 25:00", "1月1日", "2026-09-10T18:00:00"])
def test_uncertain_deadlines_remain_unset(text):
    value, issue = resolve_deadline(text, datetime(2026, 9, 7, 2, tzinfo=UTC))
    assert value is None and issue


def test_missing_deadline_and_cross_year_relative_date():
    assert resolve_deadline(None, request().meeting_at) == (None, None)
    value, issue = resolve_deadline("明天", datetime(2026, 12, 31, 2, tzinfo=UTC))
    assert value.isoformat() == "2027-01-01T15:59:00+00:00" and issue is None
    value, issue = resolve_deadline("周一", datetime(2026, 9, 9, 2, tzinfo=UTC))
    assert value is None and issue


def test_candidates_missing_owners_collaborators_and_invalid_sources():
    raw = json.loads(fixture("normal"))
    normal = raw["actions"][0]
    raw["actions"] = [normal,
        {**normal, "owner": None},
        {**normal, "source_quote": "原文中不存在的内容"},
        {**normal, "kind": "DISCUSSION"},
        {**normal, "collaborators": [{"name": "同名"}], "deadline_text": "尽快"},
        {"title": "结构错误"},
    ]
    result = asyncio.run(analyze_text(FixtureAnalysisAdapter(json.dumps(raw)), request()))
    rows = resolve_candidates(result, request().text, request().meeting_at, PEOPLE)
    assert [row.disposition for row in rows] == ["READY", "NEEDS_INFO", "REJECTED", "DISCUSSION", "READY", "REJECTED"]
    assert rows[0].owner_id == 1 and rows[0].collaborator_ids == [3]
    assert request().text[rows[0].source_start:rows[0].source_end] == normal["source_quote"]
    assert rows[4].unresolved_collaborators and rows[4].due_at is None


def test_directory_uses_active_people_and_real_participation(db):
    from scripts.seed_demo import seed_demo
    from app.models import Meeting, User
    from sqlalchemy import select
    seed_demo(db, "test-password-T09")
    meeting_id = db.scalar(select(Meeting.id).limit(1))
    people = load_directory(db, meeting_id)
    zhangsan = next(person for person in people if person.name == "张三")
    assert zhangsan.participant and zhangsan.department == "技术部"
    user = db.get(User, zhangsan.id)
    user.is_active = False
    db.flush()
    assert zhangsan.id not in {person.id for person in load_directory(db, meeting_id)}
