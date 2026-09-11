import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db, get_engine
from app.models import User
from app.security import hash_password
from scripts.seed_demo import seed_demo


@pytest.fixture(autouse=True)
def offline_defaults(monkeypatch):
    # The complete regression suite must never spend the user's API balance.
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'analysis_mode', 'demo')
    monkeypatch.setattr(settings, 'asr_mode', 'unconfigured')
    monkeypatch.setattr(settings, 'embedding_mode', 'keyword')


@pytest.fixture
def db():
    """Real MySQL tests; each test is enclosed by a transaction that is rolled back."""
    engine = get_engine()
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            try:
                yield session
            finally:
                session.close()
                transaction.rollback()


@pytest.fixture
def client(db):
    from app.main import create_app

    seed_demo(db, "test-password-T03")
    test_hash = hash_password("test-password-T03")
    for user in db.scalars(select(User).where(User.username.in_(["boss", "zhangsan", "lisi", "wangwu", "zhaoliu"]))):
        user.password_hash = test_hash
    db.flush()
    app = create_app(start_worker=False)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={"Origin": "http://127.0.0.1:5173"}) as test_client:
        yield test_client


@pytest.fixture
def existing_pending(client, db):
    """Keep user/demo candidates; tests assert their own changes against the baseline."""
    from app.services.candidates import pending_count
    return pending_count(db)
