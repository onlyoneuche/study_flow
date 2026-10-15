from datetime import date, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.db.types import utc_now
from app.models import (
    FocusSummary,
    GroupMember,
    GroupStreak,
    GroupStreakDay,
    Invite,
    PointsLedger,
    QuestionFlag,
    QuizAttempt,
    QuizQuestion,
    SessionParticipant,
    StreakFreeze,
    StudySession,
    User,
)
from app.models.enums import (
    AgeBand,
    AudienceBand,
    EducationLevel,
    MemberRole,
    PointComponent,
    StreakOutcome,
    audience_for_level,
)
from tests.factories import graph, group, user


def rejected(db, operation, message=None):
    with pytest.raises(IntegrityError, match=message), db.begin_nested():
        operation()
        db.flush()


def add_member(db, squad, learner, **overrides):
    row = GroupMember(group_id=squad.id, user_id=learner.id, **overrides)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("level", list(EducationLevel))
def test_every_education_level_has_the_documented_band(level):
    expected = (
        AudienceBand.SECONDARY if level.value.startswith(("JSS", "SS")) else AudienceBand.TERTIARY
    )
    assert audience_for_level(level) == expected


def test_other_requires_recorded_adult_confirmation(db):
    rejected(
        db, lambda: user(db, EducationLevel.OTHER, adult_confirmed_at=None), "adult_confirmation"
    )
    rejected(
        db, lambda: user(db, EducationLevel.OTHER, age_band=AgeBand.UNDER_18), "adult_confirmation"
    )
    adult = user(db, EducationLevel.OTHER)
    squad = group(db, adult)
    assert squad.audience_band == AudienceBand.TERTIARY
    secondary = user(db)
    rejected(db, lambda: add_member(db, squad, secondary), "cross-band")


def test_email_uniqueness_and_enums_are_enforced_in_database(db):
    learner = user(db, email="Ada@example.test")
    rejected(db, lambda: user(db, email="ada@EXAMPLE.test"), "UNIQUE")
    rejected(
        db,
        lambda: db.execute(
            text("UPDATE users SET level = 'INVALID' WHERE id = :id"), {"id": learner.id}
        ),
        "CHECK",
    )
    rejected(
        db,
        lambda: db.execute(
            text("UPDATE users SET age_band = 'unknown' WHERE id = :id"), {"id": learner.id}
        ),
        "CHECK",
    )


def test_membership_history_allows_rejoining_but_not_two_active_rows(db):
    learner = user(db)
    squad = group(db, learner)
    first = add_member(db, squad, learner)
    rejected(db, lambda: add_member(db, squad, learner), "UNIQUE")
    first.left_at = utc_now()
    db.flush()
    second = add_member(db, squad, learner)
    assert first.id != second.id
    rejected(
        db,
        lambda: db.execute(
            update(GroupMember).where(GroupMember.id == first.id).values(left_at=None)
        ),
        "UNIQUE",
    )


def test_group_and_user_membership_limits_apply_to_reactivation(db):
    learner = user(db)
    squads = [group(db, learner) for _ in range(4)]
    for squad in squads[:3]:
        add_member(db, squad, learner)
    rejected(db, lambda: add_member(db, squads[3], learner), "at most 3")
    left = add_member(
        db, squads[3], learner, joined_at=utc_now() - timedelta(days=1), left_at=utc_now()
    )
    rejected(
        db,
        lambda: db.execute(
            update(GroupMember).where(GroupMember.id == left.id).values(left_at=None)
        ),
        "at most 3",
    )
    other = user(db)
    small = group(db, other, max_members=3)
    for _ in range(3):
        add_member(db, small, user(db))
    rejected(db, lambda: add_member(db, small, user(db)), "group is full")


def test_group_band_cannot_be_bypassed_through_profile_or_group_updates(db):
    learner = user(db)
    squad = group(db, learner)
    add_member(db, squad, learner, role=MemberRole.OWNER)
    rejected(
        db,
        lambda: db.execute(
            update(User).where(User.id == learner.id).values(level=EducationLevel.UG_100)
        ),
        "cross-band",
    )
    rejected(db, lambda: group(db, learner, audience_band=AudienceBand.TERTIARY), "audience band")
    adult = user(db, EducationLevel.OTHER)
    rejected(
        db,
        lambda: db.execute(
            text("UPDATE groups SET owner_id = :owner WHERE id = :id"),
            {"owner": adult.id, "id": squad.id},
        ),
        "audience band",
    )


