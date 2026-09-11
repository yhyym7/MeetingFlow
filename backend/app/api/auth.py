from fastapi import APIRouter, Request, Response

from app.api.dependencies import CurrentUser, Database
from app.config import get_settings
from app.schemas.auth import LoginRequest
from app.schemas.people import AdminUserOut
from app.services import auth


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AdminUserOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Database):
    user, token = auth.login(db, payload.username, payload.password, request.cookies.get(auth.COOKIE_NAME))
    settings = get_settings()
    response.set_cookie(
        auth.COOKIE_NAME, token, max_age=settings.session_hours * 3600,
        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/",
    )
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Database):
    auth.logout(db, request.cookies.get(auth.COOKIE_NAME))
    response.delete_cookie(auth.COOKIE_NAME, httponly=True, secure=get_settings().cookie_secure, samesite="lax")


@router.get("/me", response_model=AdminUserOut)
def me(user: CurrentUser):
    return user
