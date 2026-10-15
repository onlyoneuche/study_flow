from datetime import date, datetime

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import func, select

from app.core.calendar import lagos_date, latest_evaluable_day
from app.demo.seed import PASSWORD, banks, email, seed_demo
from app.models import (
    DemoSeedRun,
    FocusSummary,
    Group,
    GroupMember,
    GroupStreakDay,
    Invite,
    PointsLedger,
    QuizAttempt,
    QuizQuestion,
    SessionParticipant,
    StreakFreeze,
    StudySession,
    User,
)
from app.models.enums import ParticipantStatus, SessionMode


def seed(client, clock):
    return client.portal.call(seed_demo, client.app.state.database, clock.now)


def test_seed_replays_history_streak_points_and_ready_quiz(auth_client, clock, db):
    summary = seed(auth_client, clock)
    assert (
        summary["weekly_points"],
        summary["weekly_target"],
        summary["streak"],
        summary["freezes_remaining"],
    ) == (340, 600, 12, 1)
    focus_rows = db.scalars(select(FocusSummary)).all()
    assert len(focus_rows) == 3 and all(row.is_valid and row.opted_in for row in focus_rows)
    focus_participants = [
        db.get(SessionParticipant, row.session_participant_id) for row in focus_rows
    ]
    assert {p.session_id for p in focus_participants} == {summary["focus_session_id"]}
    assert db.get(StudySession, summary["focus_session_id"]).mode == "live"
    assert summary["focus_participant_id"] in {p.id for p in focus_participants}
    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    assert len(users) == 9
    assert {u.level for u in users} == {"SS2"}
    ada = next(u for u in users if u.display_name == "Ada")
    assert ada.email == email("Ada")
    assert PasswordHelper().verify_and_update(PASSWORD, ada.hashed_password)[0]
    assert ada.guardian_consent_at and ada.is_verified
    days = db.scalars(
        select(GroupStreakDay).where(GroupStreakDay.group_id == summary["group_id"])
    ).all()
    assert len(days) == 13
    assert sum(d.outcome == "kept" for d in days) == 12
    assert sum(d.outcome == "frozen" for d in days) == 1
    assert db.scalar(select(func.count()).select_from(StreakFreeze)) == 1
    assert set(db.scalars(select(StudySession.mode))) == {SessionMode.LIVE, SessionMode.SOLO}
    assert (
        db.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.submitted_at.is_not(None))
        )
        == 12
    )
    p = db.get(SessionParticipant, summary["quiz_participant_id"])
    assert (p.status, p.active_seconds, p.quiz_status) == ("joined", 1500, "ready")
    assert p.completed_at is None
    attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.participant_id == p.id))
    assert attempt.started_at == clock.now and attempt.submitted_at is None
    live = db.get(StudySession, summary["session_id"])
    assert live.status == "scheduled" and live.started_at > clock.now
    assert lagos_date(live.started_at) == lagos_date(clock.now)
    completed = db.scalars(
        select(SessionParticipant).where(SessionParticipant.status == ParticipantStatus.COMPLETED)
    ).all()
    assert all(p.active_seconds >= 1200 for p in completed)
    assert len(banks()) == 6


