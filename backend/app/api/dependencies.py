from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import COOKIE_NAME, resolve_user


Database = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: Database) -> User:
    return resolve_user(db, request.cookies.get(COOKIE_NAME))


CurrentUser = Annotated[User, Depends(current_user)]
