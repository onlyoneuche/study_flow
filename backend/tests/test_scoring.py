from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.calendar import lagos_date, monday_of
from app.models import (
    FocusSummary,
    GroupMember,
    GroupStreak,
    PointsLedger,
    Quiz,
    QuizAttempt,
    SessionParticipant,
    StudySession,
)
from app.models.enums import EducationLevel, QuizSource, SessionMode
from app.services.completion import complete, round_half_up
from tests.factories import user
from tests.test_groups import create


def participation(
    db,
    uid,
    now,
    score=11,
    minutes=45,
    mode=SessionMode.SOLO,
    group_id=None,
    subject="chemistry",
    level=EducationLevel.SS2,
    counted=False,
):
    start = now - timedelta(minutes=minutes + 10)
    session = StudySession(
        host_id=uid,
        group_id=group_id,
        mode=mode,
        planned_minutes=minutes,
        scheduled_at=start,
        started_at=start,
        end_at=start + timedelta(minutes=minutes),
        status="ended",
    )
    db.add(session)
    db.flush()
    quiz = Quiz(
        cache_key="a" * 64,
        subject_norm=subject,
        topic_norm="mole concept",
        level=level,
        prompt_version="v1",
        model_name="test",
        source=QuizSource.FALLBACK,
    )
    db.add(quiz)
    db.flush()
    participant = SessionParticipant(
        session_id=session.id,
        user_id=uid,
        subject=subject,
        subject_norm=subject,
        topic="Mole concept",
        topic_norm="mole concept",
        level=level,
        joined_at=start,
        active_seconds=int(minutes * 60 * 0.91),
        last_heartbeat_at=session.end_at,
        status="completed" if counted else "joined",
        is_live_credited=mode == SessionMode.LIVE,
        quiz_status="ready",
        quiz_id=quiz.id,
        session_date=lagos_date(start),
        ended_at=session.end_at,
        completed_at=now if counted else None,
    )
    db.add(participant)
    db.flush()
    attempt = QuizAttempt(
        participant_id=participant.id,
        quiz_id=quiz.id,
        user_id=uid,
        started_at=session.end_at,
        submitted_at=now,
        answers=[0] * 15,
        correct_count=score,
        score_pct=100 * score / 15,
        counts_for_baseline=counted,
    )
    db.add(attempt)
    db.flush()
    return participant, session, attempt


def award(client, pid, now, with_quiz=True):
    async def run():
        async with client.app.state.quizzes.database(write=True) as db:
            p = await db.get(SessionParticipant, pid)
            session = await db.get(StudySession, p.session_id)
            attempt = await db.scalar(select(QuizAttempt).where(QuizAttempt.participant_id == pid))
            await complete(db, session, p, now, attempt if with_quiz else None)
            await db.commit()

    client.portal.call(run)


def components(db, pid, group_id):
    return dict(
        db.execute(
            select(PointsLedger.component, PointsLedger.points).where(
                PointsLedger.participant_id == pid, PointsLedger.group_id == group_id
            )
        ).all()
    )


@pytest.mark.parametrize("mode,total", [(SessionMode.LIVE, 30), (SessionMode.SOLO, 25)])
def test_document_worked_example(auth_client, actor, clock, db_engine, mode, total):
    learner = actor()
    group = create(auth_client, learner)
    with Session(db_engine) as db:
        for days, score in [(3, 8), (2, 9), (1, 10)]:
            participation(
                db, learner.id, clock.now - timedelta(days=days), score=score, counted=True
            )
        p, _, _ = participation(db, learner.id, clock.now, mode=mode, group_id=group["id"])
        p.active_seconds = 41 * 60
        pid = p.id
        db.commit()
    award(auth_client, pid, clock.now)
    with Session(db_engine) as db:
        values = components(db, pid, group["id"])
        assert values["base"] == 15 and values["quiz"] == 7 and values["improvement"] == 3
        assert sum(values.values()) == total and ("group_live" not in values)
        attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.participant_id == pid))
        assert attempt.baseline_pct == pytest.approx(60)
        assert attempt.counts_for_baseline
        latest = db.scalars(
            select(QuizAttempt.score_pct)
            .where(QuizAttempt.counts_for_baseline.is_(True))
            .order_by(QuizAttempt.submitted_at.desc())
            .limit(3)
        ).all()
        assert sum(latest) / 3 == pytest.approx(66.6666667)


