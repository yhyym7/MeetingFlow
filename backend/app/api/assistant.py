from fastapi import APIRouter

from app.ai.assistant import answer_query
from app.api.dependencies import CurrentUser, Database
from app.schemas.assistant import AssistantAnswer, AssistantQuery

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/query", response_model=AssistantAnswer)
async def query(payload: AssistantQuery, db: Database, actor: CurrentUser):
    return await answer_query(db, actor, payload.question)
