import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.ai.adapters import FixtureAnalysisAdapter
from app.models import ActionItem, AnalysisRecord, Task, TaskCollaborator, TaskEvent, User
from app.services.candidates import auto_publish_analysis
from test_analysis import fixture
from test_auth_people import login, user_id
from test_workflow import setup_job, worker


def analyzed(client, db, actions=None):
    job, meeting, record, boss = setup_job(client, db)
    content = json.loads(fixture("normal"))
    if actions is not None:
        content["actions"] = actions
    asyncio.run(worker(db, FixtureAnalysisAdapter(json.dumps(content, ensure_ascii=False))).run_next())
    analysis = db.scalar(select(AnalysisRecord).where(AnalysisRecord.input_id == record["id"]))
    return analysis, meeting, record, boss


def rows(db, analysis):
    return list(db.scalars(select(ActionItem).where(ActionItem.analysis_id == analysis.id).order_by(ActionItem.position)))


def correction(db, **extra):
    payload = {"title": "补全后的任务", "owner_id": user_id(db, "zhangsan"),
               "source_excerpt": "张三明天整理接口清单，王五协助核对字段。", "collaborator_ids": []}
    return {**payload, **extra}


def test_publish_is_atomic_idempotent_and_preserves_manual_edits(client, db):
    analysis, meeting, *_ = analyzed(client, db)
    auto_publish_analysis(db, analysis.id)
    candidate = rows(db, analysis)[0]
    task = db.scalar(select(Task).where(Task.candidate_id == candidate.id))
    assert candidate.status == "PUBLISHED" and not candidate.needs_attention
    assert db.scalar(select(func.count()).select_from(TaskCollaborator).where(TaskCollaborator.task_id == task.id)) == 1
    assert client.patch(f"/api/tasks/{task.id}", json={"title": "人工修改保留", "collaborator_ids": []}).status_code == 200
    auto_publish_analysis(db, analysis.id)
    retried = client.post(f"/api/candidates/{candidate.id}/publish", json=correction(db))
    assert retried.status_code == 200 and retried.json()["title"] == "人工修改保留"
    assert retried.json()["collaborator_ids"] == []
    assert db.scalar(select(func.count()).select_from(Task).where(Task.candidate_id == candidate.id)) == 1
    assert db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task.id, TaskEvent.event_type == "CREATED")) == 1
    # The database itself enforces one task for the same candidate.
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(Task(candidate_id=candidate.id, title="重复", description="重复", owner_id=task.owner_id, created_by_id=task.created_by_id))
        db.flush()


def test_partial_bad_candidates_do_not_block_valid_work_and_boss_can_correct(client, db, existing_pending):
    normal = json.loads(fixture("normal"))["actions"][0]
    actions = [normal, {**normal, "owner": None}, {**normal, "source_quote": "不存在的原文"},
               {**normal, "kind": "DISCUSSION"}, {"broken": True}]
    analysis, meeting, *_ = analyzed(client, db, actions)
    auto_publish_analysis(db, analysis.id)
    candidates = rows(db, analysis)
    assert [r.status for r in candidates] == ["PUBLISHED", "NEEDS_INFO", "REJECTED", "DISCUSSION", "REJECTED"]
    assert client.get("/api/dashboard").json()["pending_supplement_count"] == existing_pending + 3
    path = f"/api/candidates/{candidates[1].id}/publish"
    assert client.post(path, json=correction(db, source_excerpt="伪造来源")).status_code == 422
    fixed = client.post(path, json=correction(db))
    assert fixed.status_code == 200
    assert client.post(path, json=correction(db)).json()["id"] == fixed.json()["id"]
    dismissed = client.post(f"/api/candidates/{candidates[2].id}/dismiss")
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "DISMISSED"
    auto_publish_analysis(db, analysis.id)
    assert client.get("/api/dashboard").json()["pending_supplement_count"] == existing_pending + 1
    page = client.get(f"/api/meetings/{meeting['id']}/candidates?attention_only=true&page_size=1").json()
    assert page["total"] == 1 and len(page["items"]) == 1


