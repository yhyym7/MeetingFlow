from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    secret = get_settings().database_url
    if secret is None:
        raise RuntimeError("Configure MEETINGFLOW_DATABASE_URL in backend/.env first.")
    url = make_url(secret.get_secret_value())
    if url.drivername != "mysql+pymysql":
        raise RuntimeError("This project requires MySQL with the PyMySQL driver.")
    return create_engine(
        url, pool_pre_ping=True, pool_recycle=1800,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5, "read_timeout": 15, "write_timeout": 15,
            "init_command": "SET time_zone = '+00:00'",
        },
    )


def get_db() -> Generator[Session, None, None]:
    # Services own commits; closing a failed request rolls back uncommitted work.
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
