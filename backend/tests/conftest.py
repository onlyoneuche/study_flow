from pathlib import Path
from shutil import copyfile

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.db.database import configure_sqlite

BACKEND = Path(__file__).resolve().parents[1]


def migration_config(path: Path) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["database_url"] = f"sqlite+aiosqlite:///{path}"
    return config


@pytest.fixture(scope="session")
def schema_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("migrated") / "template.db"
    command.upgrade(migration_config(path), "head")
    return path


@pytest.fixture
def db_path(schema_file, tmp_path):
    path = tmp_path / "studyflow.db"
    # Alembic disposed its final connection, checkpointing the WAL before copying.
    copyfile(schema_file, path)
    return path


@pytest.fixture
def db_engine(db_path):
    engine = create_engine(f"sqlite:///{db_path}")
    configure_sqlite(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    with Session(db_engine, expire_on_commit=False) as session:
        yield session