def test_rerun_archives_only_owned_data_and_keeps_immutable_ledger(auth_client, clock, db):
    from tests.factories import graph

    real = graph(db)
    db.add(
        PointsLedger(
            user_id=real.user.id,
            group_id=real.group.id,
            participant_id=real.participant.id,
            component="base",
            points=15,
            lagos_date=real.participant.session_date,
            week_start=date(2026, 10, 12),
        )
    )
    db.commit()
    before = (
        real.user.email,
        real.user.hashed_password,
        real.user.is_active,
        real.group.name,
        real.group.is_active,
    )
    first = seed(auth_client, clock)
    old_ada = db.scalar(select(User).where(User.email == email("Ada")))
    old_ledger = list(db.execute(select(PointsLedger.id, PointsLedger.points)))
    old_invites = list(db.scalars(select(Invite).where(Invite.group_id == first["group_id"])))
    second = seed(auth_client, clock)
    db.rollback()  # End the old WAL read snapshot before checking the reset.
    assert before == (
        real.user.email,
        real.user.hashed_password,
        real.user.is_active,
        real.group.name,
        real.group.is_active,
    )
    assert old_ada.is_active is False and old_ada.email.startswith("archived-")
    assert db.get(Group, first["group_id"]).is_active is False
    assert all(i.revoked_at for i in old_invites)
    assert all(db.get(PointsLedger, lid).points == points for lid, points in old_ledger)
    assert db.get(StudySession, first["session_id"]).status == "cancelled"
    assert first["group_id"] != second["group_id"]
    assert second["weekly_points"] == 340 and second["streak"] == 12
    assert (
        db.scalar(
            select(func.count()).select_from(DemoSeedRun).where(DemoSeedRun.is_active.is_(True))
        )
        == 1
    )
    assert db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) == 10


def test_email_collision_does_not_claim_a_non_demo_user(auth_client, clock, db):
    from tests.factories import user

    real = user(db, email=email("Ada"))
    db.commit()
    with pytest.raises(RuntimeError, match="non-demo account"):
        seed(auth_client, clock)
    db.expire_all()
    assert real.is_active and real.email == email("Ada")
    assert db.scalar(select(func.count()).select_from(DemoSeedRun)) == 0
    assert db.scalar(select(func.count()).select_from(Group)) == 0


@pytest.mark.parametrize("mixed", ["member", "owner", "other_group"])
def test_mixed_real_membership_blocks_reset_without_changes(auth_client, clock, db, mixed):
    from tests.factories import group, user

    summary = seed(auth_client, clock)
    run = db.scalar(select(DemoSeedRun).where(DemoSeedRun.is_active.is_(True)))
    real = user(db)
    if mixed == "member":
        db.add(GroupMember(group_id=summary["group_id"], user_id=real.id))
    elif mixed == "owner":
        db.get(Group, summary["group_id"]).owner_id = real.id
    else:
        g = group(db, real)
        db.add(GroupMember(group_id=g.id, user_id=run.user_ids[0]))
    db.commit()
    with pytest.raises(RuntimeError, match="non-demo"):
        seed(auth_client, clock)
    db.expire_all()
    assert run.is_active and run.archived_at is None
    assert db.get(Group, summary["group_id"]).is_active
    assert db.scalar(select(User).where(User.email == email("Ada"))).is_active
    assert real.is_active
    assert db.scalar(select(func.count()).select_from(DemoSeedRun)) == 1


def test_interrupted_reset_rolls_back_archiving_and_new_users(auth_client, clock, db, monkeypatch):
    summary = seed(auth_client, clock)
    before_users = list(
        db.execute(select(User.id, User.email, User.is_active, User.hashed_password))
    )
    before_points = list(db.execute(select(PointsLedger.id, PointsLedger.points)))

    async def interrupted(*args, **kwargs):
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr("app.demo.seed.replay", interrupted)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        seed(auth_client, clock)
    db.expire_all()
    assert (
        list(db.execute(select(User.id, User.email, User.is_active, User.hashed_password)))
        == before_users
    )
    assert list(db.execute(select(PointsLedger.id, PointsLedger.points))) == before_points
    assert db.get(Group, summary["group_id"]).is_active
    assert db.scalar(select(func.count()).select_from(DemoSeedRun)) == 1


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-10-19T01:59:00+01:00",
        "2026-10-19T02:00:00+01:00",
        "2026-10-18T20:00:00+01:00",
        "2027-01-01T20:00:00+01:00",
    ],
)
def test_seed_obeys_due_days_weeks_and_never_finalises_today(auth_client, clock, db, stamp):
    clock.now = datetime.fromisoformat(stamp)
    summary = seed(auth_client, clock)
    assert summary["streak"] == 12
    assert db.scalar(select(func.max(GroupStreakDay.date))) == latest_evaluable_day(clock.now)
    assert summary["weekly_target"] == 600
    assert summary["freezes_remaining"] in (1, 2)
    for p in db.scalars(
        select(SessionParticipant).where(SessionParticipant.completed_at.is_not(None))
    ):
        assert p.session_date <= lagos_date(clock.now)
        assert p.completed_at <= clock.now


