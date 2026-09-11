import logging
import asyncio
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.people import router as people_router
from app.api.meetings import router as meetings_router
from app.api.tasks import router as tasks_router
from app.api.dashboard import router as dashboard_router
from app.api.jobs import router as jobs_router
from app.api.candidates import router as candidates_router
from app.api.assistant import router as assistant_router
from app.api.audio import router as audio_router
from app.config import get_settings
from app.api.dependencies import CurrentUser
from app.ai.demo import DEMO_TEXT


class HealthResponse(BaseModel):
    status: str
    service: str


def create_app(*, start_worker: bool | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(application):
        enabled = settings.analysis_worker_enabled if start_worker is None else start_worker
        worker_task = None
        audio_task = None
        if enabled:
            from app.ai.workflow import AnalysisWorker
            worker = AnalysisWorker()
            worker_task = asyncio.create_task(worker.run_forever())
            if settings.asr_mode == 'local':
                from app.ai.audio_worker import AudioWorker
                audio_worker = AudioWorker()
                audio_task = asyncio.create_task(audio_worker.run_forever())
        try:
            yield
        finally:
            if audio_task:
                audio_worker.stop.set()
                audio_task.cancel()
                with suppress(asyncio.CancelledError):
                    await audio_task
            if worker_task:
                worker.stop.set()
                worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await worker_task

    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    @application.middleware("http")
    async def protect_requests(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if not origin:
                try:
                    referer = urlsplit(request.headers.get("referer", ""))
                    origin = f"{referer.scheme}://{referer.netloc}" if referer.scheme and referer.netloc else None
                except ValueError:
                    origin = None
            if origin not in settings.trusted_origins:
                return JSONResponse(status_code=403, content={"detail": "请求来源不受信任"})
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic's raw validation input may contain submitted passwords.
        errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).error("Database operation failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "数据服务暂时不可用，请稍后重试"})

    application.include_router(auth_router, prefix="/api")
    application.include_router(people_router, prefix="/api")
    application.include_router(meetings_router, prefix="/api")
    application.include_router(tasks_router, prefix="/api")
    application.include_router(dashboard_router, prefix="/api")
    application.include_router(jobs_router, prefix="/api")
    application.include_router(candidates_router, prefix="/api")
    application.include_router(assistant_router, prefix="/api")
    application.include_router(audio_router, prefix="/api")

    @application.get("/api/analysis-config", tags=["analysis"])
    def analysis_config(actor: CurrentUser):
        return {"mode": settings.analysis_mode,
                "audio_max_mb": settings.audio_max_mb, "transcription_available": settings.asr_mode == 'local',
                "embedding_mode": settings.embedding_mode,
                "demo_text": DEMO_TEXT if settings.analysis_mode == "demo" and actor.role in {"BOSS", "MANAGER"} else None}

    @application.get("/api/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; does not assert database or AI readiness."""
        return HealthResponse(status="ok", service=settings.app_name)

    return application


app = create_app()
