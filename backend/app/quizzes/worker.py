import asyncio
import logging
import secrets
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

import anyio
import httpx
from pydantic import ValidationError
from sqlalchemy import exists, select

from app.core.study import PROMPT_VERSION, cache_key
from app.models import Quiz, QuizAttempt, QuizQuestion, SessionParticipant, StudySession
from app.models.enums import ParticipantStatus, QuizSource, QuizStatus, QuizVariantStatus
from app.quizzes.schema import SYSTEM_PROMPT, USER_PROMPT, QuizDocument, level_descriptor
from app.services.completion import complete

logger = logging.getLogger(__name__)


@dataclass
class Job:
    key: str
    subject: str
    topic: str
    subject_norm: str
    topic_norm: str
    level: object


def job_for(participant):
    return Job(
        cache_key(participant.subject_norm, participant.topic_norm, participant.level),
        participant.subject,
        participant.topic,
        participant.subject_norm,
        participant.topic_norm,
        participant.level,
    )


async def questions_for(db, quiz_id):
    return list(
        (
            await db.scalars(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz_id)
                .order_by(QuizQuestion.position)
            )
        ).all()
    )


async def usable(db, quiz_id):
    quiz = await db.get(Quiz, quiz_id)
    if not quiz or quiz.status != QuizVariantStatus.ACTIVE:
        return False
    questions = await questions_for(db, quiz_id)
    return len(questions) == 15 and not any(q.is_disabled or q.flag_count for q in questions)


async def cached(db, job, user_id, related=False):
    attempted = select(QuizAttempt.quiz_id).where(QuizAttempt.user_id == user_id)
    bad = exists(
        select(QuizQuestion.id).where(
            QuizQuestion.quiz_id == Quiz.id,
            (QuizQuestion.is_disabled.is_(True)) | (QuizQuestion.flag_count > 0),
        )
    )
    query = select(Quiz).where(
        Quiz.status == QuizVariantStatus.ACTIVE,
        ~bad,
        Quiz.id.not_in(attempted),
        Quiz.level == job.level,
        Quiz.subject_norm == job.subject_norm,
    )
    if not related:
        query = query.where(Quiz.cache_key == job.key)
    for quiz in (await db.scalars(query.order_by(Quiz.id.desc()))).all():
        if await usable(db, quiz.id):
            return quiz
    return None


async def store_quiz(db, job, document, model_name, source=QuizSource.LLM, *, historical=False):
    quiz = Quiz(
        cache_key=job.key,
        subject_norm=job.subject_norm,
        topic_norm=job.topic_norm,
        level=job.level,
        prompt_version=PROMPT_VERSION,
        model_name=model_name,
        source=source,
        status=QuizVariantStatus.RETIRED if historical else QuizVariantStatus.ACTIVE,
    )
    db.add(quiz)
    await db.flush()
    for position, item in enumerate(document.questions):
        order = list(range(4))
        secrets.SystemRandom().shuffle(order)
        db.add(
            QuizQuestion(
                quiz_id=quiz.id,
                position=position,
                question=item.question,
                options=[item.options[index] for index in order],
                correct_index=order.index(item.correct_index),
                explanation=item.explanation,
                difficulty=item.difficulty,
            )
        )
    active = (
        await db.scalars(
            select(Quiz)
            .where(Quiz.cache_key == job.key, Quiz.status == QuizVariantStatus.ACTIVE)
            .order_by(Quiz.id.desc())
        )
    ).all()
    for old in active[5:] if not historical else []:
        # Logical eviction preserves the questions referenced by historical attempts and flags.
        old.status = QuizVariantStatus.RETIRED
    await db.flush()
    return quiz


