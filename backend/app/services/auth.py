import hashlib
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthSession, User
from app.models.base import utc_now
from app.permissions import require_known_user
from app.security import hash_password, verify_password


COOKIE_NAME = "meetingflow_session"
_DUMMY_HASH = hash_password("not-a-real-user-password")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def resolve_user(db: Session, token: str | None) -> User:
    if not token or len(token) > 128:
        raise HTTPException(401, "请先登录")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
    if session is None or session.expires_at <= utc_now():
        raise HTTPException(401, "登录已失效，请重新登录")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "登录已失效，请重新登录")
    require_known_user(user)
    return user


def login(db: Session, username: str, password: str, old_token: str | None) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not valid or user is None or not user.is_active:
        raise HTTPException(401, "账号或密码错误")
    require_known_user(user)
    if old_token and len(old_token) <= 128:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(old_token)))
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(
        token_hash=token_digest(token), user_id=user.id,
        expires_at=utc_now() + timedelta(hours=get_settings().session_hours),
    ))
    db.commit()
    return user, token


def logout(db: Session, token: str | None) -> None:
    if token and len(token) <= 128:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        db.commit()
