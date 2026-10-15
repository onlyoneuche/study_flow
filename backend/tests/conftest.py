from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace

import jwt
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.db.database import configure_sqlite
from app.db.types import utc_now
from app.main import create_app
from app.models.enums import EducationLevel
from tests.factories import user

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


@pytest.fixture
def ollama_transport():
    return None


@pytest.fixture
def auth_client(db_path, ollama_transport):
    settings = Settings(
        _env_file=None,
        environment="test",
        auth_secret="test-secret-with-at-least-32-characters",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        frontend_url="http://127.0.0.1:3000",
    )
    with TestClient(create_app(settings, ollama_transport=ollama_transport)) as client:
        yield client


@pytest.fixture
def actor(auth_client, db_engine):
    def make(level=EducationLevel.SS2, name="Ada"):
        with Session(db_engine) as db:
            learner = user(db, level=level, display_name=name)
            db.commit()
            uid = learner.id
        token = jwt.encode(
            {"sub": str(uid), "aud": "fastapi-users:auth", "exp": utc_now() + timedelta(hours=1)},
            auth_client.app.state.settings.auth_secret.get_secret_value(),
            algorithm="HS256",
        )
        return SimpleNamespace(id=uid, headers={"Authorization": f"Bearer {token}"})

    return make


@pytest.fixture
def clock(auth_client):
    clock = SimpleNamespace(now=datetime(2026, 10, 15, 22, 50, tzinfo=UTC))
    auth_client.app.state.clock = lambda: clock.now
    return clock
