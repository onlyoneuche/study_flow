"""Optional self-reported reflection data. Never imported by scoring/streak services."""

from datetime import timedelta
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.models import FocusSummary, SessionParticipant
from app.models.enums import SessionMode, SessionStatus
from app.services.groups import fail


class SummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    opted_in: bool
    attentive_pct: int | None = Field(default=None, ge=0, le=100)
    away_seconds: int | None = Field(default=None, ge=0)
    samples: int | None = Field(default=None, ge=0)
    paused_seconds: int | None = Field(default=None, ge=0)
    sample_fps: float | None = None
    tracker_version: str = Field(min_length=1, max_length=100, pattern=r"^mp-[\w./-]+$")

    @model_validator(mode="after")
    def metrics(self):
        values = [self.attentive_pct, self.away_seconds, self.samples, self.paused_seconds]
        if self.opted_in:
            if any(v is None for v in values) or self.sample_fps != 1:
                raise ValueError("The minimal tracker requires all numeric metrics at 1 fps")
        elif any(v is not None for v in [*values, self.sample_fps]):
            raise ValueError("Opted-out summaries cannot contain metrics")
        return self


async def save_summary(db, session, participant, data, now):
    if not participant.ended_at:
        fail("focus_not_ended", "Focus summaries are saved after your study time ends.")
    if now > session.end_at + timedelta(minutes=30):
        fail("focus_deadline", "The focus summary window has closed.", 410)
    existing = await db.scalar(
        select(FocusSummary.id).where(FocusSummary.session_participant_id == participant.id)
    )
    if existing:
        fail("focus_exists", "A focus summary is already saved for this participation.")
    valid = False
    if data.opted_in:
        duration = max(
            0,
            (participant.ended_at - max(participant.joined_at, session.started_at)).total_seconds(),
        )
        if (
            data.samples > 2 * duration + 30
            or data.away_seconds > duration
            or data.paused_seconds > duration
        ):
            fail("focus_bounds", "Focus metrics exceed the participation duration.", 422)
        valid = (
            participant.active_seconds > 0
            and data.samples >= 60
            and data.samples / data.sample_fps >= 0.5 * participant.active_seconds
        )
    row = FocusSummary(
        session_participant_id=participant.id,
        **data.model_dump(),
        is_valid=valid,
        created_at=now,
    )
    db.add(row)
    await db.flush()
    return row


def personal(row):
    if not row or not row.opted_in:
        return None
    return dict(
        attentive_pct=row.attentive_pct,
        away_seconds=row.away_seconds,
        paused_seconds=row.paused_seconds,
        samples=row.samples,
        is_valid=row.is_valid,
    )


async def own_summary(db, participant_id):
    return await db.scalar(
        select(FocusSummary).where(FocusSummary.session_participant_id == participant_id)
    )


async def comparison(db, session, participant, now):
    if session.status != SessionStatus.ENDED or now <= session.end_at + timedelta(minutes=30):
        fail("focus_pending", "Session comparison opens 30 minutes after the session ends.")
    mine = await own_summary(db, participant.id)
    result = dict(mine=personal(mine), comparison=None)
    if not mine or not mine.opted_in or not mine.is_valid or session.mode == SessionMode.SOLO:
        return result
    values = list(
        await db.scalars(
            select(FocusSummary.attentive_pct)
            .join(SessionParticipant, FocusSummary.session_participant_id == SessionParticipant.id)
            .where(
                SessionParticipant.session_id == session.id,
                FocusSummary.opted_in.is_(True),
                FocusSummary.is_valid.is_(True),
            )
        )
    )
    if len(values) >= 3:
        middle = median(values)
        difference = mine.attentive_pct - middle
        result["comparison"] = dict(
            n=len(values),
            median_pct=middle,
            position="above" if difference > 5 else "below" if difference < -5 else "around",
        )
    return result
