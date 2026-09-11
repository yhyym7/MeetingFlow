from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import AuthSession, User
from app.models.base import utc_now
from app.services.auth import COOKIE_NAME, token_digest


def login(client, username="boss"):
    response = client.post("/api/auth/login", json={"username": username, "password": "test-password-T03"})
    assert response.status_code == 200, response.text
    return response


def user_id(db, username):
    return db.scalar(select(User.id).where(User.username == username))


def test_login_cookie_and_hash_only_session(client, db):
    response = login(client)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    token = client.cookies.get(COOKIE_NAME)
    saved = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
    assert saved is not None and saved.token_hash != token
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["role"] == "BOSS"
    assert "password_hash" not in me.json()
    assert me.headers["cache-control"] == "no-store"


def test_logout_revokes_copied_cookie(client):
    login(client)
    token = client.cookies.get(COOKIE_NAME)
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client, db):
    login(client)
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(client.cookies.get(COOKIE_NAME))))
    session.expires_at = utc_now() - timedelta(seconds=1)
    db.flush()
    assert client.get("/api/auth/me").status_code == 401


def test_disabled_account_revokes_sessions_even_after_reenable(client, db):
    login(client, "zhangsan")
    employee_token = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    login(client)
    target_id = user_id(db, "zhangsan")
    assert client.patch(f"/api/users/{target_id}", json={"is_active": False}).status_code == 200
    assert db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == target_id)) == 0
    assert client.patch(f"/api/users/{target_id}", json={"is_active": True}).status_code == 200
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, employee_token)
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("username,password", [("boss", "wrong"), ("absent", "wrong")])
def test_wrong_login_has_generic_error(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "账号或密码错误"}


def test_employee_directory_has_only_public_fields(client, db):
    login(client, "zhangsan")
    response = client.get("/api/users?role=BOSS&current_user_id=1")
    assert response.status_code == 200
    assert all(set(row) == {"id", "name", "department_id"} for row in response.json())
    own_id = user_id(db, "zhangsan")
    assert client.patch(f"/api/users/{own_id}", json={"role": "BOSS"}).status_code == 403
    assert client.post("/api/departments", json={"name": "非法新增"}).status_code == 403
    assert client.post("/api/users", json={"username": "forbidden", "name": "测试", "password": "test123456"}).status_code == 403


@pytest.mark.parametrize("change", [{"is_active": False}, {"role": "EMPLOYEE"}])
def test_last_boss_cannot_be_disabled_or_demoted(client, db, change):
    login(client)
    response = client.patch(f"/api/users/{user_id(db, 'boss')}", json=change)
    assert response.status_code == 409
    assert client.get("/api/auth/me").status_code == 200


def test_boss_can_create_people_and_update_departments(client):
    login(client)
    department = client.post("/api/departments", json={"name": "测试新部门"})
    assert department.status_code == 201
    department_id = department.json()["id"]
    assert client.patch(f"/api/departments/{department_id}", json={"name": "测试更名部门"}).status_code == 200
    new_user = client.post("/api/users", json={
        "username": "new_employee", "name": "新员工", "department_id": department_id, "password": "test123456",
    })
    assert new_user.status_code == 201
    assert new_user.json()["role"] == "EMPLOYEE"
    assert "password" not in new_user.json() and "password_hash" not in new_user.json()
    assert client.patch(f"/api/users/{new_user.json()['id']}", json={"name": "更名员工", "department_id": None}).status_code == 200
    duplicate = client.post("/api/users", json={"username": "NEW_EMPLOYEE", "name": "重复", "password": "test123456"})
    assert duplicate.status_code == 409


def test_new_boss_allows_old_boss_demotion_and_revokes_old_session(client, db):
    login(client)
    assert client.post("/api/users", json={"username": "second_boss", "name": "第二管理者", "role": "BOSS", "password": "test123456"}).status_code == 201
    assert client.patch(f"/api/users/{user_id(db, 'boss')}", json={"role": "EMPLOYEE"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_missing_login_and_invalid_updates(client, db):
    assert client.get("/api/users").status_code == 401
    login(client)
    assert client.get("/api/users?page_size=101").status_code == 422
    assert client.get("/api/users?page=0").status_code == 422
    assert client.patch("/api/users/2147483647", json={"name": "不存在"}).status_code == 404
    for payload in ({"name": None}, {"role": None}, {"is_active": None}, {"department_id": 2147483647}):
        assert client.patch(f"/api/users/{user_id(db, 'zhangsan')}", json=payload).status_code == 422


def test_untrusted_and_missing_origin_are_rejected(client):
    payload = {"username": "boss", "password": "test-password-T03"}
    assert client.post("/api/auth/login", json=payload, headers={"Origin": "https://untrusted.example"}).status_code == 403
    client.headers.pop("origin")
    assert client.post("/api/auth/login", json=payload).status_code == 403
    assert client.post("/api/auth/login", json=payload, headers={"Referer": "http://127.0.0.1:5173/login"}).status_code == 200


def test_validation_does_not_echo_passwords_or_accept_claimed_identity(client):
    submitted = "secret-value-for-validation"
    response = client.post("/api/auth/login", json={"username": "boss", "password": submitted, "role": "BOSS"})
    assert response.status_code == 422
    assert submitted not in response.text
    short_password = "secret"
    login(client)
    response = client.post("/api/users", json={"username": "short_password", "name": "测试", "password": short_password})
    assert response.status_code == 422
    assert '"input"' not in response.text


def test_disabled_user_cannot_login_and_login_rotates_cookie(client, db):
    login(client, "zhangsan")
    first_token = client.cookies.get(COOKIE_NAME)
    login(client, "zhangsan")
    assert client.cookies.get(COOKIE_NAME) != first_token
    assert db.scalar(select(AuthSession.id).where(AuthSession.token_hash == token_digest(first_token))) is None
    employee = db.get(User, user_id(db, "zhangsan"))
    employee.is_active = False
    db.flush()
    assert client.get("/api/auth/me").status_code == 401
    response = client.post("/api/auth/login", json={"username": "zhangsan", "password": "test-password-T03"})
    assert response.status_code == 401


def test_invalid_referer_is_rejected(client):
    client.headers.pop("origin")
    response = client.post("/api/auth/login", headers={"Referer": "http://[invalid"}, json={"username": "boss", "password": "test-password-T03"})
    assert response.status_code == 403