@pytest.mark.parametrize(
    "prior_scores,score,improvement,baseline",
    [
        ([], 0, 3, None),
        ([9], 11, 3, 60),
        ([8, 10], 11, 3, 60),
        ([15, 15, 15], 0, 0, 100),
        ([0, 0, 0], 15, 10, 0),
    ],
)
def test_baseline_first_quiz_partial_history_and_clamping(
    auth_client, actor, clock, db_engine, prior_scores, score, improvement, baseline
):
    learner = actor()
    group = create(auth_client, learner)
    with Session(db_engine) as db:
        for index, prior in enumerate(prior_scores):
            participation(
                db,
                learner.id,
                clock.now - timedelta(days=len(prior_scores) - index),
                score=prior,
                counted=True,
            )
        p, _, _ = participation(db, learner.id, clock.now, score=score)
        pid = p.id
        db.commit()
    award(auth_client, pid, clock.now)
    with Session(db_engine) as db:
        assert components(db, pid, group["id"])["improvement"] == improvement
        attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.participant_id == pid))
        assert attempt.baseline_pct == baseline


def test_baseline_uses_only_last_three_same_subject_level_counted_attempts(
    auth_client, actor, clock, db_engine
):
    learner = actor()
    group = create(auth_client, learner)
    with Session(db_engine) as db:
        for days, score in [(5, 0), (4, 0), (3, 8), (2, 9), (1, 10)]:
            participation(
                db, learner.id, clock.now - timedelta(days=days), score=score, counted=True
            )
        participation(
            db,
            learner.id,
            clock.now - timedelta(hours=20),
            score=0,
            counted=True,
            subject="mathematics",
        )
        participation(
            db,
            learner.id,
            clock.now - timedelta(hours=19),
            score=0,
            counted=True,
            level=EducationLevel.SS3,
        )
        participation(db, learner.id, clock.now - timedelta(hours=18), score=0, counted=False)
        p, _, _ = participation(db, learner.id, clock.now)
        pid = p.id
        db.commit()
    award(auth_client, pid, clock.now)
    with Session(db_engine) as db:
        attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.participant_id == pid))
        assert attempt.baseline_pct == pytest.approx(60)
        assert components(db, pid, group["id"])["improvement"] == 3


def test_three_group_credit_live_only_host_and_no_duplicate_awards(
    auth_client, actor, clock, db_engine
):
    learner = actor()
    groups = [create(auth_client, learner) for _ in range(3)]
    with Session(db_engine) as db:
        p, _, _ = participation(
            db, learner.id, clock.now, mode=SessionMode.LIVE, group_id=groups[0]["id"]
        )
        pid = p.id
        db.commit()
    award(auth_client, pid, clock.now)
    award(auth_client, pid, clock.now)
    with Session(db_engine) as db:
        assert sum(components(db, pid, groups[0]["id"]).values()) == 30  # first-quiz I=3
        for g in groups[1:]:
            assert components(db, pid, g["id"]) == {"base": 15, "quiz": 7, "improvement": 3}
        assert db.scalar(select(func.count()).select_from(PointsLedger)) == 10


def test_daily_cap_is_per_user_session_not_group_and_baseline_still_counts(
    auth_client, actor, clock, db_engine
):
    learner = actor()
    groups = [create(auth_client, learner) for _ in range(3)]
    ids = []
    for index in range(4):
        with Session(db_engine) as db:
            p, _, _ = participation(db, learner.id, clock.now + timedelta(minutes=index), score=12)
            ids.append(p.id)
            db.commit()
        award(auth_client, ids[-1], clock.now + timedelta(minutes=index))
    with Session(db_engine) as db:
        for g in groups:
            assert components(db, ids[3], g["id"]) == {"daily_cap": 0}
            assert components(db, ids[2], g["id"]) != {"daily_cap": 0}
        assert db.scalar(
            select(QuizAttempt.counts_for_baseline).where(QuizAttempt.participant_id == ids[3])
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(SessionParticipant)
                .where(SessionParticipant.status == "completed")
            )
            == 4
        )


def test_concurrent_completions_share_the_last_daily_award_slot(
    auth_client, actor, clock, db_engine
):
    learner = actor()
    group = create(auth_client, learner)
    ids = []
    for index in range(4):
        with Session(db_engine) as db:
            p, _, _ = participation(db, learner.id, clock.now + timedelta(seconds=index))
            ids.append(p.id)
            db.commit()
    for pid in ids[:2]:
        award(auth_client, pid, clock.now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda pid: award(auth_client, pid, clock.now), ids[2:]))
    with Session(db_engine) as db:
        capped = sum(components(db, pid, group["id"]) == {"daily_cap": 0} for pid in ids)
        assert capped == 1


