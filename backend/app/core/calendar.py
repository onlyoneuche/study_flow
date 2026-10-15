from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LAGOS = ZoneInfo("Africa/Lagos")


def lagos_date(timestamp: datetime) -> date:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return timestamp.astimezone(LAGOS).date()


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def lagos_week_start(timestamp: datetime) -> date:
    return monday_of(lagos_date(timestamp))


def latest_evaluable_day(timestamp: datetime) -> date:
    day = lagos_date(timestamp)
    return day - timedelta(days=2 if timestamp.astimezone(LAGOS).time() < time(2) else 1)
