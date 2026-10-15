from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select

from app.core.calendar import LAGOS, latest_evaluable_day
from app.models import (
    GroupMember,
    GroupStreak,
    GroupStreakDay,
    SessionParticipant,
    StreakFreeze,
    StudySession,
)
from app.models.enums import MemberRole, ParticipantStatus, SessionMode
from app.services.jobs import SingleInstanceLock
from app.services.streaks import catch_up
from tests.factories import group, user

DAY = date(2026, 10, 12)  # Monday


def midnight(day):
    return datetime.combine(day, time.min, LAGOS)


def squad(db, count=3, current=4):
    people = [user(db) for _ in range(count)]
    g = group(db, people[0], created_at=midnight(DAY - timedelta(days=1)))
    memberships = [
        GroupMember(
            group_id=g.id,
            user_id=p.id,
            role=MemberRole.OWNER if i == 0 else MemberRole.MEMBER,
            joined_at=g.created_at,
        )
        for i, p in enumerate(people)
    ]
    streak = GroupStreak(
        group_id=g.id,
        current=current,
        best=max(4, current),
        last_evaluated_date=DAY - timedelta(days=1),
    )
    db.add_all([*memberships, streak])
    db.commit()
    return g, people, memberships, streak


def completed(db, person, day, mode=SessionMode.SOLO):
    s = StudySession(
        host_id=person.id,
        mode=mode,
        planned_minutes=25,
        group_id=db.scalar(select(GroupMember.group_id).where(GroupMember.user_id == person.id))
        if mode == SessionMode.LIVE
        else None,
    )
    db.add(s)
    db.flush()
    db.add(
        SessionParticipant(
            session_id=s.id,
            user_id=person.id,
            subject="Chemistry",
            subject_norm="chemistry",
            topic="Moles",
            topic_norm="moles",
            level=person.level,
            session_date=day,
            status=ParticipantStatus.COMPLETED,
            completed_at=midnight(day) + timedelta(hours=23),
        )
    )
    db.commit()


def run(auth_client, day=DAY):
    auth_client.portal.call(
        catch_up,
        auth_client.app.state.database,
        midnight(day + timedelta(days=1)) + timedelta(hours=2),
    )


def result(db, g, streak, day=DAY):
    db.expire_all()
    db.refresh(streak)
    row = db.scalar(
        select(GroupStreakDay).where(GroupStreakDay.group_id == g.id, GroupStreakDay.date == day)
    )
    assert streak.last_evaluated_date == day
    return row


def test_kept_distinct_members_any_session_and_idempotent(db, auth_client):
    g, people, _, streak = squad(db)
    for i, person in enumerate(people):
        completed(db, person, DAY, SessionMode.SOLO if i % 2 else SessionMode.LIVE)
    completed(db, people[0], DAY)
    run(auth_client)
    run(auth_client)
    row = result(db, g, streak)
    assert (row.outcome, row.completed_count, row.eligible_count) == ("kept", 3, 3)
    assert (streak.current, streak.best) == (5, 5)
    assert db.scalar(select(func.count()).select_from(GroupStreakDay)) == 1
    assert db.scalar(select(func.count()).select_from(StreakFreeze)) == 0


@pytest.mark.parametrize(
    "current,used,outcome,expected",
    [(4, 0, "frozen", 4), (4, 1, "frozen", 4), (4, 2, "broken", 0), (0, 0, "broken", 0)],
)
def test_missed_day_freezes_or_resets(db, auth_client, current, used, outcome, expected):
    g, people, _, streak = squad(db, current=current)
    # Evaluate Wednesday so this week's existing freezes are on prior days.
    day = DAY + timedelta(days=2)
    streak.last_evaluated_date = day - timedelta(days=1)
    for i in range(used):
        db.add(StreakFreeze(group_id=g.id, date=DAY + timedelta(days=i), week_start=DAY))
    db.commit()
    completed(db, people[0], day)
    run(auth_client, day)
    run(auth_client, day)
    row = result(db, g, streak, day)
    assert (row.outcome, row.completed_count, streak.current, streak.best) == (
        outcome,
        1,
        expected,
        4,
    )
    assert db.scalar(select(func.count()).select_from(StreakFreeze)) == used + (outcome == "frozen")


def test_paused_days_advance_cursor_without_spending(db, auth_client):
    g, _, _, streak = squad(db, count=2)
    run(auth_client, DAY + timedelta(days=2))
    row = result(db, g, streak, DAY + timedelta(days=2))
    assert (row.outcome, streak.current) == ("paused", 4)
    assert db.scalar(select(func.count()).select_from(GroupStreakDay)) == 3
    assert db.scalar(select(func.count()).select_from(StreakFreeze)) == 0