def test_time_only_live_fallback_and_lagos_session_day(auth_client, actor, clock, db_engine):
    learner = actor()
    group = create(auth_client, learner)
    clock.now = clock.now.replace(hour=23, minute=15)  # 00:15 Lagos on the next day
    with Session(db_engine) as db:
        p, _, attempt = participation(
            db, learner.id, clock.now, mode=SessionMode.LIVE, group_id=group["id"]
        )
        pid = p.id
        attempt.submitted_at = None
        attempt.score_pct = None
        attempt.correct_count = None
        attempt.answers = None
        db.commit()
    award(auth_client, pid, clock.now, with_quiz=False)
    with Session(db_engine) as db:
        assert components(db, pid, group["id"]) == {"base": 15, "live": 5}
        p = db.get(SessionParticipant, pid)
        assert p.session_date.isoformat() == "2026-10-15"
        rows = db.scalars(select(PointsLedger)).all()
        assert all(
            row.lagos_date == p.session_date and row.week_start == monday_of(p.session_date)
            for row in rows
        )
        assert not db.scalar(select(QuizAttempt.counts_for_baseline))


@pytest.mark.parametrize("minutes,expected", [(25, 8), (45, 15), (60, 20)])
def test_base_points_use_planned_duration_and_round_half_up(minutes, expected):
    assert round_half_up(minutes / 3) == expected
    assert round_half_up(2.5) == 3