def test_seed_refuses_running_backend_lock(auth_client, clock, db_path, db):
    from app.services.jobs import SingleInstanceLock

    lock = SingleInstanceLock(db_path)
    lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="Another StudyFlow instance"):
            seed(auth_client, clock)
    finally:
        lock.release()
    assert db.scalar(select(func.count()).select_from(DemoSeedRun)) == 0


def test_demo_sign_in_quiz_submission_and_rankings_use_real_routes(auth_client, clock, db):
    summary = seed(auth_client, clock)
    response = auth_client.post(
        "/api/v1/auth/jwt/login", data={"username": email("Ada"), "password": PASSWORD}
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    dashboard = auth_client.get("/api/v1/users/me/dashboard", headers=headers).json()
    assert dashboard["groups"][0]["weekly_points"] == 340
    pid = summary["quiz_participant_id"]
    quiz = auth_client.get(f"/api/v1/participants/{pid}/quiz", headers=headers)
    assert quiz.status_code == 200 and quiz.json()["status"] == "ready"
    assert "correct_index" not in quiz.text
    p = db.get(SessionParticipant, pid)
    answers = list(
        db.scalars(
            select(QuizQuestion.correct_index)
            .where(QuizQuestion.quiz_id == p.quiz_id)
            .order_by(QuizQuestion.position)
        )
    )
    result = auth_client.post(
        f"/api/v1/participants/{pid}/quiz/submit", headers=headers, json={"answers": answers}
    )
    assert result.status_code == 200
    assert result.json()["correct_count"] == 15
    group = auth_client.get(f"/api/v1/groups/{summary['group_id']}", headers=headers).json()
    assert group["weekly_points"] == 365
    assert group["streak"] == 12  # The next streak evaluation is still at 02:00.
    ranks = auth_client.get("/api/v1/leaderboard/groups", headers=headers).json()["groups"]
    assert ranks[0]["name"] == "Lagos Brainiacs"
    assert "score_pct" not in str(ranks)


def test_historical_quizzes_preserve_non_demo_cache_and_flags(auth_client, clock, db):
    from app.core.study import cache_key, normalise, normalise_subject
    from app.models import QuestionFlag, Quiz
    from app.quizzes.schema import QuizDocument
    from app.quizzes.worker import Job, questions_for, store_quiz
    from tests.factories import user

    real = user(db)
    db.commit()
    uid = real.id

    async def existing_cache():
        async with auth_client.app.state.database.session_factory() as session:
            entry = banks()["Chemistry"]
            subject, topic = normalise_subject(entry["subject"]), normalise(entry["topic"])
            job = Job(
                cache_key(subject, topic, "SS2"),
                entry["subject"],
                entry["topic"],
                subject,
                topic,
                "SS2",
            )
            document = QuizDocument.model_validate({"questions": entry["questions"]})
            quizzes = [await store_quiz(session, job, document, "non-demo-model") for _ in range(5)]
            question = (await questions_for(session, quizzes[0].id))[0]
            session.add(QuestionFlag(question_id=question.id, user_id=uid, reason="unclear"))
            question.flag_count = 1
            await session.commit()
            return [q.id for q in quizzes], question.id

    qids, question_id = auth_client.portal.call(existing_cache)
    db.rollback()
    seed(auth_client, clock)
    db.rollback()
    assert {q.status for q in db.scalars(select(Quiz).where(Quiz.id.in_(qids)))} == {"active"}
    assert db.get(QuizQuestion, question_id).flag_count == 1
    assert db.scalar(select(func.count()).select_from(QuestionFlag)) == 1
    assert db.get(User, uid).is_active
