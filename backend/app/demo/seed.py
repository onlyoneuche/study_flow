"""Local synthetic demo history, replayed through study, grading and streak services.

Reset means a fresh active generation. Immutable ledger/history is archived, never erased.
"""

import asyncio
import json
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from fastapi_users.password import PasswordHelper
from sqlalchemy import func, or_, select

from app.auth.schemas import UserCreate
from app.core.calendar import LAGOS, lagos_date, latest_evaluable_day, monday_of
from app.core.config import get_settings
from app.core.study import cache_key, normalise, normalise_subject
from app.db.database import Database
from app.db.types import utc_now
from app.models import (
    DemoSeedRun,
    Group,
    GroupMember,
    GroupStreak,
    Invite,
    PointsLedger,
    QuizAttempt,
    SessionParticipant,
    StudySession,
    User,
)
from app.models.enums import (
    EducationLevel,
    MemberRole,
    QuizSource,
    QuizStatus,
    SessionMode,
    SessionStatus,
)
from app.quizzes.schema import QuizDocument
from app.quizzes.seed import seed_quizzes_in_session
from app.quizzes.worker import Job, questions_for, store_quiz
from app.services.focus import SummaryInput, save_summary
from app.services.groups import group_view, new_invite
from app.services.jobs import SingleInstanceLock
from app.services.quizzes import submit_attempt
from app.services.sessions import advance_session, heartbeat, join_session
from app.services.streaks import evaluate_day

PASSWORD = "StudyFlow-demo-2026!"
DOMAIN = "demo.studyflow.example.com"
SQUAD_NAMES = ("Ada", "Tunde", "Zainab", "Chidi", "Emeka", "Funmi")
RIVAL_NAMES = ("Ife", "Musa", "Bisi")
ALL_NAMES = (*SQUAD_NAMES, *RIVAL_NAMES)
SUBJECTS = {
    "Ada": "Chemistry",
    "Tunde": "Physics",
    "Zainab": "Biology",
    "Chidi": "Mathematics",
    "Emeka": "Economics",
    "Funmi": "English",
    "Ife": "Chemistry",
    "Musa": "Mathematics",
    "Bisi": "Biology",
}


@dataclass
class Learner:
    user: User
    entry: dict


def email(name):
    return f"{name.lower()}@{DOMAIN}"


def start_of(day):
    return datetime.combine(day, time.min, LAGOS)


def banks():
    entries = json.loads((Path(__file__).parents[1] / "quizzes/demo_quizzes.json").read_text())
    entries += json.loads(Path(__file__).with_name("subject_quizzes.json").read_text())
    result = {}
    for entry in entries:
        QuizDocument.model_validate({"questions": entry["questions"]})
        result.setdefault(entry["subject"], entry)
    return result


async def archive_previous(db, now):
    previous = await db.scalar(select(DemoSeedRun).where(DemoSeedRun.is_active.is_(True)))
    ids = set(previous.user_ids) if previous else set()
    # A reserved address without an ownership record belongs to somebody else, regardless of name.
    collisions = (
        await db.scalars(
            select(User).where(
                User.email.in_([email(name) for name in ALL_NAMES]), User.id.not_in(ids)
            )
        )
    ).all()
    if collisions:
        raise RuntimeError("A demo email already belongs to a non-demo account. Nothing was reset.")
    if not previous:
        return
    groups = list(
        await db.scalars(
            select(Group).where(or_(Group.id.in_(previous.group_ids), Group.owner_id.in_(ids)))
        )
    )
    gids = {g.id for g in groups}
    if any(g.owner_id not in ids for g in groups):
        raise RuntimeError("A demo group now has a non-demo owner. Nothing was reset.")
    mixed = await db.scalar(
        select(GroupMember.id)
        .where(
            or_(
                GroupMember.group_id.in_(gids) & GroupMember.user_id.not_in(ids),
                GroupMember.user_id.in_(ids) & GroupMember.group_id.not_in(gids),
            )
        )
        .limit(1)
    )
    sessions = list(
        await db.scalars(
            select(StudySession).where(
                or_(StudySession.host_id.in_(ids), StudySession.group_id.in_(gids))
            )
        )
    )
    sids = {s.id for s in sessions}
    foreign_participant = await db.scalar(
        select(SessionParticipant.id)
        .where(
            or_(
                SessionParticipant.session_id.in_(sids) & SessionParticipant.user_id.not_in(ids),
                SessionParticipant.user_id.in_(ids) & SessionParticipant.session_id.not_in(sids),
            )
        )
        .limit(1)
    )
    if (
        mixed
        or foreign_participant
        or any(
            s.host_id not in ids or (s.group_id is not None and s.group_id not in gids)
            for s in sessions
        )
    ):
        raise RuntimeError(
            "Demo data is mixed with non-demo membership or sessions. Nothing was reset. "
            "Use a separate demo database to keep that shared history intact."
        )
    users = list(await db.scalars(select(User).where(User.id.in_(ids))))
    archive_emails = {u.id: f"archived-{previous.id}-{u.id}@{DOMAIN}" for u in users}
    if await db.scalar(select(User.id).where(User.email.in_(archive_emails.values())).limit(1)):
        raise RuntimeError("An archive email is already in use. Nothing was reset.")
    for g in groups:
        g.is_active = False
    for member in await db.scalars(
        select(GroupMember).where(GroupMember.group_id.in_(gids), GroupMember.left_at.is_(None))
    ):
        if member.joined_at > now:
            raise RuntimeError("Cannot reset demo data using a clock earlier than its membership.")
        member.left_at = now
    for invite in await db.scalars(select(Invite).where(Invite.group_id.in_(gids))):
        invite.revoked_at = invite.revoked_at or now
    for s in sessions:
        if s.status in {SessionStatus.RUNNING, SessionStatus.SCHEDULED}:
            s.status = SessionStatus.CANCELLED
    for u in users:
        u.email, u.is_active = archive_emails[u.id], False
    previous.is_active, previous.archived_at = False, now
    await db.flush()


