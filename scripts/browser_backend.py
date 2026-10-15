"""Start browser checks against a disposable, migrated and seeded local database."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.quizzes.seed import seed_quizzes  # noqa: E402

url = os.environ.get("DATABASE_URL", "")
if not url.startswith("sqlite+aiosqlite:////tmp/studyflow-"):
    raise SystemExit("Browser checks require a disposable /tmp/studyflow- database.")
config = Config(str(BACKEND / "alembic.ini"))
config.attributes["database_url"] = url
command.upgrade(config, "head")


async def seed():
    database = Database(get_settings().database_url)
    try:
        await seed_quizzes(database)
    finally:
        await database.close()


asyncio.run(seed())
os.execv(str(BACKEND / ".venv/bin/uvicorn"), ["uvicorn", "app.main:create_app", "--factory",
    "--app-dir", str(BACKEND), "--host", "127.0.0.1", "--port", "8000"])
