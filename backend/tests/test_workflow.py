import asyncio
from contextlib import nullcontext
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.ai.adapters import AnalysisError, FixtureAnalysisAdapter, UnconfiguredAnalysisAdapter
from app.ai.workflow import AnalysisWorker
from app.models import AnalysisRecord, ProcessingJob, Task, User
from app.services.jobs import create_analysis_job, retry_job
from app.services.meetings import save_text_input
from app.schemas.meetings import TextInputCreate
from test_analysis import fixture, request
from test_auth_people import login, user_id
from test_meetings import create_meeting


def setup_job(client, db):
    login(client)
    meeting = create_meeting(client, db)
    boss = db.get(User, user_id(db, "boss"))
    # These checks deliberately exercise the analysis-only diagnostic scope.
    record, _ = save_text_input(db, boss, meeting["id"], TextInputCreate(request_id=uuid4(), text=request().text))
    record = {"id": record.id}
    job = create_analysis_job(db, boss, record["id"])
    return job, meeting, record, boss


def worker(db, adapter):
    return AnalysisWorker(adapter, lambda: nullcontext(db), retry_delay=0)


def test_real_langgraph_executes_and_persists_analysis_without_publishing(client, db):
    job, meeting, record, boss = setup_job(client, db)
    adapter = FixtureAnalysisAdapter(fixture("normal"))
    before = db.scalar(select(func.count()).select_from(Task))
    assert asyncio.run(worker(db, adapter).run_next())
    db.refresh(job)
    assert job.status == "SUCCEEDED" and job.stage == "COMPLETE_ANALYSIS"
    assert job.node_trace == ["LOAD", "ANALYZE", "VALIDATE", "PERSIST", "COMPLETE_ANALYSIS"]
    analysis = db.scalar(select(AnalysisRecord).where(AnalysisRecord.input_id == record["id"]))
    assert analysis.mode == "fixture" and analysis.resolved_candidates[0]["disposition"] == "READY"
    assert db.scalar(select(func.count()).select_from(Task)) == before
    assert create_analysis_job(db, boss, record["id"]).id == job.id
    assert not asyncio.run(worker(db, adapter).run_next())
    assert adapter.analyze_calls == 1


def test_transient_errors_retry_twice_then_fail_safely(client, db):
    job, *_ = setup_job(client, db)
    class FailingAdapter(FixtureAnalysisAdapter):
        async def analyze(self, request):
            self.analyze_calls += 1
            raise RuntimeError("secret-transport-key")
    adapter = FailingAdapter("")
    asyncio.run(worker(db, adapter).run_next())
    db.refresh(job)
    assert job.status == "FAILED" and adapter.analyze_calls == 3
    assert job.analysis_attempts == 3 and job.error_code == "ANALYSIS_PROVIDER_ERROR"
    assert "secret-transport-key" not in client.get(f"/api/jobs/{job.id}").text


def test_success_after_temporary_failure_and_invalid_structure_no_extra_retries(client, db):
    job, *_ = setup_job(client, db)
    class FlakyAdapter(FixtureAnalysisAdapter):
        async def analyze(self, request):
            if self.analyze_calls == 0:
                self.analyze_calls += 1
                raise AnalysisError("ANALYSIS_TIMEOUT", retryable=True)
            return await super().analyze(request)
    adapter = FlakyAdapter(fixture("normal"))
    asyncio.run(worker(db, adapter).run_next())
    assert job.status == "SUCCEEDED" and adapter.analyze_calls == 2
    second, *_ = setup_job(client, db)
    invalid = FixtureAnalysisAdapter(fixture("invalid"))
    asyncio.run(worker(db, invalid).run_next())
    assert second.status == "FAILED" and invalid.analyze_calls == 1 and invalid.repair_calls == 1


def test_restart_requeues_interrupted_work(client, db):
    job, *_ = setup_job(client, db)
    job.status = "RUNNING"
    db.commit()
    restarted = worker(db, FixtureAnalysisAdapter(fixture("normal")))
    assert restarted.recover_interrupted() == 1
    assert asyncio.run(restarted.run_next())
    db.refresh(job)
    assert job.status == "SUCCEEDED"


def test_failure_after_persist_reuses_result_on_retry(client, db):
    job, _, record, boss = setup_job(client, db)
    class StopAfterPersist(AnalysisWorker):
        async def complete(self, state):
            raise RuntimeError("simulated interruption after persisted analysis")
    interrupted = StopAfterPersist(FixtureAnalysisAdapter(fixture("normal")), lambda: nullcontext(db))
    asyncio.run(interrupted.run_next())
    assert job.status == "FAILED"
    retry_job(db, boss, job.id)
    # This adapter would fail if called, proving the saved analysis is reused.
    asyncio.run(worker(db, UnconfiguredAnalysisAdapter()).run_next())
    db.refresh(job)
    assert job.status == "SUCCEEDED" and job.analysis_attempts == 1
    assert db.scalar(select(func.count()).select_from(AnalysisRecord).where(AnalysisRecord.input_id == record["id"])) == 1


def test_job_and_analysis_permissions_raw_output_only_for_boss(client, db):
    job, meeting, *_ = setup_job(client, db)
    asyncio.run(worker(db, FixtureAnalysisAdapter(fixture("normal"))).run_next())
    assert "raw_output" in client.get(f"/api/meetings/{meeting['id']}/analysis").json()
    login(client, "zhangsan")
    assert client.get(f"/api/jobs/{job.id}").status_code == 200
    public = client.get(f"/api/meetings/{meeting['id']}/analysis").json()
    assert "raw_output" not in public and "resolved_candidates" not in public
    assert client.post(f"/api/jobs/{job.id}/retry").status_code == 403
    login(client, "wangwu")
    assert client.get(f"/api/jobs/{job.id}").status_code == 404
    assert client.get(f"/api/meetings/{meeting['id']}/analysis").status_code == 404


def test_same_meeting_rejects_second_active_job_and_new_version_hides_old_analysis(client, db):
    job, meeting, _, boss = setup_job(client, db)
    second = client.post(f"/api/meetings/{meeting['id']}/inputs", json={"request_id": str(uuid4()), "text": "新输入"})
    assert second.status_code == 409
    asyncio.run(worker(db, FixtureAnalysisAdapter(fixture("normal"))).run_next())
    second = client.post(f"/api/meetings/{meeting['id']}/inputs", json={"request_id": str(uuid4()), "text": "新输入"})
    assert second.status_code == 202
    assert client.get(f"/api/meetings/{meeting['id']}/analysis").status_code == 404