async def create_people(db, entries, created):
    result = {}
    helper = PasswordHelper()
    for name in ALL_NAMES:
        data = UserCreate(
            email=email(name),
            password=PASSWORD,
            display_name=name,
            level=EducationLevel.SS2,
            audience_band="secondary",
            guardian_consent=True,
        )
        fields = data.create_update_dict()
        fields.pop("password")
        # Fictional fixture consent and verified email; these are not real learners' confirmations.
        learner = User(
            **fields, hashed_password=helper.hash(PASSWORD), is_verified=True, created_at=created
        )
        learner.guardian_consent_at = created
        db.add(learner)
        await db.flush()
        result[name] = Learner(learner, entries[SUBJECTS[name]])
    return result


async def create_squad(db, name, people, day):
    created = start_of(day)
    g = Group(name=name, owner_id=people[0].user.id, audience_band="secondary", created_at=created)
    db.add(g)
    await db.flush()
    for i, person in enumerate(people):
        db.add(
            GroupMember(
                group_id=g.id,
                user_id=person.user.id,
                joined_at=created,
                created_at=created,
                role=MemberRole.OWNER if i == 0 else MemberRole.MEMBER,
            )
        )
    await db.flush()
    return g


async def historical_quiz(db, learner):
    entry = learner.entry
    subject, topic = normalise_subject(entry["subject"]), normalise(entry["topic"])
    job = Job(
        cache_key(subject, topic, "SS2"),
        entry["subject"],
        entry["topic"],
        subject,
        topic,
        EducationLevel.SS2,
    )
    document = QuizDocument.model_validate({"questions": entry["questions"]})
    # Historical imports use the normal validator/shuffler but cannot evict anyone's live cache.
    return await store_quiz(
        db, job, document, "demo-history/v1", QuizSource.FALLBACK, historical=True
    )


async def replay(
    db, people, g, start, minutes=25, mode=SessionMode.SOLO, scores=None, prepare_at=None
):
    end = start + timedelta(minutes=minutes)
    s = StudySession(
        host_id=people[0].user.id,
        group_id=g.id if mode == SessionMode.LIVE else None,
        mode=mode,
        planned_minutes=minutes,
        scheduled_at=start,
        started_at=start,
        end_at=end,
        status=SessionStatus.RUNNING,
        created_at=start,
    )
    db.add(s)
    await db.flush()
    participations = []
    for learner in people:
        p, _ = await join_session(
            db, s, learner.user, learner.entry["subject"], learner.entry["topic"], start
        )
        if scores is not None or prepare_at is not None:
            quiz = await historical_quiz(db, learner)
            p.quiz_id, p.quiz_status = quiz.id, QuizStatus.READY
        else:
            p.quiz_status = QuizStatus.UNAVAILABLE
        # Simulated observations use the same heartbeat accounting as a real room.
        for second in range(60, minutes * 60 + 1, 60):
            heartbeat(s, p, start + timedelta(seconds=second))
        participations.append(p)
    await advance_session(db, s, end)
    for i, p in enumerate(participations):
        if scores is None and prepare_at is None:
            continue
        a = QuizAttempt(
            participant_id=p.id,
            quiz_id=p.quiz_id,
            user_id=p.user_id,
            started_at=prepare_at or end + timedelta(minutes=1),
            created_at=end,
        )
        db.add(a)
        await db.flush()
        if scores is not None:
            questions = await questions_for(db, p.quiz_id)
            answers = [
                q.correct_index if q.position < scores[i] else (q.correct_index + 1) % 4
                for q in questions
            ]
            await submit_attempt(db, s, p, a, answers, end + timedelta(minutes=3))
    await db.flush()
    return participations