def test_membership_at_start_not_end_includes_removed_excludes_later_join(db, auth_client):
    g, people, members, streak = squad(db)
    members[2].left_at = midnight(DAY) + timedelta(hours=12)
    newcomer = user(db)
    db.add(
        GroupMember(
            group_id=g.id, user_id=newcomer.id, joined_at=midnight(DAY) + timedelta(seconds=1)
        )
    )
    db.commit()
    for p in [*people[:2], newcomer]:
        completed(db, p, DAY)
    run(auth_client)
    row = result(db, g, streak)
    assert (row.outcome, row.eligible_count, row.completed_count) == ("frozen", 3, 2)


def test_membership_midnight_boundaries(db, auth_client):
    g, people, members, streak = squad(db)
    members[2].left_at = midnight(DAY)
    newcomer = user(db)
    db.add(GroupMember(group_id=g.id, user_id=newcomer.id, joined_at=midnight(DAY)))
    db.commit()
    for p in [*people[:2], newcomer]:
        completed(db, p, DAY)
    run(auth_client)
    row = result(db, g, streak)
    assert (row.outcome, row.eligible_count, row.completed_count) == ("kept", 3, 3)


def test_multiday_downtime_chronological_freeze_reset_rebuild(db, auth_client):
    g, people, _, streak = squad(db)
    for offset in (0, 4):
        for p in people:
            completed(db, p, DAY + timedelta(days=offset))
    run(auth_client, DAY + timedelta(days=4))
    result(db, g, streak, DAY + timedelta(days=4))
    rows = db.scalars(select(GroupStreakDay).order_by(GroupStreakDay.date)).all()
    assert [r.outcome for r in rows] == ["kept", "frozen", "frozen", "broken", "kept"]
    assert (streak.current, streak.best) == (1, 5)
    run(auth_client, DAY + timedelta(days=4))
    assert db.scalar(select(func.count()).select_from(GroupStreakDay)) == 5


@pytest.mark.parametrize("hour,minute,last", [(1, 59, 10), (2, 0, 11), (23, 59, 11)])
def test_startup_before_after_two_lagos(db, auth_client, hour, minute, last):
    g, _, _, streak = squad(db)
    streak.last_evaluated_date = date(2026, 10, 9)
    db.commit()
    now = datetime(2026, 10, 12, hour, minute, tzinfo=LAGOS)
    auth_client.portal.call(catch_up, auth_client.app.state.database, now)
    result(db, g, streak, date(2026, 10, last))
    assert db.scalar(select(func.max(GroupStreakDay.date))) == date(2026, 10, last)


def test_fresh_group_starts_at_creation_day_no_precreation_records(db, auth_client):
    group(db, created_at=midnight(DAY) + timedelta(hours=8))
    db.commit()
    run(auth_client)
    row = db.scalar(select(GroupStreakDay))
    streak = db.scalar(select(GroupStreak))
    assert (row.date, row.outcome, row.eligible_count, streak.last_evaluated_date) == (
        DAY,
        "paused",
        0,
        DAY,
    )


def test_weekly_freezes_bucket_by_evaluated_day_not_job_day(db, auth_client):
    g, _, _, streak = squad(db)
    sunday = DAY + timedelta(days=6)
    streak.last_evaluated_date = sunday - timedelta(days=1)
    for offset in (4, 5):
        db.add(StreakFreeze(group_id=g.id, date=DAY + timedelta(days=offset), week_start=DAY))
    db.commit()
    run(auth_client, sunday)
    assert result(db, g, streak, sunday).outcome == "broken"
    streak.current = 4
    db.commit()
    run(auth_client, sunday + timedelta(days=1))
    assert result(db, g, streak, sunday + timedelta(days=1)).outcome == "frozen"
    assert db.scalar(select(func.count()).select_from(StreakFreeze)) == 3


def test_single_instance_lock_rejects_second_owner_releases_on_close(tmp_path):
    first = SingleInstanceLock(tmp_path / "study.db")
    second = SingleInstanceLock(tmp_path / "study.db")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="Another StudyFlow instance"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


@pytest.mark.parametrize("month,day", [(1, 1), (3, 29), (10, 25), (12, 31)])
def test_lagos_has_no_dst_at_evaluation_boundary(month, day):
    stamp = datetime(2026, month, day, 1, tzinfo=UTC)
    assert stamp.astimezone(LAGOS).hour == 2
    assert latest_evaluable_day(stamp) == stamp.date() - timedelta(days=1)


