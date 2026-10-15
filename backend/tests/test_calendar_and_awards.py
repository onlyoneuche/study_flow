from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.core.calendar import lagos_week_start, latest_evaluable_day
from app.models import GroupMember, PointsLedger, StreakFreeze
from tests.factories import graph, group, user
from tests.test_schema_constraints import rejected


def test_awards_are_unique_per_user_group_session_component_not_across_groups(db):
    data = graph(db)
    squads = [data.group, group(db, data.user), group(db, data.user)]
    for squad in squads:
        db.add(GroupMember(group_id=squad.id, user_id=data.user.id))
        db.add(
            PointsLedger(
                user_id=data.user.id,
                group_id=squad.id,
                participant_id=data.participant.id,
                component="base",
                points=15,
                lagos_date=date(2026, 10, 15),
                week_start=date(2026, 10, 12),
            )
        )
        db.flush()
    assert db.scalar(select(func.count()).select_from(PointsLedger)) == 3
    rejected(
        db,
        lambda: db.add(
            PointsLedger(
                user_id=data.user.id,
                group_id=data.group.id,
                participant_id=data.participant.id,
                component="base",
                points=15,
                lagos_date=date(2026, 10, 15),
                week_start=date(2026, 10, 12),
            )
        ),
        "already exists",
    )
    other = user(db)
    rejected(
        db,
        lambda: db.add(
            PointsLedger(
                user_id=other.id,
                group_id=data.group.id,
                participant_id=data.participant.id,
                component="quiz",
                points=7,
                lagos_date=date(2026, 10, 15),
                week_start=date(2026, 10, 12),
            )
        ),
        "user must match",
    )


def test_freeze_week_changes_at_monday_midnight_lagos(db):
    before = datetime(2026, 10, 18, 22, 59, 59, tzinfo=UTC)
    after = datetime(2026, 10, 18, 23, 0, tzinfo=UTC)
    assert lagos_week_start(before) == date(2026, 10, 12)
    assert lagos_week_start(after) == date(2026, 10, 19)
    squad = group(db)
    for day in (date(2026, 10, 17), date(2026, 10, 18)):
        db.add(StreakFreeze(group_id=squad.id, date=day, week_start=lagos_week_start(before)))
        db.flush()
    rejected(
        db,
        lambda: db.add(
            StreakFreeze(
                group_id=squad.id, date=date(2026, 10, 16), week_start=lagos_week_start(before)
            )
        ),
        "at most 2",
    )
    db.add(
        StreakFreeze(group_id=squad.id, date=date(2026, 10, 19), week_start=lagos_week_start(after))
    )
    db.flush()


@pytest.mark.parametrize("hour,minute,expected", [(0, 59, 13), (1, 0, 14), (23, 30, 14)])
def test_catch_up_waits_for_two_am_lagos(hour, minute, expected):
    assert latest_evaluable_day(datetime(2026, 10, 15, hour, minute, tzinfo=UTC)) == date(
        2026, 10, expected
    )