def test_foreign_keys_protect_history(db):
    learner = user(db)
    group(db, learner)
    rejected(
        db,
        lambda: db.execute(text("DELETE FROM users WHERE id = :id"), {"id": learner.id}),
        "FOREIGN KEY",
    )


def test_invite_code_expiry_and_usage_constraints(db):
    learner = user(db)
    squad = group(db, learner)

    def invite(**changes):
        values = dict(group_id=squad.id, created_by=learner.id, code="abcd1234", max_uses=7)
        values.update(changes)
        row = Invite(**values)
        db.add(row)
        db.flush()
        return row

    invitation = invite()
    assert 604799 <= (invitation.expires_at - invitation.created_at).total_seconds() <= 604801
    rejected(db, invite, "UNIQUE")
    rejected(db, lambda: invite(code="short"), "code_length")
    rejected(db, lambda: invite(code="abcdefgh", uses=8), "use_limits")
    rejected(db, lambda: invite(code="abcdefgh", max_uses=0), "use_limits")
    rejected(
        db, lambda: invite(code="abcdefgh", expires_at=utc_now() - timedelta(days=1)), "expiry"
    )


@pytest.mark.parametrize("minutes", [25, 45, 60])
def test_only_documented_session_durations(db, minutes):
    learner = user(db)
    db.add(StudySession(host_id=learner.id, mode="solo", planned_minutes=minutes))
    db.flush()
    rejected(
        db, lambda: db.execute(text("UPDATE sessions SET planned_minutes = 30")), "planned_duration"
    )
    rejected(
        db, lambda: db.execute(text("UPDATE sessions SET mode = 'live'")), "live_requires_group"
    )


def test_participant_snapshot_and_attempt_are_unique(db):
    data = graph(db)
    rejected(
        db,
        lambda: db.add(
            SessionParticipant(
                session_id=data.session.id,
                user_id=data.user.id,
                subject="Physics",
                subject_norm="physics",
                topic="Motion",
                topic_norm="motion",
                level="SS2",
                session_date=date(2026, 10, 15),
            )
        ),
        "UNIQUE",
    )
    # Creating the attempt starts its timer; results are populated only on submission.
    attempt = QuizAttempt(
        participant_id=data.participant.id, quiz_id=data.quiz.id, user_id=data.user.id
    )
    db.add(attempt)
    db.flush()
    assert attempt.submitted_at is None and attempt.score_pct is None
    rejected(
        db,
        lambda: db.add(
            QuizAttempt(
                participant_id=data.participant.id, quiz_id=data.quiz.id, user_id=data.user.id
            )
        ),
        "UNIQUE",
    )
    rejected(
        db,
        lambda: db.execute(update(QuizAttempt).values(counts_for_baseline=True)),
        "baseline_requires_submission",
    )
    rejected(
        db,
        lambda: db.execute(update(QuizAttempt).values(submitted_at=utc_now())),
        "submitted_attempt_has_results",
    )
    data.user.level = EducationLevel.SS3
    db.flush()
    assert data.participant.level == EducationLevel.SS2


def test_question_shape_and_distinct_flaggers(db):
    data = graph(db)
    question = QuizQuestion(
        quiz_id=data.quiz.id,
        position=0,
        question="What is a mole?",
        options=["A", "B", "C", "D"],
        correct_index=2,
        explanation="An amount of substance.",
        difficulty="easy",
    )
    db.add(question)
    db.flush()
    rejected(
        db, lambda: db.execute(update(QuizQuestion).values(options=["A", "B"])), "four_options"
    )
    rejected(db, lambda: db.execute(update(QuizQuestion).values(correct_index=4)), "correct_index")
    db.add(QuestionFlag(question_id=question.id, user_id=data.user.id, reason="unclear"))
    db.flush()
    rejected(
        db,
        lambda: db.add(
            QuestionFlag(question_id=question.id, user_id=data.user.id, reason="off_topic")
        ),
        "UNIQUE",
    )