def test_points_endpoints_show_improvement_only_and_private_ledger(
    auth_client, actor, clock, db_engine
):
    learner, stranger = actor(), actor()
    group = create(auth_client, learner)
    with Session(db_engine) as db:
        p, _, _ = participation(db, learner.id, clock.now)
        pid = p.id
        db.commit()
    award(auth_client, pid, clock.now)
    response = auth_client.get(f"/api/v1/groups/{group['id']}/points", headers=learner.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["weekly_points"] == 25 and body["target"] == 100 and body["fill_pct"] == 25
    assert body["ranking"][0]["improvement_points"] == 3
    assert body["ranking"][0]["completed_sessions"] == 1
    assert "score_pct" not in response.text and "correct_count" not in response.text
    assert (
        auth_client.get(
            f"/api/v1/groups/{group['id']}/points", headers=stranger.headers
        ).status_code
        == 403
    )
    ledger = auth_client.get("/api/v1/users/me/ledger", headers=learner.headers).json()
    assert {row["component"] for row in ledger["entries"]} == {"base", "quiz", "improvement"}
    assert all(row["group_name"] == "Study Squad" for row in ledger["entries"])
    assert (
        auth_client.get("/api/v1/users/me/ledger", headers=stranger.headers).json()["entries"] == []
    )
    assert auth_client.get("/api/v1/users/me/ledger").status_code == 401
    assert (
        len(
            auth_client.get("/api/v1/users/me/ledger?limit=1", headers=learner.headers).json()[
                "entries"
            ]
        )
        == 1
    )
    assert (
        auth_client.get(
            f"/api/v1/groups/{group['id']}/points?week=2026-10-13", headers=learner.headers
        ).status_code
        == 422
    )
    assert (
        auth_client.get(
            "/api/v1/users/me/ledger?from=2026-10-15&to=2026-10-12", headers=learner.headers
        ).status_code
        == 422
    )


def test_group_leaderboard_uses_average_then_streak_and_audience_band(
    auth_client, actor, clock, db_engine
):
    small_owner, large_owner, tied_owner = actor(), actor(), actor()
    adult_owner = actor(EducationLevel.OTHER)
    small = create(auth_client, small_owner)
    large = create(auth_client, large_owner)
    tied = create(auth_client, tied_owner)
    adult = create(auth_client, adult_owner)
    with Session(db_engine) as db:
        for g, size, uid, points, streak in [
            (small, 3, small_owner.id, 120, 2),
            (large, 8, large_owner.id, 240, 9),
            (tied, 3, tied_owner.id, 120, 5),
            (adult, 3, adult_owner.id, 900, 8),
        ]:
            for _ in range(size - 1):
                member = user(
                    db, level=EducationLevel.OTHER if uid == adult_owner.id else EducationLevel.SS2
                )
                db.add(GroupMember(group_id=g["id"], user_id=member.id, role="member"))
                db.flush()
            p, _, _ = participation(
                db,
                uid,
                clock.now,
                level=EducationLevel.OTHER if uid == adult_owner.id else EducationLevel.SS2,
            )
            db.add(
                PointsLedger(
                    user_id=uid,
                    group_id=g["id"],
                    participant_id=p.id,
                    component="base",
                    points=points,
                    lagos_date=p.session_date,
                    week_start=monday_of(p.session_date),
                )
            )
            db.add(GroupStreak(group_id=g["id"], current=streak, best=streak))
        db.commit()
    response = auth_client.get("/api/v1/leaderboard/groups", headers=small_owner.headers)
    groups = response.json()["groups"]
    assert [row["group_id"] for row in groups] == [tied["id"], small["id"], large["id"]]
    assert [row["points_per_member"] for row in groups] == [40, 40, 30]
    assert "display_name" not in response.text and "score_pct" not in response.text
    assert (
        len(
            auth_client.get("/api/v1/leaderboard/groups", headers=adult_owner.headers).json()[
                "groups"
            ]
        )
        == 1
    )
    assert (
        auth_client.get(
            "/api/v1/leaderboard/groups?week=2026-10-05", headers=small_owner.headers
        ).json()["groups"][0]["weekly_points"]
        == 0
    )


def test_member_ranking_ties_use_completions_and_improvement_adjustments(
    auth_client, actor, clock, db_engine
):
    owner, second = actor(), actor()
    group = create(auth_client, owner)
    with Session(db_engine) as db:
        db.add(GroupMember(group_id=group["id"], user_id=second.id, role="member"))
        db.flush()
        for uid, count in [(owner.id, 1), (second.id, 2)]:
            for index in range(count):
                p, _, _ = participation(db, uid, clock.now - timedelta(minutes=index))
                db.add(
                    PointsLedger(
                        user_id=uid,
                        group_id=group["id"],
                        participant_id=p.id,
                        component="improvement" if index == 0 else "daily_cap",
                        points=6 if index == 0 else 0,
                        lagos_date=p.session_date,
                        week_start=monday_of(p.session_date),
                    )
                )
        db.commit()
    path = f"/api/v1/groups/{group['id']}/points"
    ranked = auth_client.get(path, headers=owner.headers).json()["ranking"]
    assert [row["user_id"] for row in ranked] == [second.id, owner.id]
    with Session(db_engine) as db:
        original = db.scalar(
            select(PointsLedger).where(
                PointsLedger.user_id == second.id, PointsLedger.component == "improvement"
            )
        )
        db.add(
            PointsLedger(
                user_id=second.id,
                group_id=group["id"],
                participant_id=original.participant_id,
                component="adjustment",
                points=-4,
                reverses_id=original.id,
                lagos_date=original.lagos_date,
                week_start=original.week_start,
            )
        )
        db.commit()
    ranked = auth_client.get(path, headers=owner.headers).json()["ranking"]
    assert [row["improvement_points"] for row in ranked] == [6, 2]


def test_focus_data_never_changes_points(auth_client, actor, clock, db_engine):
    learners = [actor(), actor()]
    ids = []
    groups = [create(auth_client, learner) for learner in learners]
    with Session(db_engine) as db:
        for learner, focus in zip(learners, [0, 100], strict=True):
            p, _, _ = participation(db, learner.id, clock.now)
            ids.append(p.id)
            db.add(
                FocusSummary(
                    session_participant_id=p.id,
                    opted_in=True,
                    attentive_pct=focus,
                    away_seconds=0,
                    samples=1500,
                    paused_seconds=0,
                    sample_fps=1,
                    is_valid=True,
                    tracker_version="test-only",
                )
            )
        db.commit()
    for pid in ids:
        award(auth_client, pid, clock.now)
    with Session(db_engine) as db:
        assert components(db, ids[0], groups[0]["id"]) == components(db, ids[1], groups[1]["id"])


def test_daily_cap_resets_by_session_start_lagos_day(auth_client, actor, clock, db_engine):
    learner = actor()
    group = create(auth_client, learner)
    for _ in range(3):
        with Session(db_engine) as db:
            p, _, _ = participation(db, learner.id, clock.now)
            pid = p.id
            db.commit()
        award(auth_client, pid, clock.now)
    next_day = clock.now + timedelta(days=1)
    with Session(db_engine) as db:
        p, _, _ = participation(db, learner.id, next_day)
        pid = p.id
        db.commit()
    award(auth_client, pid, next_day)
    with Session(db_engine) as db:
        assert "daily_cap" not in components(db, pid, group["id"])
        assert components(db, pid, group["id"])["base"] == 15


def test_archived_history_survives_owner_band_change(auth_client, actor, clock, db_engine):
    learner = actor()
    group = create(auth_client, learner)
    with Session(db_engine) as db:
        p, _, _ = participation(db, learner.id, clock.now)
        pid = p.id
        db.commit()
    award(auth_client, pid, clock.now)
    assert (
        auth_client.delete(
            f"/api/v1/groups/{group['id']}/members/{learner.id}", headers=learner.headers
        ).status_code
        == 204
    )
    changed = auth_client.patch(
        "/api/v1/users/me",
        headers=learner.headers,
        json={"level": "OTHER", "adult_confirmation": True},
    )
    assert changed.status_code == 200, changed.text
    history = auth_client.get("/api/v1/users/me/ledger", headers=learner.headers).json()["entries"]
    assert sum(row["points"] for row in history) == 25
    assert auth_client.get("/api/v1/groups", headers=learner.headers).json() == []
    assert (
        auth_client.get("/api/v1/leaderboard/groups", headers=learner.headers).json()["groups"]
        == []
    )
