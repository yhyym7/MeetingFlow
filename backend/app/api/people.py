from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.dependencies import CurrentUser, Database
from app.models import Department, User
from app.permissions import require_boss
from app.schemas.people import AdminUserOut, DepartmentCreate, DepartmentOut, PublicUserOut, UserCreate, UserUpdate
from app.services import people


router = APIRouter(tags=["people"])
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Database, actor: CurrentUser, page: Page = 1, page_size: PageSize = 20):
    return list(db.scalars(select(Department).order_by(Department.id).offset((page - 1) * page_size).limit(page_size)))


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(payload: DepartmentCreate, db: Database, actor: CurrentUser):
    require_boss(actor)
    department = Department(name=payload.name)
    db.add(department)
    people.commit_or_conflict(db)
    return department


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
def rename_department(department_id: int, payload: DepartmentCreate, db: Database, actor: CurrentUser):
    require_boss(actor)
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(404, "部门不存在")
    department.name = payload.name
    people.commit_or_conflict(db)
    return department


@router.get("/users", response_model=list[AdminUserOut | PublicUserOut])
def list_users(db: Database, actor: CurrentUser, page: Page = 1, page_size: PageSize = 20):
    query = select(User).order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    schema = AdminUserOut if actor.role == "BOSS" else PublicUserOut
    return [schema.model_validate(user) for user in db.scalars(query)]


@router.post("/users", response_model=AdminUserOut, status_code=201)
def create_user(payload: UserCreate, db: Database, actor: CurrentUser):
    return people.create_user(db, actor, payload)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: int, payload: UserUpdate, db: Database, actor: CurrentUser):
    return people.update_user(db, actor, user_id, payload)
