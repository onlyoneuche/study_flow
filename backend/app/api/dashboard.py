from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.api.groups import DB, Learner
from app.core.calendar import lagos_date, lagos_week_start
from app.models import Group, GroupMember, QuizAttempt, SessionParticipant, StudySession
from app.models.enums import ParticipantStatus
from app.services.completion import deadline
from app.services.groups import group_view
from app.services.sessions import open_sessions, session_view

router = APIRouter()


@router.get("/users/me/dashboard")
async def dashboard(db: DB, user: Learner, request: Request):
    now = request.app.state.clock()
    groups = (
        await db.scalars(
            select(Group)
            .join(GroupMember)
            .where(
                GroupMember.user_id == user.id,
                GroupMember.left_at.is_(None),
                Group.is_active.is_(True),
            )
            .order_by(Group.id)
        )
    ).all()
    recent = (
        await db.execute(
            select(SessionParticipant, StudySession, QuizAttempt)
            .join(StudySession, StudySession.id == SessionParticipant.session_id)
            .outerjoin(QuizAttempt, QuizAttempt.participant_id == SessionParticipant.id)
            .where(SessionParticipant.user_id == user.id)
            .order_by(SessionParticipant.joined_at.desc(), SessionParticipant.id.desc())
            .limit(8)
        )
    ).all()
    weekly_completed = await db.scalar(
        select(func.count())
        .select_from(SessionParticipant)
        .where(
            SessionParticipant.user_id == user.id,
            SessionParticipant.status == ParticipantStatus.COMPLETED,
            SessionParticipant.session_date >= lagos_week_start(now),
            SessionParticipant.session_date <= lagos_date(now),
        )
    )
    return dict(
        server_now=now,
        weekly_completed=weekly_completed,
        groups=[
            await group_view(db, g, user.id, str(request.app.state.settings.frontend_url), now)
            for g in groups
        ],
        sessions=[
            await session_view(db, s, user.id, now) for s in await open_sessions(db, user.id)
        ],
        recent=[
            dict(
                participant_id=p.id,
                session_id=s.id,
                subject=p.subject,
                topic=p.topic,
                level=p.level,
                planned_minutes=s.planned_minutes,
                mode=s.mode,
                session_date=p.session_date,
                status=p.status,
                ended_at=p.ended_at,
                quiz_status=p.quiz_status,
                submitted=bool(a and a.submitted_at),
                quiz_available=bool(
                    p.ended_at
                    and p.status != ParticipantStatus.INCOMPLETE
                    and not (a and a.submitted_at)
                    and now <= deadline(p, a)
                ),
            )
            for p, s, a in recent
        ],
    )
