from datetime import timedelta

import pytest
from sqlalchemy import event, select

from app.models import FocusSummary, GroupStreak, SessionParticipant, User
from tests.factories import group as make_group
from tests.test_scoring import award, participation
from tests.test_streaks import DAY, completed, run, squad


def body(**changes):
    return dict(
        opted_in=True,
        attentive_pct=90,
        away_seconds=30,
        samples=1500,
        paused_seconds=100,
        sample_fps=1.0,
        tracker_version="mp-test/minimal-v1",
        **changes,
    )


@pytest.fixture
def focus_client(auth_client):
    auth_client.app.state.settings.focus_tracker_enabled = True
    return auth_client


def example(client, actor, clock, db, count=3, mode="live"):
    people = [actor(name=f"Person {i}") for i in range(count)]
    g = make_group(db, db.get(User, people[0].id))
    p, s, _ = participation(
        db, people[0].id, clock.now, mode=mode, group_id=g.id if mode == "live" else None
    )
    participants = [p]
    for person in people[1:]:
        other = SessionParticipant(
            session_id=s.id,
            user_id=person.id,
            subject="Physics",
            subject_norm="physics",
            topic="Forces",
            topic_norm="forces",
            level="SS2",
            joined_at=s.started_at,
            active_seconds=p.active_seconds,
            ended_at=s.end_at,
            session_date=p.session_date,
        )
        db.add(other)
        participants.append(other)
    db.commit()
    return people, participants, s


def post(client, person, p, values=None):
    return client.post(
        f"/api/v1/participants/{p.id}/focus-summary", headers=person.headers, json=values or body()
    )


def test_flag_off_and_private_owner(focus_client, actor, clock, db):
    people, ps, s = example(focus_client, actor, clock, db)
    assert focus_client.get("/api/v1/features").json() == {"focus_tracker_enabled": True}
    assert post(focus_client, people[1], ps[0]).status_code == 404
    assert (
        focus_client.get(
            f"/api/v1/sessions/{s.id}/focus-comparison", headers=actor().headers
        ).status_code
        == 404
    )
    assert (
        focus_client.post(f"/api/v1/participants/{ps[0].id}/focus-summary", json=body()).status_code
        == 401
    )
    focus_client.app.state.settings.focus_tracker_enabled = False
    assert post(focus_client, people[0], ps[0]).status_code == 404
    assert focus_client.get("/api/v1/features").json() == {"focus_tracker_enabled": False}


def test_summary_coverage_repeat_and_own_read(focus_client, actor, clock, db):
    people, ps, _ = example(focus_client, actor, clock, db)
    response = post(focus_client, people[0], ps[0])
    assert response.status_code == 201, response.text
    assert response.json()["mine"]["is_valid"]
    assert post(focus_client, people[0], ps[0]).status_code == 409
    assert (
        focus_client.get(
            f"/api/v1/participants/{ps[0].id}/focus-summary", headers=people[1].headers
        ).status_code
        == 404
    )
    assert (
        post(focus_client, people[1], ps[1], body_low(samples=59)).json()["mine"]["is_valid"]
        is False
    )
    assert (
        post(focus_client, people[2], ps[2], body_low(samples=100)).json()["mine"]["is_valid"]
        is False
    )


def body_low(**changes):
    return body() | changes


@pytest.mark.parametrize(
    "changes",
    [
        {"attentive_pct": 101},
        {"samples": -1},
        {"samples": True},
        {"attentive_pct": 1.2},
        {"sample_fps": 2.0},
        {"image": "data:image/jpeg;base64,private"},
        {"landmarks": [1, 2]},
        {"opted_in": False},
        {"samples": 6000},
        {"away_seconds": 2701},
        {"paused_seconds": 2701},
        {"tracker_version": "person@example.com"},
    ],
)
def test_only_bounded_numeric_metrics(focus_client, actor, clock, db, changes):
    people, ps, _ = example(focus_client, actor, clock, db, count=1)
    assert post(focus_client, people[0], ps[0], body_low(**changes)).status_code == 422
    assert db.scalar(select(FocusSummary.id)) is None


def test_opt_out_has_no_metrics(focus_client, actor, clock, db):
    people, ps, _ = example(focus_client, actor, clock, db, count=1)
    assert post(
        focus_client, people[0], ps[0], {"opted_in": False, "tracker_version": "mp-test/minimal-v1"}
    ).json() == {"mine": None}
    db.rollback()
    row = db.scalar(select(FocusSummary))
    assert not row.is_valid and row.attentive_pct is None


