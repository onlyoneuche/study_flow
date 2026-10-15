from datetime import date, datetime, timedelta

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record
from app.db.types import UTCDateTime, utc_now
from app.models.enums import (
    AgeBand,
    AudienceBand,
    Difficulty,
    EducationLevel,
    FlagReason,
    FreezeReason,
    MemberRole,
    ParticipantStatus,
    PointComponent,
    QuizSource,
    QuizStatus,
    QuizVariantStatus,
    SessionMode,
    SessionStatus,
    StreakOutcome,
)


def enum_type(enum):
    return Enum(
        enum,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
        name=enum.__name__.lower(),
    )


class User(SQLAlchemyBaseUserTable[int], Record, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(display_name)) > 0", name="display_name_not_blank"),
        CheckConstraint(
            "level != 'OTHER' OR (age_band = '18_plus' AND adult_confirmed_at IS NOT NULL)",
            name="other_requires_adult_confirmation",
        ),
    )

    # Match the case-insensitive lookup used by the fastapi-users adapter.
    email: Mapped[str] = mapped_column(String(320, collation="NOCASE"), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    level: Mapped[EducationLevel] = mapped_column(enum_type(EducationLevel))
    age_band: Mapped[AgeBand] = mapped_column(enum_type(AgeBand))
    guardian_consent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    adult_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class DemoSeedRun(Record, Base):
    """Explicit ownership for the local fixture; email/name matching never grants ownership."""

    __tablename__ = "demo_seed_runs"
    __table_args__ = (
        Index("uq_demo_seed_active", "is_active", unique=True, sqlite_where=text("is_active = 1")),
    )

    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("1"))
    user_ids: Mapped[list[int]] = mapped_column(JSON)
    group_ids: Mapped[list[int]] = mapped_column(JSON)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Group(Record, Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("max_members BETWEEN 3 AND 8", name="member_limit"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
    )

    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    audience_band: Mapped[AudienceBand] = mapped_column(enum_type(AudienceBand))
    max_members: Mapped[int] = mapped_column(default=8, server_default="8")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("1"))


class GroupMember(Record, Base):
    __tablename__ = "group_members"
    __table_args__ = (
        Index(
            "uq_group_members_active",
            "group_id",
            "user_id",
            unique=True,
            sqlite_where=text("left_at IS NULL"),
        ),
        CheckConstraint("left_at IS NULL OR left_at >= joined_at", name="membership_dates"),
        Index("ix_group_members_user_active", "user_id", "left_at"),
    )

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[MemberRole] = mapped_column(enum_type(MemberRole), default=MemberRole.MEMBER)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    removed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Invite(Record, Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint("length(code) = 8", name="code_length"),
        CheckConstraint("uses >= 0 AND max_uses > 0 AND uses <= max_uses", name="use_limits"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
    )

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: utc_now() + timedelta(days=7)
    )
    max_uses: Mapped[int]
    uses: Mapped[int] = mapped_column(default=0, server_default="0")
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class StudySession(Record, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("planned_minutes IN (25, 45, 60)", name="planned_duration"),
        CheckConstraint("mode != 'live' OR group_id IS NOT NULL", name="live_requires_group"),
        CheckConstraint(
            "end_at IS NULL OR started_at IS NULL OR end_at >= started_at", name="session_dates"
        ),
    )

    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), index=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[SessionMode] = mapped_column(enum_type(SessionMode))
    planned_minutes: Mapped[int]
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[SessionStatus] = mapped_column(
        enum_type(SessionStatus), default=SessionStatus.SCHEDULED
    )


class Quiz(Record, Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        CheckConstraint("length(cache_key) = 64", name="cache_key_length"),
        Index("ix_quizzes_related_topic", "subject_norm", "level", "status"),
    )

    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    subject_norm: Mapped[str] = mapped_column(String(200))
    topic_norm: Mapped[str] = mapped_column(String(300))
    level: Mapped[EducationLevel] = mapped_column(enum_type(EducationLevel))
    prompt_version: Mapped[str] = mapped_column(String(30))
    model_name: Mapped[str] = mapped_column(String(200))
    source: Mapped[QuizSource] = mapped_column(enum_type(QuizSource))
    status: Mapped[QuizVariantStatus] = mapped_column(
        enum_type(QuizVariantStatus), default=QuizVariantStatus.ACTIVE
    )


