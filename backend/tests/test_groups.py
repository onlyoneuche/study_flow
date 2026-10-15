from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.types import utc_now
from app.models import Group, GroupMember, Invite, PointsLedger
from app.models.enums import EducationLevel, PointComponent
from tests.factories import graph


def create(client, actor, **changes):
    response = client.post(
        "/api/v1/groups", headers=actor.headers, json={"name": "Study Squad", **changes}
    )
    assert response.status_code == 201, response.text
    return response.json()


def invite(client, owner, group, uses=20):
    response = client.post(
        f"/api/v1/groups/{group['id']}/invites", headers=owner.headers, json={"max_uses": uses}
    )
    assert response.status_code == 201, response.text
    return response.json()


def accept(client, learner, link):
    return client.post(f"/api/v1/invites/{link['code']}/accept", headers=learner.headers)


def test_create_sets_owner_band_and_limits(auth_client, actor):
    owner = actor(EducationLevel.OTHER)
    for capacity in (2, 9):
        assert (
            auth_client.post(
                "/api/v1/groups",
                headers=owner.headers,
                json={"name": "Squad", "max_members": capacity},
            ).status_code
            == 422
        )
    group = create(auth_client, owner)
    assert group["audience_band"] == "tertiary" and group["streak_paused"]
    assert group["members"][0]["role"] == "owner"
    assert group["weekly_target"] == 100 and group["weekly_points"] == 0
    assert len(auth_client.get("/api/v1/groups", headers=owner.headers).json()) == 1
    create(auth_client, owner)
    create(auth_client, owner)
    assert (
        auth_client.post("/api/v1/groups", headers=owner.headers, json={"name": "Fourth"}).json()[
            "detail"
        ]["code"]
        == "group_limit"
    )


def test_invite_preview_privacy_link_expiry_and_share(auth_client, actor, db_engine):
    owner = actor(name="Private Ada")
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group, 4)
    assert len(link["code"]) == 8 and not set(link["code"]) & set("01ILO")
    assert link["url"].endswith("/join/" + link["code"])
    assert parse_qs(urlparse(link["whatsapp_url"]).query)["text"][0].endswith(link["url"])
    preview = auth_client.get(f"/api/v1/invites/{link['code'].lower()}")
    assert preview.json() == {"name": "Study Squad", "member_count": 1}
    with Session(db_engine) as db:
        saved = db.scalar(select(Invite))
        assert saved.expires_at - saved.created_at == timedelta(days=7)
    assert auth_client.get(f"/api/v1/groups/{group['id']}").status_code == 401
    stranger = actor()
    assert (
        auth_client.get(f"/api/v1/groups/{group['id']}", headers=stranger.headers).status_code
        == 403
    )
    assert auth_client.post(f"/api/v1/invites/{link['code']}/accept").status_code == 401
    assert auth_client.get("/api/v1/invites/NOPE").status_code == 404
    assert (
        auth_client.post("/api/v1/invites/NOPE/accept", headers=stranger.headers).status_code == 404
    )


@pytest.mark.parametrize(
    "case,expected", [("expired", "expired"), ("disabled", "disabled"), ("used", "used_up")]
)
def test_dead_invites_rejected_without_membership_or_use(
    auth_client, actor, db_engine, case, expected
):
    owner, learner = actor(), actor()
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group, 1)
    with Session(db_engine) as db:
        row = db.scalar(select(Invite))
        if case == "expired":
            row.created_at = utc_now() - timedelta(days=8)
            row.expires_at = utc_now() - timedelta(days=1)
        elif case == "disabled":
            row.revoked_at = utc_now()
        else:
            row.uses = 1
        db.commit()
    assert accept(auth_client, learner, link).json()["detail"]["code"] == expected
    assert auth_client.get(f"/api/v1/invites/{link['code']}").status_code == 410
    assert auth_client.get("/api/v1/groups", headers=learner.headers).json() == []


def test_cross_band_and_max_three_groups(auth_client, actor):
    owner, learner, adult = actor(), actor(), actor(EducationLevel.OTHER)
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group)
    rejected = accept(auth_client, adult, link)
    assert rejected.status_code == 403 and rejected.json()["detail"]["code"] == "wrong_band"
    for _ in range(3):
        create(auth_client, learner)
    assert accept(auth_client, learner, link).json()["detail"]["code"] == "group_limit"
    assert (
        auth_client.get(f"/api/v1/groups/{group['id']}", headers=owner.headers).json()["invite"][
            "uses"
        ]
        == 0
    )


def test_full_group_retries_and_concurrent_last_slot(auth_client, actor, db_engine):
    owner = actor()
    group = create(auth_client, owner, max_members=3)
    link = invite(auth_client, owner, group)
    first, second, third = actor(), actor(), actor()
    assert accept(auth_client, first, link).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda a: accept(auth_client, a, link), [second, third]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r for r in responses if r.status_code == 409).json()["detail"]["code"] == "full"
    assert auth_client.get(f"/api/v1/invites/{link['code']}").json()["detail"]["code"] == "full"
    assert accept(auth_client, first, link).json()["already_member"]
    with Session(db_engine) as db:
        assert db.scalar(select(Invite.uses)) == 2
        assert db.scalar(select(func.count()).select_from(GroupMember)) == 3


