import hashlib

PROMPT_VERSION = "v1"


def normalise(value: str):
    return " ".join(value.lower().split())


def normalise_subject(value: str):
    value = normalise(value)
    return {"maths": "mathematics", "chem": "chemistry"}.get(value, value)


def cache_key(subject: str, topic: str, level: str):
    return hashlib.sha256(f"{subject}|{topic}|{level}|{PROMPT_VERSION}".encode()).hexdigest()


def required_seconds(session, participant):
    start = max(session.started_at, participant.joined_at)
    return (
        0.8 * (session.end_at - start).total_seconds()
        if session.mode == "live"
        else 0.8 * session.planned_minutes * 60
    )
