from enum import StrEnum


class EducationLevel(StrEnum):
    JSS1 = "JSS1"
    JSS2 = "JSS2"
    JSS3 = "JSS3"
    SS1 = "SS1"
    SS2 = "SS2"
    SS3 = "SS3"
    UG_100 = "UG_100"
    UG_200 = "UG_200"
    UG_300 = "UG_300"
    UG_400 = "UG_400"
    UG_500 = "UG_500"
    POSTGRAD = "POSTGRAD"
    OTHER = "OTHER"


class AudienceBand(StrEnum):
    SECONDARY = "secondary"
    TERTIARY = "tertiary"


class AgeBand(StrEnum):
    UNDER_18 = "under_18"
    ADULT = "18_plus"


class MemberRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class SessionMode(StrEnum):
    LIVE = "live"
    SOLO = "solo"


class SessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    ENDED = "ended"
    CANCELLED = "cancelled"


class ParticipantStatus(StrEnum):
    JOINED = "joined"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    LEFT = "left"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"


class QuizStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    UNAVAILABLE = "unavailable"


class QuizSource(StrEnum):
    LLM = "llm"
    FALLBACK = "fallback"


class QuizVariantStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class FlagReason(StrEnum):
    WRONG_ANSWER = "wrong_answer"
    UNCLEAR = "unclear"
    OFF_TOPIC = "off_topic"
    INAPPROPRIATE = "inappropriate"


class PointComponent(StrEnum):
    BASE = "base"
    QUIZ = "quiz"
    IMPROVEMENT = "improvement"
    LIVE = "live"
    GROUP_LIVE = "group_live"
    DAILY_CAP = "daily_cap"
    ADJUSTMENT = "adjustment"


class StreakOutcome(StrEnum):
    KEPT = "kept"
    FROZEN = "frozen"
    BROKEN = "broken"
    PAUSED = "paused"


class FreezeReason(StrEnum):
    AUTO = "auto"


def audience_for_level(level: EducationLevel) -> AudienceBand:
    if level in {
        EducationLevel.JSS1,
        EducationLevel.JSS2,
        EducationLevel.JSS3,
        EducationLevel.SS1,
        EducationLevel.SS2,
        EducationLevel.SS3,
    }:
        return AudienceBand.SECONDARY
    return AudienceBand.TERTIARY
