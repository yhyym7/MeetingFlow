import asyncio
from contextlib import nullcontext
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.ai.adapters import FixtureAnalysisAdapter, UnconfiguredAnalysisAdapter
from app.ai.workflow import AnalysisWorker
from app.models import ActionItem, AnalysisRecord, MeetingInput, ProcessingJob, Task, TaskEvent
from test_analysis import fixture, request
from test_auth_people import login
from test_candidates import correction
from test_meetings import create_meeting
from test_workflow import worker


def submit(client, meeting, **extra):
    payload = {"request_id": str(uuid4()), "text": request().text, **extra}
    response = client.post(f"/api/meetings/{meeting['id']}/inputs", json=payload)
    assert response.status_code == 202, response.text
    return response.json(), payload


def test_submit_runs_full_graph_and_network_retry_reuses_input_job_and_task(client, db):
    login(client)
    meeting = create_meeting(client, db)
    record, payload = submit(client, meeting)
    route = f"/api/meetings/{meeting['id']}/inputs"
    assert record["processing_status"] == "QUEUED"
    assert client.post(route, json=payload).json()["job_id"] == record["job_id"]
    assert client.post(route, json={**payload, "request_id": str(uuid4())}).status_code == 409
    assert db.scalar(select(func.count()).select_from(MeetingInput).where(MeetingInput.meeting_id == meeting["id"])) == 1
    adapter = FixtureAnalysisAdapter(fixture("normal"))
    asyncio.run(worker(db, adapter).run_next())
    job = client.get(f"/api/jobs/{record['job_id']}").json()
    assert job["status"] == "SUCCEEDED" and job["scope"] == "FULL_PIPELINE" and job["stage"] == "COMPLETE"
    assert db.get(ProcessingJob, record["job_id"]).node_trace == ["LOAD", "ANALYZE", "VALIDATE", "PERSIST", "PUBLISH", "COMPLETE"]
    repeated = client.post(route, json=payload).json()
    assert repeated["id"] == record["id"] and repeated["processing_status"] == "SUCCEEDED"
    assert client.get(f"/api/meetings/{meeting['id']}").json()["current_input"]["job_id"] == record["job_id"]
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()["total"] == 1
    assert not asyncio.run(worker(db, adapter).run_next()) and adapter.analyze_calls == 1
    login(client, "wangwu")
    task = client.get(f"/api/tasks?meeting_id={meeting['id']}").json()["items"][0]
    assert not task["can_view_meeting"] and task["source_excerpt"] == request().text
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == 404


def test_new_version_requires_selective_build_and_preserves_existing_task(client, db):
    login(client)
    meeting = create_meeting(client, db)
    first, _ = submit(client, meeting)
    asyncio.run(worker(db, FixtureAnalysisAdapter(fixture("normal"))).run_next())
    task = client.get(f"/api/meetings/{meeting['id']}/tasks").json()["items"][0]
    client.patch(f"/api/tasks/{task['id']}", json={"title": "保留人工修改"})
    second, _ = submit(client, meeting, text=request().text + "\n补充会议内容")
    assert second["version"] == 2
    assert client.get(f"/api/meetings/{meeting['id']}/analysis").status_code == 404
    asyncio.run(worker(db, FixtureAnalysisAdapter(fixture("normal"))).run_next())
    items = client.get(f"/api/meetings/{meeting['id']}/candidates").json()["items"]
    assert len(items) == 1 and items[0]["status"] == "REVIEW"
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()["total"] == 1
    assert client.get(f"/api/tasks/{task['id']}").json()["title"] == "保留人工修改"
    result = client.post(f"/api/candidates/{items[0]['id']}/publish", json=correction(db))
    assert result.status_code == 200 and result.json()["id"] != task["id"]


def test_retry_after_publication_commit_does_not_call_model_or_republish(client, db):
    login(client)
    meeting = create_meeting(client, db)
    record, _ = submit(client, meeting)
    class Interrupted(AnalysisWorker):
        async def complete(self, state):
            raise RuntimeError("simulated crash after publication commit")
    asyncio.run(Interrupted(FixtureAnalysisAdapter(fixture("normal")), lambda: nullcontext(db)).run_next())
    job = db.get(ProcessingJob, record["job_id"])
    assert job.status == "FAILED"
    task = client.get(f"/api/meetings/{meeting['id']}/tasks").json()["items"][0]
    client.patch(f"/api/tasks/{task['id']}", json={"title": "人工纠正"})
    assert client.post(f"/api/jobs/{job.id}/retry").status_code == 202
    asyncio.run(worker(db, UnconfiguredAnalysisAdapter()).run_next())
    db.refresh(job)
    assert job.status == "SUCCEEDED" and job.analysis_attempts == 1
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()["total"] == 1
    assert client.get(f"/api/tasks/{task['id']}").json()["title"] == "人工纠正"
    assert db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task["id"], TaskEvent.event_type == "CREATED")) == 1


def test_input_and_job_creation_roll_back_together(client, db, monkeypatch):
    import app.services.jobs as jobs
    login(client)
    meeting = create_meeting(client, db)
    def interrupted(*args, **kwargs):
        raise RuntimeError("interrupted between input and queue")
    monkeypatch.setattr(jobs, "create_analysis_job", interrupted)
    with pytest.raises(RuntimeError):
        submit(client, meeting)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(MeetingInput).where(MeetingInput.meeting_id == meeting["id"])) == 0
    assert db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.meeting_id == meeting["id"])) == 0


def test_unconfigured_model_fails_explicitly_and_can_retry_saved_input(client, db):
    login(client)
    meeting = create_meeting(client, db)
    record, payload = submit(client, meeting)
    asyncio.run(worker(db, UnconfiguredAnalysisAdapter()).run_next())
    job = client.get(f"/api/jobs/{record['job_id']}").json()
    assert job["status"] == "FAILED" and job["error_code"] == "ANALYSIS_NOT_CONFIGURED"
    repeated = client.post(f"/api/meetings/{meeting['id']}/inputs", json=payload).json()
    assert repeated["processing_status"] == "FAILED" and repeated["job_id"] == record["job_id"]
    assert client.post(f"/api/jobs/{record['job_id']}/retry").status_code == 202
    asyncio.run(worker(db, FixtureAnalysisAdapter(fixture("normal"))).run_next())
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()["total"] == 1


def test_new_version_without_prior_tasks_can_publish_and_stale_candidate_cannot(client, db, existing_pending):
    login(client)
    meeting = create_meeting(client, db)
    first, _ = submit(client, meeting)
    asyncio.run(worker(db, FixtureAnalysisAdapter(fixture("missing_owner"))).run_next())
    old_candidates = client.get(f"/api/meetings/{meeting['id']}/candidates").json()["items"]
    second, _ = submit(client, meeting)
    assert client.post(f"/api/candidates/{old_candidates[0]['id']}/publish", json=correction(db)).status_code == 409
    asyncio.run(worker(db, FixtureAnalysisAdapter(fixture("normal"))).run_next())
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()["total"] == 1
    assert client.get("/api/dashboard").json()["pending_supplement_count"] == existing_pending + 0
