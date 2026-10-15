from datetime import date
from itertools import count
from types import SimpleNamespace

from app.db.types import utc_now
from app.models import Group, Quiz, SessionParticipant, StudySession, User
from app.models.enums import AgeBand, EducationLevel, QuizSource, SessionMode, audience_for_level

sequence = count()


def user(db, level=EducationLevel.SS2, **overrides):
    fields = dict(
        email=f"student-{next(sequence)}@example.com",
        display_name="Ada",
        hashed_password="test-hash",
        level=level,
        age_band=AgeBand.ADULT if level == EducationLevel.OTHER else AgeBand.UNDER_18,
        adult_confirmed_at=utc_now() if level == EducationLevel.OTHER else None,
        guardian_consent_at=utc_now(),
    )
    fields.update(overrides)
    row = User(**fields)
    db.add(row)
    db.flush()
    return row


def group(db, owner=None, **overrides):
    owner = owner or user(db)
    fields = dict(
        name="Study Squad", owner_id=owner.id, audience_band=audience_for_level(owner.level)
    )
    fields.update(overrides)
    row = Group(**fields)
    db.add(row)
    db.flush()
    return row


def graph(db):
    learner = user(db)
    squad = group(db, learner)
    session = StudySession(host_id=learner.id, mode=SessionMode.SOLO, planned_minutes=45)
    quiz = Quiz(
        cache_key="a" * 64,
        subject_norm="chemistry",
        topic_norm="mole concept",
        level=learner.level,
        prompt_version="v1",
        model_name="qwen2.5:7b-instruct",
        source=QuizSource.LLM,
    )
    db.add_all([session, quiz])
    db.flush()
    participant = SessionParticipant(
        session_id=session.id,
        user_id=learner.id,
        subject="Chemistry",
        subject_norm="chemistry",
        topic="Mole concept",
        topic_norm="mole concept",
        level=learner.level,
        session_date=date(2026, 10, 15),
        quiz_id=quiz.id,
    )
    db.add(participant)
    db.flush()
    return SimpleNamespace(
        user=learner, group=squad, session=session, quiz=quiz, participant=participant
    )
