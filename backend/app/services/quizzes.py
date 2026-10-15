"""Shared grading for HTTP submission and historical demo replay."""

from app.models.enums import ParticipantStatus
from app.quizzes.worker import questions_for
from app.services.completion import complete, deadline
from app.services.groups import fail


async def submit_attempt(db, session, participant, attempt, answers, now):
    if not attempt:
        fail("not_started", "Open the quiz before submitting your answers.")
    if attempt.submitted_at:
        if attempt.answers != answers:
            fail(
                "already_submitted",
                "This quiz has already been submitted. Answers cannot be changed.",
            )
        return
    if not participant.ended_at or participant.status == ParticipantStatus.INCOMPLETE:
        fail("quiz_locked", "This participation is not eligible for a quiz.")
    if now > deadline(participant, attempt):
        await complete(db, session, participant, now)
        # Preserve fallback completion even though the HTTP request is rejected.
        await db.commit()
        fail(
            "quiz_deadline",
            "Your quiz submission is late. The deadline has passed; "
            "your study time keeps time-only completion and base points.",
            410,
        )
    questions = await questions_for(db, attempt.quiz_id)
    attempt.answers = answers
    attempt.correct_count = sum(answers[q.position] == q.correct_index for q in questions)
    attempt.score_pct = 100 * attempt.correct_count / 15
    attempt.submitted_at = now
    await complete(db, session, participant, now, attempt)
