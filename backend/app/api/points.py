from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import aliased

from app.api.groups import DB, Learner
from app.core.calendar import lagos_date, lagos_week_start
from app.models import Group, GroupMember, GroupStreak, PointsLedger, User
from app.models.enums import PointComponent, audience_for_level
from app.services.groups import active_members, fail, require_group

router = APIRouter()


def selected_week(week, now):
    week = week or lagos_week_start(now)
    if week.weekday() != 0:
        fail("invalid_week", "Choose a Monday date for the start of the Lagos week.", 422)
    return week


@router.get("/groups/{group_id}/points")
async def group_points(
    group_id: int, db: DB, user: Learner, request: Request, week: date | None = None
):
    group = await require_group(db, group_id, user.id)
    week = selected_week(week, request.app.state.clock())
    members = await active_members(db, group_id)
    ids = [m.user_id for m in members]
    users = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()}
    original = aliased(PointsLedger)
    improvements = or_(
        PointsLedger.component == PointComponent.IMPROVEMENT,
        and_(
            PointsLedger.component == PointComponent.ADJUSTMENT,
            original.component == PointComponent.IMPROVEMENT,
        ),
    )
    rows = (
        await db.execute(
            select(
                PointsLedger.user_id,
                func.sum(case((improvements, PointsLedger.points), else_=0)),
                func.count(func.distinct(PointsLedger.participant_id)),
            )
            .outerjoin(original, PointsLedger.reverses_id == original.id)
            .where(
                PointsLedger.group_id == group_id,
                PointsLedger.week_start == week,
                PointsLedger.user_id.in_(ids),
            )
            .group_by(PointsLedger.user_id)
        )
    ).all()
    totals = {uid: (improvement, completed) for uid, improvement, completed in rows}
    ranking = [
        dict(
            user_id=uid,
            display_name=users[uid].display_name,
            improvement_points=totals.get(uid, (0, 0))[0],
            completed_sessions=totals.get(uid, (0, 0))[1],
        )
        for uid in ids
    ]
    ranking.sort(
        key=lambda row: (-row["improvement_points"], -row["completed_sessions"], row["user_id"])
    )
    points = await db.scalar(
        select(func.coalesce(func.sum(PointsLedger.points), 0)).where(
            PointsLedger.group_id == group_id, PointsLedger.week_start == week
        )
    )
    target = 100 * len(members)
    return dict(
        group_id=group_id,
        name=group.name,
        week_start=week,
        weekly_points=points,
        member_count=len(members),
        target=target,
        fill_pct=min(100, 100 * points / max(1, target)),
        ranking=[dict(rank=i + 1, **row) for i, row in enumerate(ranking)],
    )


@router.get("/leaderboard/groups")
async def group_leaderboard(db: DB, user: Learner, request: Request, week: date | None = None):
    week = selected_week(week, request.app.state.clock())
    counts = (
        select(GroupMember.group_id.label("group_id"), func.count().label("members"))
        .where(GroupMember.left_at.is_(None))
        .group_by(GroupMember.group_id)
        .subquery()
    )
    totals = (
        select(
            PointsLedger.group_id.label("group_id"), func.sum(PointsLedger.points).label("points")
        )
        .where(PointsLedger.week_start == week)
        .group_by(PointsLedger.group_id)
        .subquery()
    )
    points = func.coalesce(totals.c.points, 0)
    streak = func.coalesce(GroupStreak.current, 0)
    average = points * 1.0 / counts.c.members
    rows = (
        await db.execute(
            select(Group.id, Group.name, counts.c.members, points, average, streak)
            .join(counts, counts.c.group_id == Group.id)
            .outerjoin(totals, totals.c.group_id == Group.id)
            .outerjoin(GroupStreak, GroupStreak.group_id == Group.id)
            .where(Group.is_active.is_(True), Group.audience_band == audience_for_level(user.level))
            .order_by(average.desc(), streak.desc(), Group.id)
            .limit(50)
        )
    ).all()
    # Only group names and aggregate figures; no member profiles or raw scores.
    return dict(
        week_start=week,
        audience_band=audience_for_level(user.level),
        groups=[
            dict(
                rank=i + 1,
                group_id=gid,
                name=name,
                member_count=members,
                weekly_points=total,
                points_per_member=avg,
                streak=current,
            )
            for i, (gid, name, members, total, avg, current) in enumerate(rows)
        ],
    )


@router.get("/users/me/ledger")
async def my_ledger(
    db: DB,
    user: Learner,
    request: Request,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    now = request.app.state.clock()
    start, end = from_ or lagos_week_start(now), to or lagos_date(now)
    if start > end:
        fail("invalid_dates", "The start date must be on or before the end date.", 422)
    rows = (
        await db.execute(
            select(PointsLedger, Group.name)
            .join(Group)
            .where(
                PointsLedger.user_id == user.id,
                PointsLedger.lagos_date >= start,
                PointsLedger.lagos_date <= end,
            )
            .order_by(PointsLedger.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return dict(
        from_date=start,
        to_date=end,
        offset=offset,
        entries=[
            dict(
                id=row.id,
                group_id=row.group_id,
                group_name=name,
                participant_id=row.participant_id,
                component=row.component,
                points=row.points,
                lagos_date=row.lagos_date,
                week_start=row.week_start,
                created_at=row.created_at,
                reverses_id=row.reverses_id,
            )
            for row, name in rows
        ],
    )
