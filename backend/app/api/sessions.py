from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.groups import DB, Learner
from app.models import StudySession
from app.models.enums import ParticipantStatus as PS
from app.models.enums import SessionMode
from app.models.enums import SessionStatus as SS
from app.services.completion import settle_due
from app.services.groups import fail, require_group
from app.services.sessions import (
    advance_session,
    end_participant,
    heartbeat,
    join_session,
    open_sessions,
    participant_for,
    participant_view,
    require_session,
    required_seconds,
    session_view,
)

router = APIRouter()


class Topic(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    subject: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=300)


class Solo(Topic):
    planned_minutes: Literal[25, 45, 60]


class Live(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planned_minutes: Literal[25, 45, 60]
    scheduled_at: AwareDatetime | None = None


async def state(db, session, user, request):
    now = request.app.state.clock()
    await advance_session(db, session, now)
    await settle_due(db, now)
    await db.commit()
    return await session_view(db, session, user.id, now)


@router.get("/sessions")
async def list_sessions(db: DB, user: Learner, request: Request):
    # State transitions are handled by the runtime; this listing remains read-only.
    sessions = await open_sessions(db, user.id)
    return [await session_view(db, s, user.id, request.app.state.clock()) for s in sessions]


@router.post("/sessions/solo", status_code=201)
async def create_solo(
    data: Solo, db: DB, user: Learner, request: Request, background_tasks: BackgroundTasks
):
    now = request.app.state.clock()
    session = StudySession(
        host_id=user.id,
        mode=SessionMode.SOLO,
        planned_minutes=data.planned_minutes,
        started_at=now,
        scheduled_at=now,
        end_at=now + timedelta(minutes=data.planned_minutes),
        status=SS.RUNNING,
    )
    db.add(session)
    await db.flush()
    participant, _ = await join_session(db, session, user, data.subject, data.topic, now)
    background_tasks.add_task(request.app.state.quizzes.enqueue, participant.id)
    return await state(db, session, user, request)


@router.post("/groups/{group_id}/sessions", status_code=201)
async def create_live(group_id: int, data: Live, db: DB, user: Learner, request: Request):
    await require_group(db, group_id, user.id)
    now = request.app.state.clock()
    scheduled: datetime = data.scheduled_at or now
    if scheduled < now and data.scheduled_at is not None:
        fail("past_schedule", "Choose a future start time, or start now.", 422)
    session = StudySession(
        group_id=group_id,
        host_id=user.id,
        mode=SessionMode.LIVE,
        planned_minutes=data.planned_minutes,
        scheduled_at=scheduled,
        started_at=scheduled,
        end_at=scheduled + timedelta(minutes=data.planned_minutes),
        status=SS.SCHEDULED if scheduled > now else SS.RUNNING,
    )
    db.add(session)
    await db.flush()
    return await state(db, session, user, request)


@router.post("/sessions/{session_id}/join")
async def join(
    session_id: int,
    data: Topic,
    db: DB,
    user: Learner,
    request: Request,
    background_tasks: BackgroundTasks,
):
    session = await require_session(db, session_id, user.id)
    participant, solo_offer = await join_session(
        db, session, user, data.subject, data.topic, request.app.state.clock()
    )
    await db.commit()
    if participant:
        background_tasks.add_task(request.app.state.quizzes.enqueue, participant.id)
    return dict(
        participant=participant_view(session, participant),
        solo_offer=solo_offer,
        message="More than 10 minutes late: start solo with your own clock, "
        "or stay in the room for presence only."
        if solo_offer
        else "Joined. Your topic and level are saved for this session.",
    )


@router.get("/sessions/{session_id}")
async def get_session_state(session_id: int, db: DB, user: Learner, request: Request):
    session = await require_session(db, session_id, user.id)
    return await state(db, session, user, request)


@router.post("/sessions/{session_id}/leave")
async def leave(session_id: int, db: DB, user: Learner, request: Request):
    session = await require_session(db, session_id, user.id)
    participant = await participant_for(db, session.id, user.id)
    if not participant:
        fail("not_joined", "Join this session first.")
    now = request.app.state.clock()
    if not participant.ended_at:
        heartbeat(session, participant, now)
        participant.status = PS.LEFT
    await advance_session(db, session, now)
    return await state(db, session, user, request)


@router.post("/sessions/{session_id}/finish")
async def finish(session_id: int, db: DB, user: Learner, request: Request):
    session = await require_session(db, session_id, user.id)
    participant = await participant_for(db, session.id, user.id)
    if session.mode != SessionMode.SOLO:
        fail("live_end", "Live sessions finish at the shared end time. You can leave and rejoin.")
    if not participant:
        fail("not_joined", "Join this session first.")
    if participant.ended_at:
        return await state(db, session, user, request)
    heartbeat(session, participant, request.app.state.clock())
    if participant.active_seconds < required_seconds(session, participant):
        # Persist the heartbeat even when early finish is refused.
        await db.commit()
        fail("not_enough_time", "Keep studying until you have completed at least 80% active time.")
    now = request.app.state.clock()
    end_participant(session, participant, now)
    session.end_at = participant.ended_at
    session.status = SS.ENDED
    return await state(db, session, user, request)