def test_end_and_window_boundaries(focus_client, actor, clock, db):
    people, ps, s = example(focus_client, actor, clock, db)
    ps[0].ended_at = None
    db.commit()
    assert post(focus_client, people[0], ps[0]).status_code == 409
    clock.now = s.end_at + timedelta(minutes=30)
    assert post(focus_client, people[1], ps[1]).status_code == 201
    assert (
        focus_client.get(
            f"/api/v1/sessions/{s.id}/focus-comparison", headers=people[1].headers
        ).status_code
        == 409
    )
    clock.now += timedelta(microseconds=1)
    assert post(focus_client, people[2], ps[2]).status_code == 410


def test_anonymous_closed_window_median_and_thresholds(focus_client, actor, clock, db):
    people, ps, s = example(focus_client, actor, clock, db)
    for person, p, score in zip(people, ps, [90, 80, 70], strict=True):
        assert post(focus_client, person, p, body_low(attentive_pct=score)).status_code == 201
    path = f"/api/v1/sessions/{s.id}/focus-comparison"
    assert focus_client.get(path, headers=people[0].headers).status_code == 409
    clock.now = s.end_at + timedelta(minutes=31)
    for person, position in zip(people, ["above", "around", "below"], strict=True):
        response = focus_client.get(path, headers=person.headers)
        assert response.status_code == 200
        assert response.json()["comparison"] == {"n": 3, "median_pct": 80, "position": position}
        assert set(response.json()) == {"mine", "comparison"}
        assert "Person" not in response.text and "user_id" not in response.text
    db.rollback()
    for p, pct in zip(ps, [85, 80, 75], strict=True):
        row = db.scalar(select(FocusSummary).where(FocusSummary.session_participant_id == p.id))
        row.attentive_pct = pct
    db.commit()
    assert (
        focus_client.get(path, headers=people[0].headers).json()["comparison"]["position"]
        == "around"
    )
    assert (
        focus_client.get(path, headers=people[2].headers).json()["comparison"]["position"]
        == "around"
    )


@pytest.mark.parametrize(
    "count,invalid,mode", [(2, False, "live"), (3, True, "live"), (1, False, "solo")]
)
def test_personal_only_without_three_valid(focus_client, actor, clock, db, count, invalid, mode):
    people, ps, s = example(focus_client, actor, clock, db, count=count, mode=mode)
    for i, (person, p) in enumerate(zip(people, ps, strict=True)):
        post(focus_client, person, p, body_low(samples=20 if invalid and i == 2 else 1500))
    clock.now = s.end_at + timedelta(minutes=31)
    response = focus_client.get(
        f"/api/v1/sessions/{s.id}/focus-comparison", headers=people[0].headers
    )
    assert response.json()["mine"]["attentive_pct"] == 90
    assert response.json()["comparison"] is None


def test_points_streaks_and_rankings_never_query_focus(focus_client, actor, clock, db):
    # SQL guard is stronger than comparing totals: these paths must not even read the table.
    learner = actor()
    from tests.test_groups import create

    group = create(focus_client, learner)
    p, _, _ = participation(db, learner.id, clock.now)
    db.commit()
    post(focus_client, learner, p, body_low(attentive_pct=0))
    g, people, _, _ = squad(db)
    for person in people:
        completed(db, person, DAY)
    engine = focus_client.app.state.database.engine.sync_engine

    def forbid(_conn, _cursor, statement, _parameters, _context, _executemany):
        assert "focus_summaries" not in statement.lower()

    event.listen(engine, "before_cursor_execute", forbid)
    try:
        award(focus_client, p.id, clock.now)
        run(focus_client)
        db.rollback()
        assert db.scalar(select(GroupStreak.current).where(GroupStreak.group_id == g.id)) == 5
        assert (
            focus_client.get(
                f"/api/v1/groups/{group['id']}/points", headers=learner.headers
            ).status_code
            == 200
        )
        assert (
            focus_client.get("/api/v1/leaderboard/groups", headers=learner.headers).status_code
            == 200
        )
        assert focus_client.get(
            f"/api/v1/groups/{g.id}/points", headers=learner.headers
        ).status_code in (200, 403, 404)
    finally:
        event.remove(engine, "before_cursor_execute", forbid)


def test_other_sessions_cannot_unlock_a_comparison(focus_client, actor, clock, db):
    people, ps, session = example(focus_client, actor, clock, db, count=2)
    for person, participant in zip(people, ps, strict=True):
        assert post(focus_client, person, participant).status_code == 201
    db.rollback()
    other_people, other_ps, _ = example(focus_client, actor, clock, db, count=3)
    for person, participant in zip(other_people, other_ps, strict=True):
        assert post(focus_client, person, participant).status_code == 201
    clock.now = session.end_at + timedelta(minutes=31)
    result = focus_client.get(
        f"/api/v1/sessions/{session.id}/focus-comparison", headers=people[0].headers
    ).json()
    assert result["mine"]["attentive_pct"] == 90
    assert result["comparison"] is None