class QuizWorker:
    def __init__(self, app):
        self.app = app
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.waiters: dict[str, set[int]] = {}
        self.task = None

    @asynccontextmanager
    async def database(self, write=False):
        with anyio.CancelScope(shield=True):
            async with self.app.state.database.session_factory() as db:
                if write:
                    await db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
                yield db

    async def start(self):
        if not self.task:
            self.task = asyncio.create_task(self.run(), name="studyflow-quiz-worker")

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None

    async def enqueue(self, participant_id):
        async with self.database() as db:
            participant = await db.get(SessionParticipant, participant_id)
            if not participant or participant.quiz_status != QuizStatus.PENDING:
                return
            session = await db.get(StudySession, participant.session_id)
            if (
                self.app.state.clock() < session.started_at
                or participant.completed_at
                or participant.status == ParticipantStatus.INCOMPLETE
            ):
                return
            job = job_for(participant)
        if job.key in self.waiters:
            self.waiters[job.key].add(participant_id)
        else:
            self.waiters[job.key] = {participant_id}
            self.queue.put_nowait(job)

    async def enqueue_due(self):
        async with self.database() as db:
            ids = list(
                (
                    await db.scalars(
                        select(SessionParticipant.id)
                        .join(StudySession)
                        .where(
                            SessionParticipant.quiz_status == QuizStatus.PENDING,
                            SessionParticipant.completed_at.is_(None),
                            SessionParticipant.status != ParticipantStatus.INCOMPLETE,
                            StudySession.started_at <= self.app.state.clock(),
                        )
                    )
                ).all()
            )
        for participant_id in ids:
            await self.enqueue(participant_id)

    async def generate(self, job):
        feedback = ""
        for _ in range(2):
            try:
                response = await asyncio.wait_for(
                    self.app.state.ollama_client.post(
                        "api/chat",
                        json={
                            "model": self.app.state.settings.ollama_model,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {
                                    "role": "user",
                                    "content": USER_PROMPT.format(
                                        subject=job.subject,
                                        topic=job.topic,
                                        level_descriptor=level_descriptor(job.level),
                                        retry_feedback=feedback,
                                    ),
                                },
                            ],
                            "format": QuizDocument.model_json_schema(),
                            "stream": False,
                            "options": {"temperature": 0.4},
                        },
                        timeout=httpx.Timeout(120.0),
                    ),
                    timeout=120.0,
                )
                response.raise_for_status()
                content = response.json()["message"]["content"]
                return QuizDocument.model_validate_json(content)
            except (
                httpx.HTTPError,
                ValidationError,
                ValueError,
                KeyError,
                TypeError,
                TimeoutError,
            ) as error:
                # Prompts, answers and student topics stay out of logs.
                errors = (
                    error.errors(include_input=False, include_url=False)
                    if isinstance(error, ValidationError)
                    else type(error).__name__
                )
                feedback = (
                    f"Your previous answer was invalid: {str(errors)[:3000]}. "
                    "Fix these problems and return all 15 questions."
                )
        return None

    async def assign_cached(self, key, job, related=False, unavailable=False):
        async with self.database(write=True) as db:
            for participant_id in list(self.waiters.get(key, set())):
                participant = await db.get(SessionParticipant, participant_id)
                if not participant or participant.quiz_status != QuizStatus.PENDING:
                    self.waiters[key].discard(participant_id)
                    continue
                if participant.completed_at or participant.status == ParticipantStatus.INCOMPLETE:
                    self.waiters[key].discard(participant_id)
                    continue
                quiz = await cached(db, job, participant.user_id, related=related)
                if quiz:
                    participant.quiz_id = quiz.id
                    participant.quiz_status = QuizStatus.READY
                    self.waiters[key].discard(participant_id)
                elif unavailable:
                    participant.quiz_id = None
                    participant.quiz_status = QuizStatus.UNAVAILABLE
                    if participant.ended_at:
                        await complete(
                            db,
                            await db.get(StudySession, participant.session_id),
                            participant,
                            self.app.state.clock(),
                        )
                    self.waiters[key].discard(participant_id)
            await db.commit()

    async def process(self, job):
        await self.assign_cached(job.key, job)
        if self.waiters[job.key]:
            document = await self.generate(job)
            if document:
                async with self.database(write=True) as db:
                    await store_quiz(db, job, document, self.app.state.settings.ollama_model)
                    await db.commit()
            # A same-topic variant may have appeared while generation was in progress.
            await self.assign_cached(job.key, job)
            await self.assign_cached(job.key, job, related=True, unavailable=True)

    async def run(self):
        while True:
            job = await self.queue.get()
            try:
                await self.process(job)
            except Exception:
                logger.exception("Quiz preparation failed; pending work will be recovered")
                # Persisted pending participations are re-enqueued by the runtime after this job.
            finally:
                self.waiters.pop(job.key, None)
                self.queue.task_done()
