from datetime import timedelta

from app.core.calendar import lagos_date
from app.models import GroupMember, SessionParticipant, StudySession
from app.models.enums import ParticipantStatus, SessionMode
from tests.factories import group
from tests.test_streaks import completed


def test_dashboard_requires_auth_and_handles_empty_account(auth_client, actor):
    assert auth_client.get("/api/v1/users/me/dashboard").status_code == 401
    owner = actor()
    data = auth_client.get("/api/v1/users/me/dashboard", headers=owner.headers).json()
    assert data["groups"] == data["sessions"] == data["recent"] == []
    assert data["weekly_completed"] == 0


def test_dashboard_own_history_and_group_completion_counts_no_scores(db, auth_client, actor, clock):
    from app.models import User

    owner, friend, stranger = actor(), actor(name="Tunde"), actor(name="Private learner")
    squad = group(db, db.get(User, owner.id))
    for person in (owner, friend):
        db.add(GroupMember(group_id=squad.id, user_id=person.id))
    db.commit()
    today = lagos_date(clock.now)
    for person in (owner, owner, friend, stranger):
        completed(db, db.get(User, person.id), today)
    completed(db, db.get(User, owner.id), today - timedelta(days=8))
    response = auth_client.get("/api/v1/users/me/dashboard", headers=owner.headers)
    assert response.status_code == 200
    data = response.json()
    assert data["weekly_completed"] == 2  # Not doubled for duplicate ledger groups.
    assert len(data["recent"]) == 3  # Only this learner's study, including old sessions.
    g = data["groups"][0]
    assert g["completed_today"] == 3
    assert {m["user_id"]: m["completed_today"] for m in g["members"]} == {owner.id: 2, friend.id: 1}
    assert not any(
        key in response.text for key in ("correct_index", "score_pct", "email", "Private learner")
    )
    assert (
        auth_client.get("/api/v1/users/me/dashboard", headers=stranger.headers).json()["groups"]
        == []
    )


def test_recent_quiz_links_use_both_deadlines(db, auth_client, actor, clock):
    from app.models import QuizAttempt
    from tests.factories import graph

    owner = actor()
    data = graph(db)
    p, s = data.participant, data.session
    p.user_id = s.host_id = owner.id
    p.ended_at = clock.now - timedelta(minutes=29)
    s.status = "ended"
    s.started_at = p.ended_at - timedelta(minutes=45)
    s.end_at = p.ended_at
    p.status = ParticipantStatus.JOINED
    p.active_seconds = 2700
    a = QuizAttempt(
        participant_id=p.id,
        quiz_id=data.quiz.id,
        user_id=owner.id,
        started_at=clock.now - timedelta(minutes=19),
    )
    db.add(a)
    db.commit()

    def available():
        return auth_client.get("/api/v1/users/me/dashboard", headers=owner.headers).json()[
            "recent"
        ][0]["quiz_available"]

    assert available()
    clock.now += timedelta(minutes=2)
    assert not available()


def test_open_rooms_and_recent_topics_only_accessible_to_user(db, auth_client, actor, clock):
    owner, other = actor(), actor()
    for uid, topic in ((owner.id, "My topic"), (other.id, "Private topic")):
        s = StudySession(
            host_id=uid,
            mode=SessionMode.SOLO,
            planned_minutes=25,
            started_at=clock.now,
            end_at=clock.now + timedelta(minutes=25),
            status="running",
        )
        db.add(s)
        db.flush()
        db.add(
            SessionParticipant(
                session_id=s.id,
                user_id=uid,
                subject="Chemistry",
                subject_norm="chemistry",
                topic=topic,
                topic_norm=topic.lower(),
                level="SS2",
                session_date=lagos_date(clock.now),
                joined_at=clock.now,
                last_heartbeat_at=clock.now,
            )
        )
    db.commit()
    response = auth_client.get("/api/v1/users/me/dashboard", headers=owner.headers)
    assert len(response.json()["sessions"]) == 1
    assert "Private topic" not in response.text
    assert response.json()["recent"][0]["topic"] == "My topic"


def test_result_history_is_private_same_subject_level_and_at_completion(
    db, auth_client, actor, clock
):
    from app.models.enums import EducationLevel
    from tests.test_scoring import participation

    owner, other = actor(), actor()
    for i in range(8):
        participation(db, owner.id, clock.now - timedelta(days=9 - i), score=i, counted=True)
    participation(db, other.id, clock.now - timedelta(hours=1), score=15, counted=True)
    participation(db, owner.id, clock.now - timedelta(hours=1), subject="physics", counted=True)
    participation(
        db, owner.id, clock.now - timedelta(hours=1), level=EducationLevel.SS3, counted=True
    )
    p, _, _ = participation(db, owner.id, clock.now, score=10, counted=True)
    participation(db, owner.id, clock.now + timedelta(days=1), score=15, counted=True)
    db.commit()
    response = auth_client.get(f"/api/v1/participants/{p.id}/result", headers=owner.headers)
    history = response.json()["score_history"]
    assert [round(r["score_pct"] * 15 / 100) for r in history] == [3, 4, 5, 6, 7, 10]
    assert (
        auth_client.get(f"/api/v1/participants/{p.id}/result", headers=other.headers).status_code
        == 403
    )


def test_expired_quiz_has_clear_rejection_and_readable_time_only_result(
    db, auth_client, actor, clock
):
    from tests.test_scoring import participation

    owner = actor()
    p, _, a = participation(db, owner.id, clock.now - timedelta(hours=1))
    a.submitted_at = None
    a.answers = a.correct_count = a.score_pct = None
    db.commit()
    assert (
        auth_client.get(f"/api/v1/participants/{p.id}/result", headers=owner.headers).status_code
        == 409
    )
    expired = auth_client.get(f"/api/v1/participants/{p.id}/quiz", headers=owner.headers)
    assert expired.status_code == 410
    assert "deadline" in expired.text
    response = auth_client.get(f"/api/v1/participants/{p.id}/result", headers=owner.headers)
    assert response.status_code == 200
    assert response.json()["status"] == "time_only"
    assert "correct_index" not in response.text
