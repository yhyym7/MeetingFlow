import asyncio
from contextlib import nullcontext

import pytest
from sqlalchemy.exc import OperationalError

from app.ai.adapters import FixtureAnalysisAdapter
from app.ai.workflow import AnalysisWorker
from app.main import create_app
from test_analysis import fixture
from test_workflow import setup_job


async def until(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.01)


def test_application_shutdown_cancels_analysis_and_restart_recovers(client, db, monkeypatch):
    job, *_ = setup_job(client, db)

    async def scenario():
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        class BlockingAdapter(FixtureAnalysisAdapter):
            async def analyze(self, request):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        first = AnalysisWorker(BlockingAdapter(""), lambda: nullcontext(db), poll_interval=0.01)
        monkeypatch.setattr("app.ai.workflow.AnalysisWorker", lambda: first)
        app = create_app(start_worker=True)
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(entered.wait(), 5)
            assert job.status == "RUNNING"
        assert cancelled.is_set() and first.stop.is_set()
        assert job.status == "RUNNING"

        adapter = FixtureAnalysisAdapter(fixture("normal"))
        second = AnalysisWorker(adapter, lambda: nullcontext(db), poll_interval=0.01)
        monkeypatch.setattr("app.ai.workflow.AnalysisWorker", lambda: second)
        app = create_app(start_worker=True)
        async with app.router.lifespan_context(app):
            await until(lambda: job.status == "SUCCEEDED")
        assert second.stop.is_set() and adapter.analyze_calls == 1
        assert job.attempts == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_at", ["recover", "claim", "complete"])
def test_database_outage_recovers_without_killing_worker(client, db, caplog, failure_at):
    job, *_ = setup_job(client, db)

    class ReconnectingWorker(AnalysisWorker):
        failed = False

        def fail_once(self, point):
            if point == failure_at and not self.failed:
                self.failed = True
                raise OperationalError("private-sql", {}, RuntimeError("private-db-password"))

        def recover_interrupted(self):
            self.fail_once("recover")
            return super().recover_interrupted()

        async def run_next(self):
            self.fail_once("claim")
            return await super().run_next()

        async def complete(self, state):
            self.fail_once("complete")
            return await super().complete(state)

    async def scenario():
        adapter = FixtureAnalysisAdapter(fixture("normal"))
        worker = ReconnectingWorker(adapter, lambda: nullcontext(db), poll_interval=0.01, error_delay=0.01)
        task = asyncio.create_task(worker.run_forever())
        try:
            await until(lambda: job.status == "SUCCEEDED")
            assert not task.done()
            assert adapter.analyze_calls == 1
        finally:
            worker.stop.set()
            await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    assert "OperationalError" in caplog.text
    assert "private-sql" not in caplog.text and "private-db-password" not in caplog.text


def test_worker_wait_can_be_stopped_during_database_outage():
    class OfflineWorker(AnalysisWorker):
        def recover_interrupted(self):
            raise OperationalError("", {}, RuntimeError("offline"))

    async def scenario():
        worker = OfflineWorker(error_delay=30)
        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0)
        worker.stop.set()
        await asyncio.wait_for(task, 1)

    asyncio.run(scenario())


def test_disabled_application_does_not_create_worker(monkeypatch):
    def unexpected():
        raise AssertionError("Worker must remain disabled")
    monkeypatch.setattr("app.ai.workflow.AnalysisWorker", unexpected)

    async def scenario():
        app = create_app(start_worker=False)
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)

    asyncio.run(scenario())
