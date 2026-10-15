from datetime import timedelta
from math import floor

from sqlalchemy import func, select

from app.core.calendar import monday_of
from app.core.study import required_seconds
from app.models import GroupMember, PointsLedger, QuizAttempt, SessionParticipant, StudySession
from app.models.enums import ParticipantStatus as PS
from app.models.enums import PointComponent as PC
from app.models.enums import QuizStatus


def round_half_up(value):
    return floor(value + 0.5)


def deadline(participant, attempt=None):
    end = participant.ended_at + timedelta(minutes=30)
    return min(end, attempt.started_at + timedelta(minutes=20)) if attempt else end


async def complete(db, session, participant, now, attempt=None):
    if participant.completed_at or participant.active_seconds < required_seconds(
        session, participant
    ):
        return
    prior = await db.scalar(
        select(func.count())
        .select_from(SessionParticipant)
        .where(
            SessionParticipant.user_id == participant.user_id,
            SessionParticipant.session_date == participant.session_date,
            SessionParticipant.completed_at.is_not(None),
            SessionParticipant.id != participant.id,
        )
    )
    group_ids = list(
        (
            await db.scalars(
                select(GroupMember.group_id).where(
                    GroupMember.user_id == participant.user_id, GroupMember.left_at.is_(None)
                )
            )
        ).all()
    )
    participant.status = PS.COMPLETED
    participant.completed_at = now
    components = {PC.BASE: round_half_up(session.planned_minutes / 3)}
    # Step 7 adds quiz/improvement components and counted baseline entries here.
    for group_id in group_ids:
        awards = (
            {PC.DAILY_CAP: 0}
            if prior >= 3
            else {
                **components,
                **(
                    {PC.LIVE: 5}
                    if participant.is_live_credited and group_id == session.group_id
                    else {}
                ),
            }
        )
        for component, points in awards.items():
            db.add(
                PointsLedger(
                    user_id=participant.user_id,
                    group_id=group_id,
                    participant_id=participant.id,
                    component=component,
                    points=points,
                    lagos_date=participant.session_date,
                    week_start=monday_of(participant.session_date),
                )
            )


async def settle_due(db, now):
    participants = (
        await db.scalars(
            select(SessionParticipant)
            .where(
                SessionParticipant.ended_at.is_not(None),
                SessionParticipant.completed_at.is_(None),
                SessionParticipant.status != PS.INCOMPLETE,
            )
            .order_by(SessionParticipant.ended_at, SessionParticipant.id)
        )
    ).all()
    for participant in participants:
        attempt = await db.scalar(
            select(QuizAttempt).where(QuizAttempt.participant_id == participant.id)
        )
        if participant.quiz_status == QuizStatus.UNAVAILABLE or now > deadline(
            participant, attempt
        ):
            await complete(db, await db.get(StudySession, participant.session_id), participant, now)
