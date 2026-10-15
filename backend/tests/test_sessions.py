from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.models import GroupMember, SessionParticipant, StudySession
from tests.test_groups import accept, create, invite


def solo(client, learner, duration=25):
    response = client.post(
        "/api/v1/sessions/solo",
        headers=learner.headers,
        json={"planned_minutes": duration, "subject": " Maths ", "topic": "Indices"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def live(client, learner, group, scheduled=None):
    response = client.post(
        f"/api/v1/groups/{group['id']}/sessions",
        headers=learner.headers,
        json={
            "planned_minutes": 25,
            **({"scheduled_at": scheduled.isoformat()} if scheduled else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def join(client, learner, session):
    return client.post(
        f"/api/v1/sessions/{session['id']}/join",
        headers=learner.headers,
        json={"subject": "Chemistry", "topic": "Mole concept"},
    )


def socket(client, learner, session):
    return client.websocket_connect(
        f"/ws/sessions/{session['id']}?token=" + learner.headers["Authorization"].split()[1]
    )


def state(ws):
    while True:
        message = ws.receive_json()
        if message["type"] == "state":
            return message


def beat(ws):
    ws.send_json({"type": "heartbeat", "active_seconds": 99999999})
    return state(ws)


def test_solo_clock_snapshot_normalisation_and_security(auth_client, actor, clock, db_engine):
    learner, stranger = actor(), actor()
    session = solo(auth_client, learner)
    assert session["mine"]["required_seconds"] == 1200
    assert session["mine"]["active_seconds"] == 0 and session["mine"]["level"] == "SS2"
    assert session["server_now"] == session["started_at"]
    assert session["mine"]["session_date"] == "2026-10-15"
    path = f"/api/v1/sessions/{session['id']}"
    assert auth_client.get(path, headers=stranger.headers).status_code == 403
    assert auth_client.get(path).status_code == 401
    for minutes in (0, 24, 26, 90):
        assert (
            auth_client.post(
                "/api/v1/sessions/solo",
                headers=learner.headers,
                json={"planned_minutes": minutes, "subject": "Maths", "topic": "Indices"},
            ).status_code
            == 422
        )
    assert (
        auth_client.post(
            "/api/v1/sessions/solo",
            headers=learner.headers,
            json={"planned_minutes": 25, "subject": " ", "topic": "Indices"},
        ).status_code
        == 422
    )
    with Session(db_engine) as db:
        participant = db.scalar(select(SessionParticipant))
        assert participant.subject == "Maths" and participant.subject_norm == "mathematics"
    with pytest.raises(WebSocketDisconnect):
        with socket(auth_client, stranger, session):
            pass
    with pytest.raises(WebSocketDisconnect):
        with auth_client.websocket_connect(f"/ws/sessions/{session['id']}?token=bad"):
            pass


def test_heartbeat_grace_exact_boundary_long_gap_and_disconnect(auth_client, actor, clock):
    learner = actor()
    session = solo(auth_client, learner)
    with socket(auth_client, learner, session) as ws:
        assert state(ws)["mine"]["active_seconds"] == 0
        clock.now += timedelta(seconds=120)
        assert beat(ws)["mine"]["active_seconds"] == 120
        clock.now += timedelta(seconds=121)
        polled = auth_client.get(
            f"/api/v1/sessions/{session['id']}", headers=learner.headers
        ).json()
        assert polled["members"][0]["status"] == "disconnected"
        assert beat(ws)["mine"]["active_seconds"] == 135
        assert beat(ws)["mine"]["active_seconds"] == 135
    clock.now += timedelta(seconds=60)
    with socket(auth_client, learner, session) as ws:
        state(ws)
        assert beat(ws)["mine"]["active_seconds"] == 195


def test_leave_rejoin_stops_time_and_preserves_snapshot(auth_client, actor, clock, db_engine):
    learner = actor()
    session = solo(auth_client, learner)
    path = f"/api/v1/sessions/{session['id']}"
    clock.now += timedelta(seconds=60)
    left = auth_client.post(path + "/leave", headers=learner.headers).json()
    assert left["mine"]["active_seconds"] == 60 and left["mine"]["status"] == "left"
    clock.now += timedelta(minutes=5)
    with socket(auth_client, learner, session) as ws:
        state(ws)
        assert beat(ws)["mine"]["active_seconds"] == 60
    auth_client.patch("/api/v1/users/me", headers=learner.headers, json={"level": "SS3"})
    again = join(auth_client, learner, session).json()["participant"]
    assert again["subject"] == "Maths" and again["level"] == "SS2"
    with socket(auth_client, learner, session) as ws:
        state(ws)
        clock.now += timedelta(seconds=30)
        assert beat(ws)["mine"]["active_seconds"] == 90
    with Session(db_engine) as db:
        assert len(db.scalars(select(SessionParticipant)).all()) == 1


def test_solo_finish_requires_80_percent_and_persists_participant_end(auth_client, actor, clock):
    learner = actor()
    session = solo(auth_client, learner)
    path = f"/api/v1/sessions/{session['id']}"
    assert auth_client.post(path + "/finish", headers=learner.headers).status_code == 409
    with socket(auth_client, learner, session) as ws:
        state(ws)
        for _ in range(10):
            clock.now += timedelta(seconds=120)
            beat(ws)
    finished = auth_client.post(path + "/finish", headers=learner.headers).json()
    assert finished["status"] == "ended" and finished["mine"]["quiz_unlocked"]
    assert datetime.fromisoformat(finished["mine"]["ended_at"]) == clock.now
    assert finished["mine"]["status"] != "completed"  # quiz is still pending until step 6
    assert (
        auth_client.post(path + "/finish", headers=learner.headers).json()["mine"]
        == finished["mine"]
    )
    assert join(auth_client, learner, session).status_code == 409


def test_end_with_insufficient_time_has_no_quiz_or_completion(auth_client, actor, clock):
    learner = actor()
    session = solo(auth_client, learner)
    clock.now += timedelta(minutes=25)
    result = auth_client.get(f"/api/v1/sessions/{session['id']}", headers=learner.headers).json()
    assert result["status"] == "ended"
    assert result["mine"]["status"] == "incomplete" and not result["mine"]["quiz_unlocked"]
    assert result["mine"]["active_seconds"] == 0


def test_live_scheduled_start_late_rules_and_cross_midnight_date(auth_client, actor, clock):
    owner, learner, observer = actor(), actor(), actor()
    group = create(auth_client, owner)
    code = invite(auth_client, owner, group)
    accept(auth_client, learner, code)
    accept(auth_client, observer, code)
    scheduled = clock.now + timedelta(minutes=2)
    session = live(auth_client, owner, group, scheduled)
    assert session["status"] == "scheduled"
    assert join(auth_client, owner, session).status_code == 200
    with socket(auth_client, owner, session) as ws:
        state(ws)
        clock.now += timedelta(seconds=60)
        assert beat(ws)["mine"]["active_seconds"] == 0
    clock.now = scheduled + timedelta(minutes=10)
    joined = join(auth_client, learner, session).json()
    assert joined["participant"]["is_live_credited"] and not joined["solo_offer"]
    assert joined["participant"]["required_seconds"] == 720
    assert joined["participant"]["session_date"] == "2026-10-15"
    clock.now += timedelta(microseconds=1)
    late = join(auth_client, observer, session).json()
    assert late["solo_offer"] and late["participant"] is None
    with socket(auth_client, observer, session) as ws:
        observed = state(ws)
        assert observed["mine"] is None and observed["goal"]["total"] == 3
    assert (
        auth_client.post(
            f"/api/v1/sessions/{session['id']}/finish", headers=owner.headers
        ).status_code
        == 409
    )
    own_clock = solo(auth_client, observer)
    assert own_clock["mine"]["session_date"] == "2026-10-16"
    assert not own_clock["mine"]["is_live_credited"]


def test_scheduled_runtime_catchup_starts_and_ends_without_participants(
    auth_client, actor, clock, db_engine
):
    owner = actor()
    group = create(auth_client, owner)
    session = live(auth_client, owner, group, clock.now + timedelta(minutes=1))
    clock.now += timedelta(minutes=2)
    auth_client.portal.call(auth_client.app.state.presence.tick)
    with Session(db_engine) as db:
        assert db.get(StudySession, session["id"]).status == "running"
    clock.now += timedelta(minutes=30)
    auth_client.portal.call(auth_client.app.state.presence.tick)
    auth_client.portal.call(auth_client.app.state.presence.tick)
    with Session(db_engine) as db:
        row = db.get(StudySession, session["id"])
        assert row.status == "ended" and row.started_at.isoformat() == session[
            "started_at"
        ].replace("Z", "+00:00")


def test_live_private_membership_removal_and_fixed_reactions(auth_client, actor, clock):
    owner, learner, stranger = actor(), actor(), actor()
    group = create(auth_client, owner)
    code = invite(auth_client, owner, group)
    accept(auth_client, learner, code)
    session = live(auth_client, owner, group)
    assert join(auth_client, stranger, session).status_code == 403
    join(auth_client, learner, session)
    with socket(auth_client, learner, session) as ws:
        state(ws)
        ws.send_json({"type": "react", "emoji": "free text"})
        while ws.receive_json()["type"] != "error":
            pass
        ws.send_json({"type": "react", "emoji": "💪"})
        while ws.receive_json()["type"] != "reaction":
            pass
        auth_client.delete(
            f"/api/v1/groups/{group['id']}/members/{learner.id}", headers=owner.headers
        )
        ws.send_json({"type": "heartbeat"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4403
    with pytest.raises(WebSocketDisconnect):
        with auth_client.websocket_connect(
            f"/ws/sessions/{session['id']}?token=" + owner.headers["Authorization"].split()[1],
            headers={"origin": "https://untrusted.test"},
        ):
            pass


@pytest.mark.parametrize("minutes", [25, 45, 60])
def test_supported_durations_and_server_ignores_client_time(auth_client, actor, clock, minutes):
    learner = actor()
    session = solo(auth_client, learner, minutes)
    assert datetime.fromisoformat(session["end_at"]) - datetime.fromisoformat(
        session["started_at"]
    ) == timedelta(minutes=minutes)
    assert session["mine"]["required_seconds"] == 0.8 * minutes * 60
    assert (
        auth_client.post(
            "/api/v1/sessions/solo",
            headers=learner.headers,
            json={
                "planned_minutes": minutes,
                "subject": "Maths",
                "topic": "Indices",
                "started_at": "2000-01-01T00:00:00Z",
            },
        ).status_code
        == 422
    )


def test_multiple_sockets_cannot_double_count_active_time(auth_client, actor, clock, db_engine):
    learner = actor()
    session = solo(auth_client, learner)
    with (
        socket(auth_client, learner, session) as first,
        socket(auth_client, learner, session) as second,
    ):
        state(first)
        state(second)
        clock.now += timedelta(seconds=15)
        first.send_json({"type": "heartbeat"})
        # A server reaction is an ordered acknowledgement after the heartbeat's transaction.
        first.send_json({"type": "react", "emoji": "📚"})
        while first.receive_json()["type"] != "reaction":
            pass
        second.send_json({"type": "heartbeat"})
        second.send_json({"type": "react", "emoji": "👏"})
        while second.receive_json()["type"] != "reaction":
            pass
    with Session(db_engine) as db:
        assert db.scalar(select(SessionParticipant.active_seconds)) == 15


def test_finish_after_planned_end_never_extends_quiz_window(auth_client, actor, clock):
    learner = actor()
    session = solo(auth_client, learner)
    with socket(auth_client, learner, session) as ws:
        state(ws)
        for _ in range(10):
            clock.now += timedelta(seconds=120)
            beat(ws)
    clock.now += timedelta(minutes=8)
    result = auth_client.post(
        f"/api/v1/sessions/{session['id']}/finish", headers=learner.headers
    ).json()
    assert result["mine"]["ended_at"] == session["end_at"] == result["end_at"]


def test_fractional_heartbeats_do_not_lose_a_second_on_every_message(auth_client, actor, clock):
    learner = actor()
    session = solo(auth_client, learner)
    with socket(auth_client, learner, session) as ws:
        state(ws)
        for seconds in (13.7, 15.2, 15.1):
            clock.now += timedelta(seconds=seconds)
            result = beat(ws)
        assert result["mine"]["active_seconds"] == 44


def test_former_live_host_cannot_list_a_room_after_leaving_group(auth_client, actor, clock):
    owner, next_owner = actor(), actor()
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group)
    accept(auth_client, next_owner, link)
    live(auth_client, owner, group)
    auth_client.delete(f"/api/v1/groups/{group['id']}/members/{owner.id}", headers=owner.headers)
    assert auth_client.get("/api/v1/sessions", headers=owner.headers).json() == []
    assert len(auth_client.get("/api/v1/sessions", headers=next_owner.headers).json()) == 1


def test_shared_goal_uses_membership_at_scheduled_start(auth_client, actor, clock, db_engine):
    owner, existing, newcomer = actor(), actor(), actor()
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group)
    accept(auth_client, existing, link)
    session = live(auth_client, owner, group)
    accept(auth_client, newcomer, link)
    with Session(db_engine) as db:
        member = db.scalar(select(GroupMember).where(GroupMember.user_id == newcomer.id))
        member.joined_at = clock.now + timedelta(seconds=1)
        db.commit()
    clock.now += timedelta(minutes=5)
    join(auth_client, existing, session)
    join(auth_client, newcomer, session)
    result = auth_client.get(f"/api/v1/sessions/{session['id']}", headers=owner.headers).json()
    assert result["goal"]["total"] == 2
    auth_client.delete(f"/api/v1/groups/{group['id']}/members/{existing.id}", headers=owner.headers)
    # Membership intervals after the start cannot shrink the fixed denominator.
    with Session(db_engine) as db:
        member = db.scalar(select(GroupMember).where(GroupMember.user_id == existing.id))
        member.left_at = clock.now
        db.commit()
    assert (
        auth_client.get(f"/api/v1/sessions/{session['id']}", headers=owner.headers).json()["goal"][
            "total"
        ]
        == 2
    )
