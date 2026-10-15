from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import StatementError

from alembic import command
from app.db.base import Base
from app.db.database import Database, database_url
from app.models import User
from tests.conftest import migration_config
from tests.factories import graph, user


def test_migration_matches_models_and_is_repeatable(db_path):
    config = migration_config(db_path)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)


def test_failed_initial_migration_rolls_back_schema(tmp_path, monkeypatch):
    path = tmp_path / "interrupted.db"
    original = Operations.create_table

    def interrupted(operation, name, *args, **kwargs):
        if name == "groups":
            raise RuntimeError("Simulated migration interruption")
        return original(operation, name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Operations, "create_table", interrupted)
        with pytest.raises(RuntimeError, match="migration interruption"):
            command.upgrade(migration_config(path), "head")
    engine = create_engine(f"sqlite:///{path}")
    try:
        assert inspect(engine).get_table_names() == []
        command.upgrade(migration_config(path), "head")
        assert len(inspect(engine).get_table_names()) == 17
    finally:
        engine.dispose()


def test_migration_down_and_up_with_populated_schema(db, db_engine, db_path):
    graph(db)
    db.commit()
    db.close()
    db_engine.dispose()
    config = migration_config(db_path)
    command.downgrade(config, "base")
    assert set(inspect(db_engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert set(inspect(db_engine).get_table_names()) == {*Base.metadata.tables, "alembic_version"}
    command.check(config)


def test_required_tables_and_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    assert len(Base.metadata.tables) == 16
    assert set(inspector.get_table_names()) == {*Base.metadata.tables, "alembic_version"}
    assert "level" not in {column["name"] for column in inspector.get_columns("sessions")}
    assert {"level", "quiz_id", "ended_at"} <= {
        column["name"] for column in inspector.get_columns("session_participants")
    }
    indexes = {index["name"] for index in inspector.get_indexes("points_ledger")}
    assert {
        "ix_points_ledger_group_week",
        "ix_points_ledger_user_day",
        "uq_points_ledger_award",
    } <= indexes


async def test_async_engine_sets_pragmas_on_every_connection(db_path):
    database = Database(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with database.engine.connect() as first, database.engine.connect() as second:
            for connection in (first, second):
                assert await connection.scalar(text("PRAGMA journal_mode")) == "wal"
                assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
                assert await connection.scalar(text("PRAGMA recursive_triggers")) == 1
                assert await connection.scalar(text("PRAGMA busy_timeout")) == 10000
        async with database.session_factory() as session:
            assert list(await session.scalars(select(User))) == []
    finally:
        await database.close()


def test_timestamps_round_trip_as_aware_utc(db):
    local = datetime(2026, 10, 15, 23, 45, tzinfo=timezone(timedelta(hours=1)))
    row = user(db, guardian_consent_at=local)
    db.expire(row)
    assert row.guardian_consent_at == local.astimezone(UTC)
    assert row.guardian_consent_at.tzinfo is UTC
    assert row.created_at.tzinfo is UTC


def test_naive_timestamps_are_rejected(db):
    with pytest.raises(StatementError, match="must include a timezone"):
        user(db, guardian_consent_at=datetime(2026, 10, 15))


def test_relative_database_paths_are_anchored_to_backend(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    resolved = database_url("sqlite+aiosqlite:///./data/studyflow.db")
    assert resolved.endswith("/backend/data/studyflow.db")
    with pytest.raises(ValueError, match="requires a sqlite"):
        database_url("postgresql://localhost/studyflow")
