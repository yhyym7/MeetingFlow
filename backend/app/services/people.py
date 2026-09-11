from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuthSession, Department, User
from app.permissions import require_boss
from app.schemas.people import UserCreate, UserUpdate
from app.security import hash_password


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "名称或登录名已存在，或关联数据发生变化") from None


def check_department(db: Session, department_id: int | None) -> None:
    if department_id is not None and db.get(Department, department_id) is None:
        raise HTTPException(422, "部门不存在")


def create_user(db: Session, actor: User, payload: UserCreate) -> User:
    require_boss(actor)
    check_department(db, payload.department_id)
    if payload.role == "MANAGER" and payload.department_id is None:
        raise HTTPException(422, "部门负责人必须指定所属部门")
    user = User(**payload.model_dump(exclude={"password"}), password_hash=hash_password(payload.password))
    db.add(user)
    commit_or_conflict(db)
    return user


def update_user(db: Session, actor: User, user_id: int, payload: UserUpdate) -> User:
    require_boss(actor)
    # Serialize changes to active Boss accounts so simultaneous demotions cannot
    # both observe the other account as the remaining administrator.
    bosses = list(db.scalars(select(User).where(User.role == "BOSS", User.is_active.is_(True))
                            .order_by(User.id).with_for_update().execution_options(populate_existing=True)))
    db.refresh(actor, with_for_update=True)
    require_boss(actor)
    user = db.scalar(select(User).where(User.id == user_id).with_for_update()
                     .execution_options(populate_existing=True))
    if user is None:
        raise HTTPException(404, "人员不存在")
    changes = payload.model_dump(exclude_unset=True)
    if user.role == "BOSS" and user.is_active:
        keeps_boss = changes.get("role", user.role) == "BOSS" and changes.get("is_active", user.is_active)
        if not keeps_boss and len(bosses) <= 1:
            raise HTTPException(409, "不能停用或降级最后一个启用的管理者")
    if "department_id" in changes:
        check_department(db, changes["department_id"])
    if changes.get("role", user.role) == "MANAGER" and changes.get("department_id", user.department_id) is None:
        raise HTTPException(422, "部门负责人必须指定所属部门")
    for key, value in changes.items():
        setattr(user, key, value)
    if changes.get("is_active") is False or "role" in changes or "department_id" in changes:
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    commit_or_conflict(db)
    return user
