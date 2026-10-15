"""Idempotent local fallback quiz seed; never resurrect a flagged/retired variant."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.study import cache_key, normalise, normalise_subject
from app.db.database import Database
from app.models import Quiz
from app.models.enums import EducationLevel, QuizSource, QuizVariantStatus
from app.quizzes.schema import QuizDocument
from app.quizzes.worker import Job, store_quiz


async def seed_quizzes_in_session(db, *, preserve_cache=False):
    count = 0
    entries = json.loads(Path(__file__).with_name("demo_quizzes.json").read_text())
    for entry in entries:
        subject, topic = normalise_subject(entry["subject"]), normalise(entry["topic"])
        level = EducationLevel(entry["level"])
        key = cache_key(subject, topic, level)
        if await db.scalar(
            select(Quiz.id).where(Quiz.cache_key == key, Quiz.model_name == "curated-demo/v1")
        ):
            continue
        if (
            preserve_cache
            and await db.scalar(
                select(func.count())
                .select_from(Quiz)
                .where(Quiz.cache_key == key, Quiz.status == QuizVariantStatus.ACTIVE)
            )
            >= 5
        ):
            continue
        document = QuizDocument.model_validate({"questions": entry["questions"]})
        job = Job(key, entry["subject"], entry["topic"], subject, topic, level)
        await store_quiz(db, job, document, "curated-demo/v1", QuizSource.FALLBACK)
        count += 1
    return count


async def seed_quizzes(database):
    async with database.session_factory() as db:
        await db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
        count = await seed_quizzes_in_session(db)
        await db.commit()
    return count


async def main():
    database = Database(get_settings().database_url)
    try:
        print(f"Seeded {await seed_quizzes(database)} fallback quizzes.")
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
