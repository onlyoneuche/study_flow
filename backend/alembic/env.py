import asyncio
from logging.config import fileConfig

from alembic import context
from app import models  # noqa: F401 -- registers all tables with Base.metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.database import Database, database_url
from app.db.types import UTCDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = config.attributes.get("database_url") or get_settings().database_url
target_metadata = Base.metadata


def render_item(kind, item, _autogen_context):
    if kind == "type" and isinstance(item, UTCDateTime):
        return "sa.DateTime()"
    return False


def run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        transactional_ddl=True,
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    database = Database(url)
    try:
        async with database.engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await database.close()


if context.is_offline_mode():
    context.configure(
        url=database_url(url),
        target_metadata=target_metadata,
        literal_binds=True,
        transactional_ddl=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