async def week_points(db, gid, week):
    return await db.scalar(
        select(func.coalesce(func.sum(PointsLedger.points), 0)).where(
            PointsLedger.group_id == gid, PointsLedger.week_start == week
        )
    )


def top_up_plan(slots, gap):
    # Minimise the gap using real allowed durations/bonuses; never invent a ledger adjustment.
    states = {0: []}
    for learner, end in slots:
        updated = dict(states)
        for total, path in states.items():
            for points, minutes, mode in (
                (8, 25, SessionMode.SOLO),
                (13, 25, SessionMode.LIVE),
                (15, 45, SessionMode.SOLO),
                (20, 60, SessionMode.SOLO),
                (25, 60, SessionMode.LIVE),
            ):
                if total + points > gap + 25 or lagos_date(
                    end - timedelta(minutes=minutes)
                ) != lagos_date(end):
                    continue
                choice = [*path, (learner, end, minutes, mode)]
                if total + points not in updated or len(choice) < len(updated[total + points]):
                    updated[total + points] = choice
        states = updated
    best = min(states, key=lambda total: (abs(gap - total), len(states[total]), total > gap))
    return states[best]


async def fill_week(db, g, people, now, target):
    week = monday_of(lagos_date(now))
    gap = target - await week_points(db, g.id, week)
    if gap <= 0:
        return
    slots = []
    for learner in people:
        count = await db.scalar(
            select(func.count())
            .select_from(SessionParticipant)
            .where(
                SessionParticipant.user_id == learner.user.id,
                SessionParticipant.session_date == lagos_date(now),
                SessionParticipant.completed_at.is_not(None),
            )
        )
        for slot in range(count, 3):
            end = now - timedelta(minutes=10 + 70 * slot)
            if lagos_date(end - timedelta(minutes=25)) == lagos_date(now):
                slots.append((learner, end))
    for learner, end, minutes, mode in top_up_plan(slots, gap):
        await replay(db, [learner], g, end - timedelta(minutes=minutes), minutes, mode)


