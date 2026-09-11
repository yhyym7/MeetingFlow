from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.candidates import CandidateOut, CandidatePublish, SupplementCollaborators
from app.schemas.common import Page, PageNumber, PageSize
from app.schemas.tasks import TaskOut
from app.services import candidates


router = APIRouter(tags=["candidates"])


@router.get("/meetings/{meeting_id}/candidates", response_model=Page[CandidateOut])
def list_candidates(meeting_id: int, db: Database, actor: CurrentUser, page: PageNumber = 1,
                    page_size: PageSize = 20, attention_only: bool = False):
    return candidates.list_candidates(db, actor, meeting_id, page, page_size, attention_only=attention_only)


@router.post("/candidates/{candidate_id}/publish", response_model=TaskOut)
def publish(candidate_id: int, payload: CandidatePublish, db: Database, actor: CurrentUser):
    return candidates.publish_candidate(db, actor, candidate_id, payload)


@router.post("/candidates/{candidate_id}/dismiss", response_model=CandidateOut)
def dismiss(candidate_id: int, db: Database, actor: CurrentUser):
    return candidates.dismiss_candidate(db, actor, candidate_id)


@router.patch("/candidates/{candidate_id}/collaborators", response_model=TaskOut)
def supplement(candidate_id: int, payload: SupplementCollaborators, db: Database, actor: CurrentUser):
    return candidates.supplement_collaborators(db, actor, candidate_id, payload.collaborator_ids)