def test_ledger_allows_only_appended_awards_and_corrections(db):
    data = graph(db)

    def award(**changes):
        values = dict(
            user_id=data.user.id,
            group_id=data.group.id,
            participant_id=data.participant.id,
            component=PointComponent.BASE,
            points=15,
            lagos_date=date(2026, 10, 15),
            week_start=date(2026, 10, 12),
        )
        values.update(changes)
        row = PointsLedger(**values)
        db.add(row)
        db.flush()
        return row

    original = award()
    rejected(db, lambda: db.execute(text("UPDATE points_ledger SET points = 999")), "append-only")
    rejected(db, lambda: db.execute(text("DELETE FROM points_ledger")), "append-only")
    rejected(db, award, "already exists")
    rejected(
        db,
        lambda: db.execute(
            text("INSERT OR REPLACE INTO points_ledger SELECT * FROM points_ledger")
        ),
        "already exists",
    )
    correction = award(component=PointComponent.ADJUSTMENT, points=-15, reverses_id=original.id)
    assert correction.reverses_id == original.id
    assert db.scalar(select(PointsLedger.points).where(PointsLedger.id == original.id)) == 15
    rejected(db, lambda: award(component=PointComponent.QUIZ, points=-1), "negative_only")
    rejected(db, lambda: award(component=PointComponent.DAILY_CAP, points=1), "daily_cap_zero")
    rejected(db, lambda: award(component=PointComponent.QUIZ, points=1.5), "integer_points")
    rejected(
        db,
        lambda: award(component=PointComponent.QUIZ, week_start=date(2026, 10, 13)),
        "lagos_week",
    )


def test_streak_days_and_freezes_are_idempotent_with_two_per_week(db):
    squad = group(db)
    streak = GroupStreak(group_id=squad.id, current=5, best=5)
    db.add(streak)
    db.flush()
    day = date(2026, 10, 15)

    def record():
        db.add(
            GroupStreakDay(
                group_id=squad.id,
                date=day,
                outcome=StreakOutcome.PAUSED,
                completed_count=1,
                eligible_count=2,
            )
        )

    record()
    db.flush()
    streak.last_evaluated_date = day
    db.flush()
    assert streak.current == 5 and streak.last_evaluated_date == day
    rejected(db, record, "UNIQUE")
    for offset in range(2):
        db.add(
            StreakFreeze(
                group_id=squad.id, date=day + timedelta(days=offset), week_start=date(2026, 10, 12)
            )
        )
        db.flush()
    rejected(
        db,
        lambda: db.add(
            StreakFreeze(
                group_id=squad.id, date=day + timedelta(days=2), week_start=date(2026, 10, 12)
            )
        ),
        "at most 2 freezes",
    )
    db.add(StreakFreeze(group_id=squad.id, date=date(2026, 10, 19), week_start=date(2026, 10, 19)))
    db.flush()


def test_focus_opt_out_has_no_metrics_and_no_points_dependency(db):
    data = graph(db)
    focus = FocusSummary(session_participant_id=data.participant.id, tracker_version="mp/v1")
    db.add(focus)
    db.flush()
    rejected(
        db,
        lambda: db.execute(update(FocusSummary).values(attentive_pct=90)),
        "opt_out_has_no_metrics",
    )
    rejected(
        db,
        lambda: db.execute(update(FocusSummary).values(opted_in=True, is_valid=True)),
        "valid_has_metrics",
    )
    rejected(
        db,
        lambda: db.add(
            FocusSummary(session_participant_id=data.participant.id, tracker_version="mp/v1")
        ),
        "UNIQUE",
    )
    db.execute(
        update(FocusSummary).values(
            opted_in=True,
            attentive_pct=90,
            samples=1500,
            sample_fps=1,
            away_seconds=20,
            is_valid=True,
        )
    )
    assert db.scalar(select(PointsLedger.id)) is None
    rejected(
        db, lambda: db.execute(update(FocusSummary).values(attentive_pct=101)), "attention_range"
    )