async def seed_demo(database, now=None, frontend_url="http://localhost:3000"):
    now = now or utc_now()
    lock = SingleInstanceLock(database.engine.url.database)
    lock.acquire()
    try:
        async with database.session_factory() as db:
            await db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
            await archive_previous(db, now)
            entries = banks()
            last = latest_evaluable_day(now)
            first = last - timedelta(days=12)
            people = await create_people(db, entries, start_of(first))
            main = [people[name] for name in SQUAD_NAMES]
            rivals = [people[name] for name in RIVAL_NAMES]
            squad = await create_squad(db, "Study Squad", main, first)
            rival = await create_squad(db, "Lagos Brainiacs", rivals, last - timedelta(days=6))
            focus_demo = None
            for day_offset in range(13):
                day = first + timedelta(days=day_offset)
                frozen = day == last - timedelta(days=1)
                present = main[:-1] if frozen else main
                scored = (
                    [8, 5, 7, 8, 4, 6]
                    if day == last - timedelta(days=5)
                    else ([11, 9, 10, 11, 10, 9] if day == last else None)
                )
                at = start_of(day) + timedelta(hours=9)
                pair = present[:3] if day == last else present[1:3]
                live_participants = await replay(
                    db,
                    pair,
                    squad,
                    at,
                    mode=SessionMode.LIVE,
                    scores=[scored[main.index(learner)] for learner in pair] if scored else None,
                )
                if day == last:
                    for participant, attention in zip(live_participants, [90, 80, 70], strict=True):
                        await save_summary(
                            db,
                            await db.get(StudySession, participant.session_id),
                            participant,
                            SummaryInput(
                                opted_in=True,
                                attentive_pct=attention,
                                away_seconds=30,
                                samples=1400,
                                paused_seconds=90,
                                sample_fps=1.0,
                                tracker_version="mp-demo/minimal-v1",
                            ),
                            at + timedelta(minutes=29),
                        )
                    focus_demo = live_participants[0]
                for i, learner in enumerate(present):
                    if learner not in pair:
                        await replay(
                            db,
                            [learner],
                            squad,
                            at + timedelta(hours=1),
                            scores=[scored[i]] if scored else None,
                        )
                if day >= last - timedelta(days=6):
                    await replay(db, rivals, rival, at, 45, SessionMode.LIVE)
            # Evaluate only the owned groups, never invoke global catch-up on non-demo groups.
            for g, begin in ((squad, first), (rival, last - timedelta(days=6))):
                streak = GroupStreak(group_id=g.id, current=0, best=0)
                db.add(streak)
                day = begin
                while day <= last:
                    await evaluate_day(db, g, streak, day)
                    await db.flush()
                    day += timedelta(days=1)
            # Keep Ada below the daily cap for the presenter's real quiz submission.
            end = now - timedelta(minutes=10)
            if lagos_date(end - timedelta(minutes=25)) == lagos_date(now):
                for learner in main[1:5]:
                    await replay(db, [learner], squad, end - timedelta(minutes=25))
                for learner in rivals:
                    await replay(db, [learner], rival, end - timedelta(minutes=25))
            await fill_week(db, squad, main[1:], now, 340)
            main_points = await week_points(db, squad.id, monday_of(lagos_date(now)))
            await fill_week(db, rival, rivals, now, math.ceil((main_points / 6 + 8) * 3))
            # An already-studied participation gives the short pitch a genuine, timed quiz flow.
            prepared = (
                await replay(db, [main[0]], squad, now - timedelta(minutes=26), prepare_at=now)
            )[0]
            scheduled = max(
                start_of(lagos_date(now)) + timedelta(hours=19), now + timedelta(minutes=10)
            )
            before_midnight = start_of(lagos_date(now) + timedelta(days=1)) - timedelta(seconds=1)
            scheduled = min(scheduled, before_midnight) if before_midnight > now else scheduled
            live = StudySession(
                host_id=main[0].user.id,
                group_id=squad.id,
                mode=SessionMode.LIVE,
                planned_minutes=45,
                scheduled_at=scheduled,
                started_at=scheduled,
                end_at=scheduled + timedelta(minutes=45),
                status=SessionStatus.SCHEDULED,
            )
            db.add(live)
            invite = await new_invite(db, squad, main[0].user.id, max_uses=7, now=now)
            await seed_quizzes_in_session(db, preserve_cache=True)
            db.add(
                DemoSeedRun(
                    user_ids=[p.user.id for p in people.values()],
                    group_ids=[squad.id, rival.id],
                    created_at=now,
                )
            )
            await db.flush()
            view = await group_view(db, squad, main[0].user.id, str(frontend_url), now)
            summary = dict(
                focus_session_id=focus_demo.session_id,
                focus_participant_id=focus_demo.id,
                group_id=squad.id,
                quiz_participant_id=prepared.id,
                session_id=live.id,
                invite_code=invite.code,
                weekly_points=view["weekly_points"],
                weekly_target=view["weekly_target"],
                streak=view["streak"],
                freezes_remaining=view["freezes_remaining"],
                scheduled_at=scheduled.astimezone(LAGOS).isoformat(),
                evaluated_through=last.isoformat(),
            )
            await db.commit()
            return summary
    finally:
        lock.release()


async def main():
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        summary = await seed_demo(database, frontend_url=str(settings.frontend_url))
        origin = str(settings.frontend_url).rstrip("/")
        print("\nStudyFlow demo ready (fictional SS2 accounts; one audience band).")
        print(f"Ada login: {email('Ada')}\nPassword: {PASSWORD}")
        print(f"Friends use the same password: {', '.join(email(n) for n in SQUAD_NAMES[1:])}")
        print(f"Weekly bar: {summary['weekly_points']}/{summary['weekly_target']} points")
        print(
            f"Streak: {summary['streak']} days; "
            f"freezes remaining this week: {summary['freezes_remaining']}"
        )
        print(f"Evaluated through: {summary['evaluated_through']} (Lagos)")
        print(
            f"Scheduled live: {summary['scheduled_at']} (Lagos)\n"
            f"Group: {origin}/groups/{summary['group_id']}"
        )
        print(
            "Prepared quiz (20-minute timer starts at seed): "
            f"{origin}/participants/{summary['quiz_participant_id']}/quiz"
        )
        print(
            "Synthetic focus comparison (ended live session): "
            f"{origin}/participants/{summary['focus_participant_id']}/quiz"
        )
        print(
            "Rerun before the presentation to refresh its deadlines. "
            "Normal live timers are 25/45/60 minutes."
        )
    except RuntimeError as error:
        raise SystemExit(
            f"Seed stopped: {error}\nStop the backend before seeding this database."
        ) from None
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
