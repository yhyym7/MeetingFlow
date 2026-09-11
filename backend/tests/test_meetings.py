from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import Meeting, MeetingInput, ProcessingJob, User
from test_auth_people import login, user_id


def create_meeting(client, db, **overrides):
    payload = {"title": "T05 项目会议", "starts_at": "2026-09-08T10:00:00+08:00",
               "participant_ids": [user_id(db, "zhangsan"), user_id(db, "lisi")]}
    payload.update(overrides)
    response = client.post("/api/meetings", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_update_meeting_and_creator_from_session(client, db):
    login(client)
    meeting = create_meeting(client, db, participant_ids=[user_id(db, "zhangsan")] * 2)
    assert meeting["created_by_id"] == user_id(db, "boss")
    assert meeting["participant_ids"] == [user_id(db, "zhangsan")]
    assert meeting["starts_at"] == "2026-09-08T02:00:00Z"
    update = client.patch(f"/api/meetings/{meeting['id']}", json={"title": "修改后", "location": None, "participant_ids": []})
    assert update.status_code == 200 and update.json()["participant_ids"] == []
    bad = client.post("/api/meetings", json={"title": "伪造", "starts_at": "2026-09-08T10:00:00+08:00",
                                          "participant_ids": [], "created_by_id": user_id(db, "zhangsan")})
    assert bad.status_code == 422


@pytest.mark.parametrize("username,can_read", [("zhangsan", True), ("lisi", True), ("wangwu", False), ("zhaoliu", False)])
def test_meeting_http_permissions_and_filtered_total(client, db, username, can_read):
    login(client)
    meeting = create_meeting(client, db)
    saved = client.post(f"/api/meetings/{meeting['id']}/inputs", json={"request_id": str(uuid4()), "text": "会议原文"}).json()
    login(client, username)
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == (200 if can_read else 404)
    assert client.get(f"/api/meetings/{meeting['id']}/inputs/{saved['id']}").status_code == (200 if can_read else 404)
    listed = client.get("/api/meetings?q=T05").json()
    assert listed["total"] == int(can_read)
    assert len(listed["items"]) == int(can_read)
    assert client.patch(f"/api/meetings/{meeting['id']}", json={"title": "无权修改"}).status_code == 403
    assert client.post(f"/api/meetings/{meeting['id']}/inputs", json={"request_id": str(uuid4()), "text": "无权提交"}).status_code == 403
    assert client.post("/api/meetings", json={"title": "无权创建", "starts_at": "2026-09-08T10:00:00+08:00", "participant_ids": []}).status_code == 403


def test_text_versions_retry_and_conflicting_request(client, db):
    login(client)
    meeting = create_meeting(client, db)
    route = f"/api/meetings/{meeting['id']}/inputs"
    payload = {"request_id": str(uuid4()), "text": "  原文保持空格\n第二行  "}
    first = client.post(route, json=payload)
    again = client.post(route, json=payload)
    assert first.status_code == 202 and again.status_code == 202
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["text"] == payload["text"]
    assert first.json()["processing_status"] == "QUEUED"
    assert first.json()["job_id"] == again.json()["job_id"]
    assert client.post(route, json={**payload, "text": "另一份原文"}).status_code == 409
    job = db.get(ProcessingJob, first.json()["job_id"])
    job.status = "FAILED"
    db.commit()
    second = client.post(route, json={"request_id": str(uuid4()), "text": "新的输入版本"})
    assert second.json()["version"] == 2
    assert client.get(f"/api/meetings/{meeting['id']}").json()["current_input"]["id"] == second.json()["id"]
    assert db.scalar(select(func.count()).select_from(MeetingInput).where(MeetingInput.meeting_id == meeting["id"])) == 2
    assert client.get(f"{route}/{first.json()['id']}").json()["text"] == payload["text"]


def test_removed_participant_immediately_loses_read_access(client, db):
    login(client)
    meeting = create_meeting(client, db)
    login(client, "zhangsan")
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == 200
    login(client)
    assert client.patch(f"/api/meetings/{meeting['id']}", json={"participant_ids": []}).status_code == 200
    login(client, "zhangsan")
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == 404


def test_invalid_meeting_inputs_and_large_chinese_text(client, db):
    login(client)
    invalid = client.post("/api/meetings", json={"title": "缺失时区", "starts_at": "2026-09-08T10:00:00", "participant_ids": []})
    assert invalid.status_code == 422
    person = db.get(User, user_id(db, "wangwu"))
    person.is_active = False
    db.flush()
    invalid = client.post("/api/meetings", json={"title": "停用人员", "starts_at": "2026-09-08T10:00:00+08:00", "participant_ids": [person.id]})
    assert invalid.status_code == 422
    meeting = create_meeting(client, db)
    assert client.patch(f"/api/meetings/{meeting['id']}", json={"title": None}).status_code == 422
    assert client.patch(f"/api/meetings/{meeting['id']}", json={}).status_code == 422
    assert client.post(f"/api/meetings/{meeting['id']}/inputs", json={"request_id": str(uuid4()), "text": " \n "}).status_code == 422
    long_text = "中文内容" * 20000
    saved = client.post(f"/api/meetings/{meeting['id']}/inputs", json={"request_id": str(uuid4()), "text": long_text})
    assert saved.status_code == 202 and saved.json()["text"] == long_text


def test_pagination_and_cross_meeting_input_id(client, db):
    login(client)
    first = create_meeting(client, db)
    second = create_meeting(client, db)
    saved = client.post(f"/api/meetings/{first['id']}/inputs", json={"request_id": str(uuid4()), "text": "第一场内容"}).json()
    assert client.get(f"/api/meetings/{second['id']}/inputs/{saved['id']}").status_code == 404
    page = client.get("/api/meetings?q=T05&page_size=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get("/api/meetings?page_size=101").status_code == 422