def test_concurrent_last_invite_use(auth_client, actor):
    owner = actor()
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group, 1)
    learners = [actor(), actor()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda a: accept(auth_client, a, link), learners))
    assert sorted(r.status_code for r in responses) == [200, 410]
    winner = learners[next(i for i, r in enumerate(responses) if r.status_code == 200)]
    assert accept(auth_client, winner, link).json()["already_member"]


def test_only_owner_regenerates_disables_or_removes(auth_client, actor):
    owner, learner, stranger = actor(), actor(), actor()
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group)
    accept(auth_client, learner, link)
    for a in (learner, stranger):
        assert (
            auth_client.post(
                f"/api/v1/groups/{group['id']}/invites", headers=a.headers, json={"max_uses": 4}
            ).status_code
            == 403
        )
        assert (
            auth_client.delete(f"/api/v1/invites/{link['code']}", headers=a.headers).status_code
            == 403
        )
        assert (
            auth_client.delete(
                f"/api/v1/groups/{group['id']}/members/{owner.id}", headers=a.headers
            ).status_code
            == 403
        )
    replacement = invite(auth_client, owner, group)
    assert replacement["code"] != link["code"]
    assert accept(auth_client, stranger, link).json()["detail"]["code"] == "disabled"
    assert (
        auth_client.delete(
            f"/api/v1/invites/{replacement['code']}", headers=owner.headers
        ).status_code
        == 204
    )
    assert accept(auth_client, stranger, replacement).json()["detail"]["code"] == "disabled"
    assert (
        auth_client.post(
            f"/api/v1/groups/{group['id']}/invites", headers=owner.headers, json={"max_uses": 0}
        ).status_code
        == 422
    )


def test_remove_rejoin_leave_and_owner_transfer_retain_points(auth_client, actor, db_engine):
    owner, first, second = actor(), actor(), actor()
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group)
    accept(auth_client, first, link)
    accept(auth_client, second, link)
    with Session(db_engine) as db:
        data = graph(db)
        # Use an independent participation for the removed member with immutable earned history.
        data.participant.user_id = first.id
        db.flush()
        db.add(
            PointsLedger(
                user_id=first.id,
                group_id=group["id"],
                participant_id=data.participant.id,
                component=PointComponent.BASE,
                points=8,
                lagos_date=data.participant.session_date,
                week_start=data.participant.session_date - timedelta(days=3),
            )
        )
        db.commit()
    path = f"/api/v1/groups/{group['id']}/members/"
    assert auth_client.delete(path + str(first.id), headers=owner.headers).status_code == 204
    assert (
        auth_client.get(f"/api/v1/groups/{group['id']}", headers=first.headers).status_code == 403
    )
    assert accept(auth_client, first, link).status_code == 200
    assert auth_client.delete(path + str(owner.id), headers=owner.headers).status_code == 204
    updated = auth_client.get(f"/api/v1/groups/{group['id']}", headers=second.headers).json()
    assert updated["owner_id"] == second.id and updated["streak_paused"]
    with Session(db_engine) as db:
        assert db.scalar(select(PointsLedger.points)) == 8
        history = db.scalars(
            select(GroupMember).where(GroupMember.user_id == first.id).order_by(GroupMember.id)
        ).all()
        assert len(history) == 2 and history[0].removed_by == owner.id


def test_empty_group_closes_invites_and_no_longer_uses_a_slot(auth_client, actor, db_engine):
    owner, other = actor(), actor()
    group = create(auth_client, owner)
    link = invite(auth_client, owner, group)
    assert (
        auth_client.delete(
            f"/api/v1/groups/{group['id']}/members/{owner.id}", headers=owner.headers
        ).status_code
        == 204
    )
    assert accept(auth_client, other, link).json()["detail"]["code"] == "disabled"
    assert auth_client.get("/api/v1/groups", headers=owner.headers).json() == []
    with Session(db_engine) as db:
        assert not db.get(Group, group["id"]).is_active


def test_invite_code_collision_retries_and_member_can_leave(auth_client, actor, monkeypatch):
    owner, learner = actor(), actor()
    group = create(auth_client, owner)
    sequence = iter("AAAAAAAA" + "AAAAAAAA" + "BBBBBBBB")
    monkeypatch.setattr("app.services.groups.secrets.choice", lambda _: next(sequence))
    first = invite(auth_client, owner, group)
    second = invite(auth_client, owner, group)
    assert first["code"] == "AAAAAAAA" and second["code"] == "BBBBBBBB"
    assert accept(auth_client, learner, second).status_code == 200
    assert (
        auth_client.delete(
            f"/api/v1/groups/{group['id']}/members/{learner.id}", headers=learner.headers
        ).status_code
        == 204
    )
    assert auth_client.get("/api/v1/groups", headers=learner.headers).json() == []
    assert accept(auth_client, learner, second).json()["already_member"] is False
