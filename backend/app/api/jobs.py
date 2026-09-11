from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.jobs import JobOut
from app.services import jobs


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Database, actor: CurrentUser):
    return jobs.get_job(db, actor, job_id)


@router.post("/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(job_id: int, db: Database, actor: CurrentUser):
    return jobs.retry_job(db, actor, job_id)
