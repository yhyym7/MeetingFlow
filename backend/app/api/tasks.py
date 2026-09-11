from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.dependencies import CurrentUser, Database
from app.schemas.common import Page, PageNumber, PageSize
from app.schemas.tasks import Membership, ProgressCreate, StatusUpdate, TaskCreate, TaskEventOut, TaskOut, TaskStatus, TaskUpdate
from app.services import tasks


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=Page[TaskOut])
def list_tasks(db: Database, actor: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20,
               membership: Membership = "all", status: TaskStatus | None = None, overdue: bool | None = None,
               meeting_id: Annotated[int | None, Query(gt=0)] = None):
    return tasks.list_tasks(db, actor, page, page_size, membership=membership, status=status, overdue=overdue, meeting_id=meeting_id)


@router.post("", response_model=TaskOut, status_code=201)
def create_task(payload: TaskCreate, db: Database, actor: CurrentUser):
    return tasks.create_task(db, actor, payload)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Database, actor: CurrentUser):
    return tasks.get_task(db, actor, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Database, actor: CurrentUser):
    return tasks.update_task(db, actor, task_id, payload)


@router.patch("/{task_id}/status", response_model=TaskOut)
def change_status(task_id: int, payload: StatusUpdate, db: Database, actor: CurrentUser):
    return tasks.change_status(db, actor, task_id, payload.status)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: Database, actor: CurrentUser):
    tasks.delete_task(db, actor, task_id)
    return Response(status_code=204)


@router.get("/{task_id}/events", response_model=Page[TaskEventOut])
def list_events(task_id: int, db: Database, actor: CurrentUser, page: PageNumber = 1, page_size: PageSize = 20):
    return tasks.list_events(db, actor, task_id, page, page_size)


@router.post("/{task_id}/events", response_model=TaskEventOut, status_code=201)
def add_progress(task_id: int, payload: ProgressCreate, db: Database, actor: CurrentUser):
    return tasks.add_progress(db, actor, task_id, payload.body)