class SessionParticipant(Record, Base):
    __tablename__ = "session_participants"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id"),
        CheckConstraint("active_seconds >= 0 AND late_minutes >= 0", name="time_nonnegative"),
        Index("ix_session_participants_user_day_status", "user_id", "session_date", "status"),
        Index("ix_session_participants_baseline", "user_id", "subject_norm", "level"),
    )

    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String(200))
    subject_norm: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(300))
    topic_norm: Mapped[str] = mapped_column(String(300))
    level: Mapped[EducationLevel] = mapped_column(enum_type(EducationLevel))
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    late_minutes: Mapped[float] = mapped_column(default=0, server_default="0")
    active_seconds: Mapped[int] = mapped_column(default=0, server_default="0")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[ParticipantStatus] = mapped_column(
        enum_type(ParticipantStatus), default=ParticipantStatus.JOINED
    )
    is_live_credited: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    quiz_status: Mapped[QuizStatus] = mapped_column(
        enum_type(QuizStatus), default=QuizStatus.PENDING
    )
    quiz_id: Mapped[int | None] = mapped_column(ForeignKey("quizzes.id"))
    session_date: Mapped[date]
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class QuizQuestion(Record, Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        UniqueConstraint("quiz_id", "position"),
        CheckConstraint("position BETWEEN 0 AND 14", name="position_range"),
        CheckConstraint("length(question) BETWEEN 10 AND 300", name="question_length"),
        CheckConstraint(
            "json_type(options) = 'array' AND json_array_length(options) = 4", name="four_options"
        ),
        CheckConstraint("correct_index BETWEEN 0 AND 3", name="correct_index_range"),
        CheckConstraint("length(explanation) <= 200", name="explanation_length"),
        CheckConstraint("flag_count >= 0", name="flag_count_nonnegative"),
    )

    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    position: Mapped[int]
    question: Mapped[str] = mapped_column(String(300))
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_index: Mapped[int]
    explanation: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[Difficulty] = mapped_column(enum_type(Difficulty))
    is_disabled: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    flag_count: Mapped[int] = mapped_column(default=0, server_default="0")


class QuizAttempt(Record, Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        CheckConstraint(
            "correct_count IS NULL OR correct_count BETWEEN 0 AND 15", name="correct_count_range"
        ),
        CheckConstraint("score_pct IS NULL OR score_pct BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint(
            "baseline_pct IS NULL OR baseline_pct BETWEEN 0 AND 100", name="baseline_range"
        ),
        CheckConstraint(
            "answers IS NULL OR (json_type(answers) = 'array' AND json_array_length(answers) = 15)",
            name="fifteen_answers",
        ),
        CheckConstraint("submitted_at IS NULL OR submitted_at >= started_at", name="attempt_dates"),
        CheckConstraint(
            "submitted_at IS NULL OR (answers IS NOT NULL "
            "AND correct_count IS NOT NULL AND score_pct IS NOT NULL)",
            name="submitted_attempt_has_results",
        ),
        CheckConstraint(
            "counts_for_baseline = 0 OR submitted_at IS NOT NULL",
            name="baseline_requires_submission",
        ),
        Index("ix_quiz_attempts_user_quiz", "user_id", "quiz_id"),
    )

    participant_id: Mapped[int] = mapped_column(ForeignKey("session_participants.id"), unique=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    answers: Mapped[list[int] | None] = mapped_column(JSON(none_as_null=True))
    correct_count: Mapped[int | None]
    score_pct: Mapped[float | None]
    baseline_pct: Mapped[float | None]
    counts_for_baseline: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class QuestionFlag(Record, Base):
    __tablename__ = "question_flags"
    __table_args__ = (
        UniqueConstraint("question_id", "user_id"),
        CheckConstraint("note IS NULL OR length(note) <= 200", name="note_length"),
    )

    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[FlagReason] = mapped_column(enum_type(FlagReason))
    note: Mapped[str | None] = mapped_column(String(200))


class PointsLedger(Record, Base):
    __tablename__ = "points_ledger"
    __table_args__ = (
        CheckConstraint("typeof(points) = 'integer'", name="integer_points"),
        CheckConstraint("component = 'adjustment' OR points >= 0", name="negative_only_adjustment"),
        CheckConstraint("component != 'daily_cap' OR points = 0", name="daily_cap_zero"),
        CheckConstraint(
            "reverses_id IS NULL OR component = 'adjustment'", name="reversal_component"
        ),
        CheckConstraint("reverses_id IS NULL OR reverses_id != id", name="no_self_reversal"),
        CheckConstraint(
            "strftime('%w', week_start) = '1' AND lagos_date >= week_start "
            "AND lagos_date < date(week_start, '+7 days')",
            name="lagos_week",
        ),
        Index("ix_points_ledger_group_week", "group_id", "week_start"),
        Index("ix_points_ledger_user_day", "user_id", "lagos_date"),
        Index(
            "uq_points_ledger_award",
            "participant_id",
            "group_id",
            "component",
            unique=True,
            sqlite_where=text("component != 'adjustment'"),
        ),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("session_participants.id"))
    component: Mapped[PointComponent] = mapped_column(enum_type(PointComponent))
    points: Mapped[int]
    lagos_date: Mapped[date]
    week_start: Mapped[date]
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("points_ledger.id"))