def test_supplement_only_adds_collaborators_and_retry_does_not_undo_later_changes(client, db, existing_pending):
    normal = json.loads(fixture("normal"))["actions"][0]
    analysis, meeting, *_ = analyzed(client, db, [{**normal, "collaborators": [{"name": "未知人员"}]}])
    auto_publish_analysis(db, analysis.id)
    candidate = rows(db, analysis)[0]
    assert candidate.status == "PUBLISHED" and candidate.needs_attention
    path = f"/api/candidates/{candidate.id}/collaborators"
    fixed = client.patch(path, json={"collaborator_ids": [user_id(db, "wangwu")]})
    task_id = fixed.json()["id"]
    assert fixed.status_code == 200 and fixed.json()["collaborator_ids"] == [user_id(db, "wangwu")]
    assert client.patch(f"/api/tasks/{task_id}", json={"collaborator_ids": []}).status_code == 200
    repeated = client.patch(path, json={"collaborator_ids": [user_id(db, "wangwu")]})
    assert repeated.json()["id"] == task_id and repeated.json()["collaborator_ids"] == []
    assert client.get("/api/dashboard").json()["pending_supplement_count"] == existing_pending + 0


def test_deleted_task_never_reappears_on_publication_retry(client, db):
    analysis, meeting, *_ = analyzed(client, db)
    auto_publish_analysis(db, analysis.id)
    candidate = rows(db, analysis)[0]
    task = db.scalar(select(Task).where(Task.candidate_id == candidate.id))
    assert client.delete(f"/api/tasks/{task.id}").status_code == 204
    auto_publish_analysis(db, analysis.id)
    assert client.post(f"/api/candidates/{candidate.id}/publish", json=correction(db)).status_code == 409
    assert client.get(f"/api/tasks/{task.id}").status_code == 404
    assert client.get(f"/api/meetings/{meeting['id']}/candidates").json()["items"][0]["task_deleted"]


@pytest.mark.parametrize("username", ["zhangsan", "lisi", "wangwu", "zhaoliu"])
def test_employees_cannot_read_or_modify_candidates(client, db, username):
    analysis, meeting, *_ = analyzed(client, db)
    auto_publish_analysis(db, analysis.id)
    candidate = rows(db, analysis)[0]
    login(client, username)
    assert client.get(f"/api/meetings/{meeting['id']}/candidates").status_code == 403
    assert client.post(f"/api/candidates/{candidate.id}/publish", json=correction(db)).status_code == 403
    assert client.post(f"/api/candidates/{candidate.id}/dismiss").status_code == 403
    assert client.patch(f"/api/candidates/{candidate.id}/collaborators", json={"collaborator_ids": []}).status_code == 403
    assert client.get("/api/dashboard").json()["pending_supplement_count"] is None


def test_disabled_owner_does_not_block_other_candidates(client, db):
    normal = json.loads(fixture("normal"))["actions"][0]
    analysis, *_ = analyzed(client, db, [normal, {**normal, "owner": {"name": "李四"}}])
    db.get(User, user_id(db, "zhangsan")).is_active = False
    db.commit()
    auto_publish_analysis(db, analysis.id)
    assert [r.status for r in rows(db, analysis)] == ["NEEDS_INFO", "PUBLISHED"]


def test_failed_publication_rolls_back_task_and_event_together(client, db, monkeypatch):
    import app.services.candidates as service
    analysis, *_ = analyzed(client, db)
    original = service.insert_task
    before = db.scalar(select(func.count()).select_from(Task))
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("interrupt before candidate commit")
    monkeypatch.setattr(service, "insert_task", interrupted)
    with pytest.raises(RuntimeError):
        auto_publish_analysis(db, analysis.id)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Task)) == before
    monkeypatch.setattr(service, "insert_task", original)
    auto_publish_analysis(db, analysis.id)
    assert db.scalar(select(func.count()).select_from(Task)) == before + 1


def test_disabled_collaborator_is_pending_but_deleted_task_no_longer_counts(client, db, existing_pending):
    analysis, meeting, *_ = analyzed(client, db)
    db.get(User, user_id(db, "wangwu")).is_active = False
    db.commit()
    auto_publish_analysis(db, analysis.id)
    candidate = rows(db, analysis)[0]
    assert candidate.status == "PUBLISHED" and candidate.needs_attention
    assert client.get("/api/dashboard").json()["pending_supplement_count"] == existing_pending + 1
    task = db.scalar(select(Task).where(Task.candidate_id == candidate.id))
    assert client.delete(f"/api/tasks/{task.id}").status_code == 204
    assert client.get("/api/dashboard").json()["pending_supplement_count"] == existing_pending + 0
    assert client.get(f"/api/meetings/{meeting['id']}/candidates?attention_only=true").json()["total"] == 0
