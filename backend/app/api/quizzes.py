from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select

from app.api.groups import DB, Learner
from app.models import (
    Group,
    PointsLedger,
    QuestionFlag,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    SessionParticipant,
    StudySession,
)
from app.models.enums import FlagReason, ParticipantStatus, QuizStatus, QuizVariantStatus
from app.quizzes.worker import questions_for, usable
from app.services.completion import complete, deadline
from app.services.groups import fail
from app.services.sessions import advance_session

router = APIRouter()


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[Annotated[StrictInt, Field(ge=0, le=3)]] = Field(min_length=15, max_length=15)


class Flag(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: FlagReason
    note: str | None = Field(default=None, max_length=200)


async def own_participant(db, participant_id, user_id, now):
    participant = await db.get(SessionParticipant, participant_id)
    if not participant:
        fail("not_found", "This study participation was not found.", 404)
    if participant.user_id != user_id:
        fail("private_quiz", "This quiz belongs to another learner.", 403)
    session = await db.get(StudySession, participant.session_id)
    await advance_session(db, session, now)
    return participant, session


async def awards(db, participant):
    rows = (
        await db.scalars(
            select(PointsLedger)
            .where(PointsLedger.participant_id == participant.id)
            .order_by(PointsLedger.group_id, PointsLedger.id)
        )
    ).all()
    names = {
        g.id: g.name
        for g in (
            await db.scalars(select(Group).where(Group.id.in_({row.group_id for row in rows})))
        ).all()
    }
    return [
        dict(
            group_id=row.group_id,
            group_name=names[row.group_id],
            component=row.component,
            points=row.points,
        )
        for row in rows
    ]


async def result(db, participant, attempt, now):
    questions = await questions_for(db, attempt.quiz_id)
    flagged = set(
        (
            await db.scalars(
                select(QuestionFlag.question_id).where(
                    QuestionFlag.user_id == participant.user_id,
                    QuestionFlag.question_id.in_([q.id for q in questions]),
                )
            )
        ).all()
    )
    return dict(
        status="submitted",
        participant_id=participant.id,
        session_id=participant.session_id,
        subject=participant.subject,
        topic=participant.topic,
        level=participant.level,
        correct_count=attempt.correct_count,
        score_pct=attempt.score_pct,
        baseline_pct=attempt.baseline_pct,
        submitted_at=attempt.submitted_at,
        server_now=now,
        points=await awards(db, participant),
        questions=[
            dict(
                id=q.id,
                position=q.position,
                question=q.question,
                options=q.options,
                difficulty=q.difficulty,
                selected_index=attempt.answers[q.position],
                correct_index=q.correct_index,
                explanation=q.explanation,
                flagged_by_me=q.id in flagged,
            )
            for q in questions
        ],
    )


async def open_quiz(participant_id, request, db, user, background_tasks):
    now = request.app.state.clock()
    participant, session = await own_participant(db, participant_id, user.id, now)
    attempt = await db.scalar(
        select(QuizAttempt).where(QuizAttempt.participant_id == participant.id)
    )
    if attempt and attempt.submitted_at:
        return await result(db, participant, attempt, now)
    if not participant.ended_at:
        await db.commit()
        fail("quiz_locked", "Your quiz unlocks at the end of your study time.")
    if participant.status == ParticipantStatus.INCOMPLETE:
        await db.commit()
        fail("incomplete", "Not enough active study time. This session has no quiz or points.")
    if now > deadline(participant, attempt):
        await complete(db, session, participant, now)
        await db.commit()
        fail(
            "quiz_deadline",
            "The quiz deadline has passed. Your active study time still counts "
            "for time-only completion and base points.",
            410,
        )
    if participant.quiz_status == QuizStatus.UNAVAILABLE:
        await complete(db, session, participant, now)
        await db.commit()
        return dict(
            status="time_only",
            participant_id=participant.id,
            session_id=session.id,
            subject=participant.subject,
            topic=participant.topic,
            message="We could not prepare a quiz. Your study time counts; base points are saved.",
            points=await awards(db, participant),
        )
    if not attempt and participant.quiz_id and not await usable(db, participant.quiz_id):
        participant.quiz_id = None
        participant.quiz_status = QuizStatus.PENDING
    if not attempt and participant.quiz_id:
        repeated = await db.scalar(
            select(QuizAttempt.id)
            .where(QuizAttempt.user_id == user.id, QuizAttempt.quiz_id == participant.quiz_id)
            .limit(1)
        )
        if repeated:
            participant.quiz_id = None
            participant.quiz_status = QuizStatus.PENDING
    if participant.quiz_status == QuizStatus.PENDING:
        await db.commit()
        background_tasks.add_task(request.app.state.quizzes.enqueue, participant.id)
        return JSONResponse(
            status_code=202,
            content={"status": "preparing", "message": "Your quiz is being prepared. Please wait."},
            background=background_tasks,
        )
    if not attempt:
        attempt = QuizAttempt(
            participant_id=participant.id,
            quiz_id=participant.quiz_id,
            user_id=user.id,
            started_at=now,
        )
        db.add(attempt)
        await db.flush()
    await db.commit()
    quiz = await db.get(Quiz, attempt.quiz_id)
    questions = await questions_for(db, quiz.id)
    return dict(
        status="ready",
        participant_id=participant.id,
        session_id=session.id,
        subject=participant.subject,
        topic=participant.topic,
        level=participant.level,
        related_topic=quiz.topic_norm != participant.topic_norm,
        quiz_topic=quiz.topic_norm,
        source=quiz.source,
        server_now=now,
        started_at=attempt.started_at,
        deadline=deadline(participant, attempt),
        questions=[
            dict(
                id=q.id,
                position=q.position,
                question=q.question,
                options=q.options,
                difficulty=q.difficulty,
            )
            for q in questions
        ],
    )


@router.get("/participants/{participant_id}/quiz")
async def get_quiz(
    participant_id: int, request: Request, db: DB, user: Learner, background_tasks: BackgroundTasks
):
    return await open_quiz(participant_id, request, db, user, background_tasks)


@router.post("/participants/{participant_id}/quiz/start")
async def start_quiz(
    participant_id: int, request: Request, db: DB, user: Learner, background_tasks: BackgroundTasks
):
    return await open_quiz(participant_id, request, db, user, background_tasks)


@router.post("/participants/{participant_id}/quiz/submit")
async def submit_quiz(
    participant_id: int, data: Submission, request: Request, db: DB, user: Learner
):
    now = request.app.state.clock()
    participant, session = await own_participant(db, participant_id, user.id, now)
    attempt = await db.scalar(
        select(QuizAttempt).where(QuizAttempt.participant_id == participant.id)
    )
    if not attempt:
        fail("not_started", "Open the quiz before submitting your answers.")
    if attempt.submitted_at:
        if attempt.answers != data.answers:
            fail(
                "already_submitted",
                "This quiz has already been submitted. Answers cannot be changed.",
            )
        return await result(db, participant, attempt, now)
    if not participant.ended_at or participant.status == ParticipantStatus.INCOMPLETE:
        fail("quiz_locked", "This participation is not eligible for a quiz.")
    if now > deadline(participant, attempt):
        await complete(db, session, participant, now)
        await db.commit()
        fail(
            "quiz_deadline",
            "Your quiz submission is late. The deadline has passed; "
            "your study time keeps time-only completion and base points.",
            410,
        )
    questions = await questions_for(db, attempt.quiz_id)
    attempt.answers = data.answers
    attempt.correct_count = sum(data.answers[q.position] == q.correct_index for q in questions)
    attempt.score_pct = 100 * attempt.correct_count / 15
    attempt.submitted_at = now
    await complete(db, session, participant, now, attempt)
    await db.commit()
    return await result(db, participant, attempt, now)


@router.post("/questions/{question_id}/flags", status_code=201)
async def flag_question(question_id: int, data: Flag, db: DB, user: Learner):
    question = await db.get(QuizQuestion, question_id)
    if not question:
        fail("not_found", "This question was not found.", 404)
    submitted = await db.scalar(
        select(QuizAttempt.id)
        .where(
            QuizAttempt.user_id == user.id,
            QuizAttempt.quiz_id == question.quiz_id,
            QuizAttempt.submitted_at.is_not(None),
        )
        .limit(1)
    )
    if not submitted:
        fail("submit_first", "Submit your own quiz before flagging one of its questions.", 403)
    previous = await db.scalar(
        select(QuestionFlag).where(
            QuestionFlag.question_id == question.id, QuestionFlag.user_id == user.id
        )
    )
    if previous:
        fail("already_flagged", "You have already flagged this question.")
    db.add(
        QuestionFlag(question_id=question.id, user_id=user.id, reason=data.reason, note=data.note)
    )
    question.flag_count += 1
    if question.flag_count >= 3 or data.reason == FlagReason.INAPPROPRIATE:
        question.is_disabled = True
        quiz = await db.get(Quiz, question.quiz_id)
        quiz.status = QuizVariantStatus.RETIRED
    await db.commit()
    return dict(message="Thank you. Your flag is saved; your score and points stay the same.")