class GroupStreak(Record, Base):
    __tablename__ = "group_streaks"
    __table_args__ = (CheckConstraint("current >= 0 AND best >= current", name="streak_range"),)

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), unique=True)
    current: Mapped[int] = mapped_column(default=0, server_default="0")
    best: Mapped[int] = mapped_column(default=0, server_default="0")
    last_evaluated_date: Mapped[date | None]


class GroupStreakDay(Record, Base):
    __tablename__ = "group_streak_days"
    __table_args__ = (
        UniqueConstraint("group_id", "date"),
        CheckConstraint(
            "completed_count >= 0 AND eligible_count >= completed_count", name="member_counts"
        ),
    )

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    date: Mapped[date]
    outcome: Mapped[StreakOutcome] = mapped_column(enum_type(StreakOutcome))
    completed_count: Mapped[int]
    eligible_count: Mapped[int]


class StreakFreeze(Record, Base):
    __tablename__ = "streak_freezes"
    __table_args__ = (
        UniqueConstraint("group_id", "date"),
        CheckConstraint(
            "strftime('%w', week_start) = '1' AND date >= week_start "
            "AND date < date(week_start, '+7 days')",
            name="lagos_week",
        ),
        Index("ix_streak_freezes_group_week", "group_id", "week_start"),
    )

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    date: Mapped[date]
    week_start: Mapped[date]
    reason: Mapped[FreezeReason] = mapped_column(enum_type(FreezeReason), default=FreezeReason.AUTO)


class FocusSummary(Record, Base):
    __tablename__ = "focus_summaries"
    __table_args__ = (
        CheckConstraint(
            "attentive_pct IS NULL OR attentive_pct BETWEEN 0 AND 100", name="attention_range"
        ),
        CheckConstraint("away_seconds IS NULL OR away_seconds >= 0", name="away_nonnegative"),
        CheckConstraint("samples IS NULL OR samples >= 0", name="samples_nonnegative"),
        CheckConstraint("paused_seconds IS NULL OR paused_seconds >= 0", name="paused_nonnegative"),
        CheckConstraint("sample_fps IS NULL OR sample_fps IN (0.5, 1, 2)", name="sample_rate"),
        CheckConstraint(
            "opted_in = 1 OR (attentive_pct IS NULL AND away_seconds IS NULL "
            "AND samples IS NULL AND paused_seconds IS NULL "
            "AND sample_fps IS NULL AND is_valid = 0)",
            name="opt_out_has_no_metrics",
        ),
        CheckConstraint(
            "is_valid = 0 OR (opted_in = 1 AND attentive_pct IS NOT NULL "
            "AND away_seconds IS NOT NULL AND samples IS NOT NULL "
            "AND samples >= 60 AND sample_fps IS NOT NULL)",
            name="valid_has_metrics",
        ),
    )

    session_participant_id: Mapped[int] = mapped_column(
        ForeignKey("session_participants.id"), unique=True
    )
    opted_in: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    attentive_pct: Mapped[int | None]
    away_seconds: Mapped[int | None]
    samples: Mapped[int | None]
    paused_seconds: Mapped[int | None]
    sample_fps: Mapped[float | None]
    is_valid: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    tracker_version: Mapped[str] = mapped_column(String(100))
