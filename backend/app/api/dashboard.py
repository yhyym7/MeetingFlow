from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.dashboard import DashboardOut
from app.services.dashboard import get_dashboard


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Database, actor: CurrentUser):
    return get_dashboard(db, actor)
