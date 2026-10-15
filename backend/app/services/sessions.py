from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import lagos_date
from app.core.study import normalise, normalise_subject, required_seconds
from app.models import Group, GroupMember, SessionParticipant, StudySession, User
from app.models.enums import ParticipantStatus as PS
from app.models.enums import QuizStatus, SessionMode
from app.models.enums import SessionStatus as SS
from app.services.completion import complete
from app.services.groups import fail, require_group

REACTIONS = ("💪", "🔥", "📚", "👏")


def heartbeat(session: StudySession, participant: SessionParticipant, now):
    if participant.status in {PS.LEFT, PS.COMPLETED, PS.INCOMPLETE} or participant.ended_at:
        return
    if now < session.started_at:
        return
    end = min(now, session.end_at)
    previous = max(participant.last_heartbeat_at or participant.joined_at, session.started_at)
    # Use the actual gap for grace even if the counting window ends during that gap.
    gap = (now - previous).total_seconds()
    if gap >= 0:
        counted = max(0, int(end.timestamp()) - int(previous.timestamp()))
        participant.active_seconds += counted if gap <= 120 else min(15, counted)
        participant.last_heartbeat_at = end
        participant.status = PS.ACTIVE


def end_participant(session: StudySession, participant: SessionParticipant, now):
    if participant.ended_at:
        return
    participant.ended_at = min(now, session.end_at)
    if participant.active_seconds < required_seconds(session, participant):
        participant.status = PS.INCOMPLETE
    else:
        # Completion and points require the quiz (or its documented unavailable/deadline fallback).
        participant.status = PS.JOINED


async def advance_session(db: AsyncSession, session: StudySession, now):
    if session.status == SS.SCHEDULED and now >= session.started_at:
        session.status = SS.RUNNING
    if session.status in {SS.SCHEDULED, SS.RUNNING} and now >= session.end_at:
        session.status = SS.ENDED
        participants = (
            await db.scalars(
                select(SessionParticipant).where(SessionParticipant.session_id == session.id)
            )
        ).all()
        for participant in participants:
            # End is not a heartbeat: do not award time with no evidence that the PWA stayed open.
            end_participant(session, participant, session.end_at)
            if participant.quiz_status == QuizStatus.UNAVAILABLE:
                await complete(db, session, participant, now)


async def require_session(db: AsyncSession, session_id: int, user_id: int):
    session = await db.get(StudySession, session_id)
    if not session:
        fail("not_found", "This session was not found.", 404)
    if session.mode == SessionMode.LIVE:
        await require_group(db, session.group_id, user_id)
    elif session.host_id != user_id:
        fail("private_session", "This solo session belongs to another learner.", 403)
    return session


async def participant_for(db: AsyncSession, session_id: int, user_id: int):
    return await db.scalar(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id, SessionParticipant.user_id == user_id
        )
    )


async def join_session(
    db: AsyncSession, session: StudySession, user: User, subject: str, topic: str, now
):
    await advance_session(db, session, now)
    if session.status in {SS.ENDED, SS.CANCELLED}:
        fail("ended", "This session has ended. Start a new solo session instead.")
    participant = await participant_for(db, session.id, user.id)
    if participant:
        if participant.status == PS.LEFT and not participant.ended_at:
            participant.status = PS.JOINED
            participant.last_heartbeat_at = max(now, session.started_at)
        return participant, False
    late = max(0, (now - session.started_at).total_seconds())
    if session.mode == SessionMode.LIVE and late > 600:
        # The member can observe via the socket, but does not enter the live goal or earn L.
        return None, True
    participant = SessionParticipant(
        session_id=session.id,
        user_id=user.id,
        subject=subject,
        subject_norm=normalise_subject(subject),
        topic=topic,
        topic_norm=normalise(topic),
        level=user.level,
        joined_at=now,
        late_minutes=late / 60,
        active_seconds=0,
        last_heartbeat_at=max(now, session.started_at),
        status=PS.JOINED,
        is_live_credited=session.mode == SessionMode.LIVE,
        quiz_status=QuizStatus.PENDING,
        session_date=lagos_date(session.started_at),
    )
    db.add(participant)
    await db.flush()
    return participant, False


def participant_view(session, participant):
    if not participant:
        return None
    return dict(
        id=participant.id,
        user_id=participant.user_id,
        subject=participant.subject,
        topic=participant.topic,
        level=participant.level,
        joined_at=participant.joined_at,
        late_minutes=participant.late_minutes,
        active_seconds=participant.active_seconds,
        required_seconds=required_seconds(session, participant),
        status=participant.status,
        is_live_credited=participant.is_live_credited,
        quiz_status=participant.quiz_status,
        ended_at=participant.ended_at,
        session_date=participant.session_date,
        time_met=participant.active_seconds >= required_seconds(session, participant),
        quiz_unlocked=bool(participant.ended_at and participant.status != PS.INCOMPLETE),
    )


async def session_view(db: AsyncSession, session, user_id, now):
    participants = (
        await db.scalars(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == session.id)
            .order_by(SessionParticipant.joined_at, SessionParticipant.id)
        )
    ).all()
    users = (
        await db.scalars(select(User).where(User.id.in_([p.user_id for p in participants])))
    ).all()
    names = {u.id: u.display_name for u in users}
    members = []
    for p in participants:
        status = p.status.value
        if p.ended_at and p.status != PS.INCOMPLETE:
            status = "finished" if p.status == PS.COMPLETED else "quiz_pending"
        elif p.status not in {PS.LEFT, PS.INCOMPLETE, PS.COMPLETED}:
            status = (
                "disconnected" if (now - p.last_heartbeat_at).total_seconds() > 120 else "studying"
            )
            if session.status == SS.SCHEDULED:
                status = "waiting"
        members.append(
            dict(user_id=p.user_id, display_name=names[p.user_id], subject=p.subject, status=status)
        )
    eligible = set()
    if session.group_id:
        eligible = set(
            (
                await db.scalars(
                    select(GroupMember.user_id).where(
                        GroupMember.group_id == session.group_id,
                        GroupMember.joined_at <= session.started_at,
                        (GroupMember.left_at.is_(None))
                        | (GroupMember.left_at > session.started_at),
                    )
                )
            ).all()
        )
    credited = [p for p in participants if p.is_live_credited and p.user_id in eligible]
    group = await db.get(Group, session.group_id) if session.group_id else None
    return dict(
        id=session.id,
        group_id=session.group_id,
        group_name=group.name if group else None,
        host_id=session.host_id,
        mode=session.mode,
        planned_minutes=session.planned_minutes,
        scheduled_at=session.scheduled_at,
        started_at=session.started_at,
        end_at=session.end_at,
        status=session.status,
        server_now=now,
        members=members,
        mine=participant_view(
            session, next((p for p in participants if p.user_id == user_id), None)
        ),
        goal=dict(done=sum(p.status == PS.COMPLETED for p in credited), total=len(eligible)),
        reactions=REACTIONS,
    )


async def open_sessions(db: AsyncSession, user_id: int):
    group_ids = select(GroupMember.group_id).where(
        GroupMember.user_id == user_id, GroupMember.left_at.is_(None)
    )
    return list(
        (
            await db.scalars(
                select(StudySession)
                .where(
                    StudySession.status.in_([SS.SCHEDULED, SS.RUNNING]),
                    (StudySession.group_id.in_(group_ids))
                    | ((StudySession.mode == SessionMode.SOLO) & (StudySession.host_id == user_id)),
                )
                .order_by(StudySession.started_at)
            )
        ).all()
    )
