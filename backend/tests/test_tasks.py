from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import Task, TaskEvent, User
from test_auth_people import login, user_id
from test_meetings import create_meeting


def create_task(client, db, **overrides):
    payload = {"title": "T06 测试任务", "owner_id": user_id(db, "zhangsan"), "collaborator_ids": [user_id(db, "wangwu")]}
    payload.update(overrides)
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_task_creation_defaults_and_date_only_deadline(client, db):
    login(client)
    task = create_task(client, db, due_at="2026-09-10", collaborator_ids=[user_id(db, "zhangsan"), user_id(db, "wangwu")] * 2)
    assert task["collaborator_ids"] == [user_id(db, "wangwu")]
    assert task["due_at"] == "2026-09-10T15:59:00Z"
    assert task["priority"] == "NORMAL" and task["status"] == "TODO"
    assert task["description"] == task["title"]
    assert task["created_by_id"] == user_id(db, "boss")
    assert not task["can_view_meeting"]
    no_deadline = create_task(client, db)
    assert no_deadline["due_at"] is None and not no_deadline["is_overdue"]


@pytest.mark.parametrize("username,visible,status_code", [("boss", True, 200), ("zhangsan", True, 200), ("wangwu", True, 403), ("lisi", False, 404), ("zhaoliu", False, 404)])
def test_task_http_visibility_status_and_progress(client, db, username, visible, status_code):
    login(client)
    meeting = create_meeting(client, db)
    task = create_task(client, db, meeting_id=meeting["id"])
    login(client, username)
    assert client.get(f"/api/tasks/{task['id']}").status_code == (200 if visible else 404)
    assert client.get(f"/api/tasks/{task['id']}/events").status_code == (200 if visible else 404)
    assert client.patch(f"/api/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}).status_code == status_code
    progress = client.post(f"/api/tasks/{task['id']}/events", json={"body": "今天完成了字段核对"})
    assert progress.status_code == (201 if visible else 404)
    listed = client.get(f"/api/tasks?meeting_id={meeting['id']}").json()
    assert listed["total"] == int(visible)
    if username != "boss":
        assert client.patch(f"/api/tasks/{task['id']}", json={"title": "越权"}).status_code == 403
        assert client.delete(f"/api/tasks/{task['id']}").status_code == 403
        assert client.post("/api/tasks", json={"title": "越权创建", "owner_id": user_id(db, username)}).status_code == 403


def test_uninvited_collaborator_sees_only_task_source_excerpt(client, db):
    login(client)
    meeting = create_meeting(client, db)
    secret_text = "财务内部完整会议内容，不应通过任务暴露"
    client.post(f"/api/meetings/{meeting['id']}/inputs", json={"request_id": str(uuid4()), "text": secret_text})
    task = create_task(client, db, meeting_id=meeting["id"], source_excerpt="王五协助核对字段")
    login(client, "wangwu")
    response = client.get(f"/api/tasks/{task['id']}")
    assert response.json()["source_meeting_title"] == meeting["title"]
    assert response.json()["source_excerpt"] == "王五协助核对字段"
    assert not response.json()["can_view_meeting"]
    assert secret_text not in response.text
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == 404
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").status_code == 404
    login(client, "lisi")
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == 200
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()["total"] == 0


def test_complete_reopen_and_duplicate_status_have_consistent_history(client, db):
    login(client)
    task = create_task(client, db, due_at="2000-01-01")
    login(client, "zhangsan")
    done = client.patch(f"/api/tasks/{task['id']}/status", json={"status": "DONE"}).json()
    assert done["completed_at"] and not done["is_overdue"]
    count = db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task["id"]))
    again = client.patch(f"/api/tasks/{task['id']}/status", json={"status": "DONE"}).json()
    assert again["completed_at"] == done["completed_at"]
    assert db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task["id"])) == count
    reopened = client.patch(f"/api/tasks/{task['id']}/status", json={"status": "TODO"}).json()
    assert reopened["completed_at"] is None and reopened["is_overdue"]
    history = client.get(f"/api/tasks/{task['id']}/events").json()["items"]
    assert sum(event["event_type"] == "STATUS_CHANGED" for event in history) == 2


def test_boss_reassigns_and_removed_users_lose_access(client, db):
    login(client)
    task = create_task(client, db)
    changed = client.patch(f"/api/tasks/{task['id']}", json={"owner_id": user_id(db, "lisi"), "collaborator_ids": []})
    assert changed.status_code == 200 and changed.json()["collaborator_ids"] == []
    for username in ("zhangsan", "wangwu"):
        login(client, username)
        assert client.get(f"/api/tasks/{task['id']}").status_code == 404
        assert client.get(f"/api/tasks/{task['id']}/events").status_code == 404
    login(client, "lisi")
    assert client.get(f"/api/tasks/{task['id']}").status_code == 200


def test_soft_delete_filters_task_events_and_lists(client, db):
    login(client)
    meeting = create_meeting(client, db)
    task = create_task(client, db, meeting_id=meeting["id"])
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert db.get(Task, task["id"]).deleted_at is not None
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404
    assert client.get(f"/api/tasks/{task['id']}/events").status_code == 404
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()["total"] == 0


def test_owned_collaborating_and_overdue_filters(client, db):
    login(client)
    meeting = create_meeting(client, db)
    task = create_task(client, db, meeting_id=meeting["id"], due_at="2000-01-01")
    login(client, "wangwu")
    assert client.get(f"/api/tasks?meeting_id={meeting['id']}&membership=owned").json()["total"] == 0
    assert client.get(f"/api/tasks?meeting_id={meeting['id']}&membership=collaborating&overdue=true").json()["total"] == 1
    assert client.get(f"/api/tasks?meeting_id={meeting['id']}&overdue=false").json()["total"] == 0
    login(client)
    client.patch(f"/api/tasks/{task['id']}", json={"due_at": None})
    assert client.get(f"/api/tasks?meeting_id={meeting['id']}&overdue=false").json()["total"] == 1


def test_bad_inputs_and_source_correction_history(client, db):
    login(client)
    task = create_task(client, db, source_excerpt="应移除的原始摘录")
    assert client.patch(f"/api/tasks/{task['id']}", json={"source_excerpt": "修正后的摘录"}).status_code == 200
    assert "应移除的原始摘录" not in client.get(f"/api/tasks/{task['id']}/events").text
    for payload in ({"owner_id": 2147483647}, {"title": None}, {"due_at": "2026-09-09T12:00:00"}, {"status": "DONE"}):
        assert client.patch(f"/api/tasks/{task['id']}", json=payload).status_code == 422
    assert client.post(f"/api/tasks/{task['id']}/events", json={"body": " \n "}).status_code == 422
    assert client.get("/api/tasks?page_size=101").status_code == 422
    person = db.get(User, user_id(db, "zhaoliu"))
    person.is_active = False
    db.flush()
    assert client.patch(f"/api/tasks/{task['id']}", json={"collaborator_ids": [person.id]}).status_code == 422
