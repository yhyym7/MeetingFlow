import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.adapters import AnalysisAdapter, AnalysisError, UnconfiguredAnalysisAdapter
from app.ai.analysis import analyze_text
from app.ai.contracts import AnalysisRequest, PersonReference
from app.ai.resolution import load_directory, resolve_candidates
from app.database import get_engine
from app.models import AnalysisRecord, Meeting, MeetingInput, ProcessingJob
from app.models.base import utc_now
from app.config import get_settings
from app.ai.demo import DemoAnalysisAdapter


class AnalysisState(TypedDict, total=False):
    job_id: int
    input_id: int
    request: AnalysisRequest
    people: list
    reusable: bool
    result: Any
    resolved: list
    scope: str


class AnalysisWorker:
    """One in-process worker; MySQL stores recovery data, not LangGraph checkpoints."""

    def __init__(self, adapter: AnalysisAdapter | None = None, session_factory: Callable | None = None,
                 *, retry_delay: float = 0.5, poll_interval: float = 1, error_delay: float = 1):
        from app.ai.deepseek import DeepSeekAnalysisAdapter
        self.adapter = adapter or ({"demo": DemoAnalysisAdapter, "deepseek": DeepSeekAnalysisAdapter}
                                   .get(get_settings().analysis_mode, UnconfiguredAnalysisAdapter)())
        self.sessions = session_factory or (lambda: Session(get_engine(), expire_on_commit=False))
        self.retry_delay = retry_delay
        self.poll_interval = poll_interval
        self.error_delay = error_delay
        self.stop = asyncio.Event()
        graph = StateGraph(AnalysisState)
        graph.add_node("load", self.load)
        graph.add_node("analyze", self.analyze)
        graph.add_node("validate", self.validate)
        graph.add_node("persist", self.persist)
        graph.add_node("publish", self.publish)
        graph.add_node("complete", self.complete)
        graph.add_edge(START, "load")
        graph.add_conditional_edges("load", lambda state: self.after_analysis(state) if state["reusable"] else "analyze",
                                    {"complete": "complete", "publish": "publish", "analyze": "analyze"})
        graph.add_edge("analyze", "validate")
        graph.add_edge("validate", "persist")
        graph.add_conditional_edges("persist", self.after_analysis, {"complete": "complete", "publish": "publish"})
        graph.add_edge("publish", "complete")
        graph.add_edge("complete", END)
        self.graph = graph.compile()

    @staticmethod
    def after_analysis(state):
        return "publish" if state["scope"] == "FULL_PIPELINE" else "complete"

    def trace(self, job_id: int, name: str):
        with self.sessions() as db:
            job = db.get(ProcessingJob, job_id)
            job.node_trace = [*job.node_trace, name]
            job.stage = name
            db.commit()

    async def load(self, state: AnalysisState):
        self.trace(state["job_id"], "LOAD")
        with self.sessions() as db:
            job = db.get(ProcessingJob, state["job_id"])
            record = db.get(MeetingInput, job.input_id)
            meeting = db.get(Meeting, record.meeting_id)
            existing = db.scalar(select(AnalysisRecord.id).where(AnalysisRecord.input_id == record.id))
            if existing:
                return {"input_id": record.id, "reusable": True, "scope": job.scope}
            people = load_directory(db, meeting.id)
            request = AnalysisRequest(text=record.text, meeting_at=meeting.starts_at,
                                      participants=[PersonReference(name=p.name, department=p.department) for p in people if p.participant])
            return {"input_id": record.id, "reusable": False, "request": request, "people": people, "scope": job.scope}

    async def analyze(self, state: AnalysisState):
        self.trace(state["job_id"], "ANALYZE")
        max_attempts = 1 if self.adapter.mode == "deepseek" else 3
        for attempt in range(max_attempts):
            with self.sessions() as db:
                job = db.get(ProcessingJob, state["job_id"])
                job.analysis_attempts += 1
                db.commit()
            try:
                return {"result": await analyze_text(self.adapter, state["request"])}
            except AnalysisError as exc:
                if not exc.retryable or attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (2 ** attempt))

    async def validate(self, state: AnalysisState):
        self.trace(state["job_id"], "VALIDATE")
        return {"resolved": resolve_candidates(state["result"], state["request"].text,
                                                state["request"].meeting_at, state["people"])}

    async def persist(self, state: AnalysisState):
        self.trace(state["job_id"], "PERSIST")
        result = state["result"]
        with self.sessions() as db:
            db.add(AnalysisRecord(input_id=state["input_id"], mode=result.mode, summary=result.summary,
                                  decisions=result.decisions, risks=result.risks, raw_output=result.raw_output,
                                  resolved_candidates=[row.model_dump(mode="json") for row in state["resolved"]]))
            db.commit()
        return {}

    async def publish(self, state: AnalysisState):
        from app.services.candidates import auto_publish_analysis
        self.trace(state["job_id"], "PUBLISH")
        with self.sessions() as db:
            analysis_id = db.scalar(select(AnalysisRecord.id).where(AnalysisRecord.input_id == state["input_id"]))
            auto_publish_analysis(db, analysis_id)
        return {}

    async def complete(self, state: AnalysisState):
        self.trace(state["job_id"], "COMPLETE" if state["scope"] == "FULL_PIPELINE" else "COMPLETE_ANALYSIS")
        with self.sessions() as db:
            job = db.get(ProcessingJob, state["job_id"])
            job.status, job.finished_at, job.error_code = "SUCCEEDED", utc_now(), None
            db.commit()
        return {}

    def recover_interrupted(self) -> int:
        with self.sessions() as db:
            result = db.execute(update(ProcessingJob).where(ProcessingJob.status == "RUNNING")
                                .values(status="QUEUED", finished_at=None, error_code=None))
            db.commit()
            return result.rowcount

    async def run_next(self) -> bool:
        with self.sessions() as db:
            job = db.scalar(select(ProcessingJob).where(ProcessingJob.status == "QUEUED")
                            .order_by(ProcessingJob.id).limit(1).with_for_update(skip_locked=True))
            if job is None:
                return False
            job.status, job.started_at, job.finished_at = "RUNNING", utc_now(), None
            job.attempts += 1
            job_id = job.id
            db.commit()
        try:
            # Tracing must not export private meeting state to an external service.
            with tracing_context(enabled=False):
                await self.graph.ainvoke({"job_id": job_id}, config={"recursion_limit": 12})
        except SQLAlchemyError:
            # Keep RUNNING durable: the single worker recovers it after reconnection.
            raise
        except Exception as exc:
            allowed_codes = {"ANALYSIS_NOT_CONFIGURED", "DEMO_SAMPLE_REQUIRED", "ANALYSIS_TIMEOUT", "ANALYSIS_PROVIDER_ERROR",
                             "ANALYSIS_INVALID_STRUCTURE", "ANALYSIS_OUTPUT_TOO_LARGE_OR_INVALID",
                             "ANALYSIS_AUTH_ERROR", "ANALYSIS_QUOTA_ERROR", "ANALYSIS_INPUT_TOO_LONG"}
            code = exc.code if isinstance(exc, AnalysisError) and exc.code in allowed_codes else "ANALYSIS_WORKER_ERROR"
            with self.sessions() as db:
                db.rollback()
                job = db.get(ProcessingJob, job_id)
                job.status, job.finished_at, job.error_code = "FAILED", utc_now(), code
                db.commit()
        return True

    async def run_forever(self):
        needs_recovery = True
        failures = 0
        while not self.stop.is_set():
            try:
                if needs_recovery:
                    self.recover_interrupted()
                    needs_recovery = False
                worked = await self.run_next()
                failures = 0
                if not worked:
                    await self.wait_or_stop(self.poll_interval)
            except SQLAlchemyError as exc:
                # Never log SQL, connection strings or provider payloads.
                logging.getLogger(__name__).warning("Analysis database unavailable: %s", type(exc).__name__)
                needs_recovery = True
                failures = min(failures + 1, 6)
                await self.wait_or_stop(min(30, self.error_delay * 2 ** (failures - 1)))

    async def wait_or_stop(self, seconds: float):
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)
        except TimeoutError:
            pass
