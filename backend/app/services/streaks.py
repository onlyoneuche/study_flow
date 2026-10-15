"""Historical membership and completion records are the only streak inputs."""

from datetime import datetime, time, timedelta

from sqlalchemy import func, or_, select

from app.core.calendar import LAGOS, lagos_date, latest_evaluable_day, monday_of
from app.models import (
    Group,
    GroupMember,
    GroupStreak,
    GroupStreakDay,
    SessionParticipant,
    StreakFreeze,
)
from app.models.enums import ParticipantStatus, StreakOutcome


async def evaluate_day(db, group, streak, day):
    existing = await db.scalar(
        select(GroupStreakDay).where(
            GroupStreakDay.group_id == group.id, GroupStreakDay.date == day
        )
    )
    if existing:
        streak.last_evaluated_date = day
        return
    start = datetime.combine(day, time.min, LAGOS)
    members = set(
        await db.scalars(
            select(GroupMember.user_id).where(
                GroupMember.group_id == group.id,
                GroupMember.joined_at <= start,
                or_(GroupMember.left_at.is_(None), GroupMember.left_at > start),
            )
        )
    )
    done = set(
        await db.scalars(
            select(SessionParticipant.user_id).where(
                SessionParticipant.user_id.in_(members),
                SessionParticipant.session_date == day,
                SessionParticipant.status == ParticipantStatus.COMPLETED,
            )
        )
    )
    if len(members) < 3:
        outcome = StreakOutcome.PAUSED
    elif done == members:
        streak.current += 1
        streak.best = max(streak.best, streak.current)
        outcome = StreakOutcome.KEPT
    else:
        used = await db.scalar(
            select(func.count())
            .select_from(StreakFreeze)
            .where(StreakFreeze.group_id == group.id, StreakFreeze.week_start == monday_of(day))
        )
        if streak.current > 0 and used < 2:
            db.add(StreakFreeze(group_id=group.id, date=day, week_start=monday_of(day)))
            outcome = StreakOutcome.FROZEN
        else:
            streak.current = 0
            outcome = StreakOutcome.BROKEN
    db.add(
        GroupStreakDay(
            group_id=group.id,
            date=day,
            outcome=outcome,
            completed_count=len(done),
            eligible_count=len(members),
        )
    )
    streak.last_evaluated_date = day


async def catch_up(database, now):
    """Commit each day with its cursor, freeze and streak in one reserved transaction."""
    latest = latest_evaluable_day(now)
    async with database.session_factory() as db:
        group_ids = list(await db.scalars(select(Group.id).where(Group.is_active.is_(True))))
    for group_id in group_ids:
        while True:
            async with database.session_factory() as db:
                await db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
                group = await db.get(Group, group_id)
                if not group or not group.is_active:
                    break
                streak = await db.scalar(
                    select(GroupStreak).where(GroupStreak.group_id == group_id)
                )
                cursor = streak.last_evaluated_date if streak else None
                day = cursor + timedelta(days=1) if cursor else lagos_date(group.created_at)
                if day > latest:
                    break
                if streak is None:
                    streak = GroupStreak(group_id=group_id, current=0, best=0)
                    db.add(streak)
                await evaluate_day(db, group, streak, day)
                await db.commit()