def test_job_schedules_are_lagos_crons_and_weekly_does_not_write(auth_client):
    jobs = auth_client.app.state.jobs

    # Replace tick with an async no-op to inspect startup without presence side effects.
    async def tick():
        pass

    auth_client.app.state.presence.tick = tick
    auth_client.portal.call(jobs.start)
    scheduler = auth_client.app.state.presence.scheduler
    nightly = scheduler.get_job("nightly_streaks").trigger
    weekly = scheduler.get_job("weekly_boundary").trigger
    assert str(nightly.timezone) == str(weekly.timezone) == "Africa/Lagos"
    sunday = datetime(2026, 10, 18, 22, 59, tzinfo=UTC)
    assert weekly.get_next_fire_time(None, sunday).astimezone(UTC) == datetime(
        2026, 10, 18, 23, tzinfo=UTC
    )
    assert nightly.get_next_fire_time(None, sunday).astimezone(UTC) == datetime(
        2026, 10, 19, 1, tzinfo=UTC
    )
    auth_client.portal.call(jobs.weekly)
    auth_client.portal.call(jobs.stop)


def test_day_failure_rolls_back_freeze_streak_and_cursor(db, auth_client):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    g, _, _, streak = squad(db)
    db.execute(
        text(
            "CREATE TRIGGER fail_day BEFORE INSERT ON group_streak_days "
            "BEGIN SELECT RAISE(ABORT, 'simulated interruption'); END"
        )
    )
    db.commit()
    with pytest.raises(IntegrityError, match="simulated interruption"):
        run(auth_client)
    db.expire_all()
    assert (streak.current, streak.last_evaluated_date) == (4, DAY - timedelta(days=1))
    assert db.scalar(select(func.count()).select_from(StreakFreeze)) == 0
    db.execute(text("DROP TRIGGER fail_day"))
    db.commit()
    run(auth_client)
    assert result(db, g, streak).outcome == "frozen"


def test_simultaneous_catchup_is_idempotent_even_without_process_lock(db, auth_client):
    import asyncio

    g, _, _, streak = squad(db)

    async def race():
        database = auth_client.app.state.database
        now = midnight(DAY + timedelta(days=1)) + timedelta(hours=2)
        await asyncio.gather(catch_up(database, now), catch_up(database, now))

    auth_client.portal.call(race)
    assert result(db, g, streak).outcome == "frozen"
    assert db.scalar(select(func.count()).select_from(StreakFreeze)) == 1
    assert db.scalar(select(func.count()).select_from(GroupStreakDay)) == 1


def test_archived_group_is_not_evaluated(db, auth_client):
    g, _, _, streak = squad(db)
    g.is_active = False
    db.commit()
    run(auth_client)
    db.expire_all()
    assert streak.last_evaluated_date == DAY - timedelta(days=1)
    assert db.scalar(select(func.count()).select_from(GroupStreakDay)) == 0


def test_group_bar_and_freezes_switch_at_lagos_monday_preserving_ledger(
    db, auth_client, actor, clock
):
    from app.models import PointsLedger
    from tests.factories import graph

    owner = actor()
    data = graph(db)
    data.group.owner_id = owner.id
    db.add(GroupMember(group_id=data.group.id, user_id=owner.id))
    db.add(
        PointsLedger(
            user_id=data.user.id,
            group_id=data.group.id,
            participant_id=data.participant.id,
            component="base",
            points=15,
            lagos_date=date(2026, 10, 18),
            week_start=DAY,
        )
    )
    for day in (date(2026, 10, 17), date(2026, 10, 18)):
        db.add(StreakFreeze(group_id=data.group.id, date=day, week_start=DAY))
    db.commit()
    clock.now = datetime(2026, 10, 18, 22, 59, 59, tzinfo=UTC)
    before = auth_client.get(f"/api/v1/groups/{data.group.id}", headers=owner.headers).json()
    clock.now += timedelta(seconds=1)
    after = auth_client.get(f"/api/v1/groups/{data.group.id}", headers=owner.headers).json()
    assert (before["weekly_points"], before["freezes_remaining"], before["week_start"]) == (
        15,
        0,
        "2026-10-12",
    )
    assert (after["weekly_points"], after["freezes_remaining"], after["week_start"]) == (
        0,
        2,
        "2026-10-19",
    )
    historical = auth_client.get(
        f"/api/v1/groups/{data.group.id}/points?week=2026-10-12", headers=owner.headers
    )
    assert historical.json()["weekly_points"] == 15
    assert db.scalar(select(func.count()).select_from(PointsLedger)) == 1
