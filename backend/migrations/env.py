from logging.config import fileConfig

from alembic import context

from app.database import get_engine
from app.models import Base
from app.models.base import UTCDateTime


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def render_item(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from sqlalchemy.dialects import mysql")
        return "mysql.DATETIME(fsp=6)"
    return False


if context.is_offline_mode():
    context.configure(
        dialect_name="mysql", target_metadata=Base.metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata,
            compare_type=True, render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
