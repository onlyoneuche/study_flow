"""Import every model here so Alembic sees the complete metadata."""

from app.models.entities import (
    FocusSummary,
    Group,
    GroupMember,
    GroupStreak,
    GroupStreakDay,
    Invite,
    PointsLedger,
    QuestionFlag,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    SessionParticipant,
    StreakFreeze,
    StudySession,
    User,
)

__all__ = [
    "FocusSummary",
    "Group",
    "GroupMember",
    "GroupStreak",
    "GroupStreakDay",
    "Invite",
    "PointsLedger",
    "QuestionFlag",
    "Quiz",
    "QuizAttempt",
    "QuizQuestion",
    "SessionParticipant",
    "StreakFreeze",
    "StudySession",
    "User",
]
