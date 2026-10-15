from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


def database_url(raw_url: str) -> str:
    url = make_url(raw_url)
    if url.drivername != "sqlite+aiosqlite":
        raise ValueError("StudyFlow requires a sqlite+aiosqlite database URL")
    if url.database and url.database != ":memory:":
        path = Path(url.database)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(path.resolve()))
    return url.render_as_string(hide_password=False)


def configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def connect(connection, _record):
        # Explicit BEGIN below makes DDL and savepoints transactional on SQLite.
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA recursive_triggers=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")


class Database:
    def __init__(self, url: str):
        self.engine = create_async_engine(database_url(url), connect_args={"timeout": 10})
        configure_sqlite(self.engine.sync_engine)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session_factory() as session:
        yield session
