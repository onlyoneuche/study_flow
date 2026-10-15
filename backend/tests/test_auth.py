import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.models.enums import EducationLevel, audience_for_level
from tests.factories import group

PASSWORD = "study-flow-test-password"
EMAIL = "ada@example.com"


def registration(level=EducationLevel.SS2, **changes):
    secondary = audience_for_level(level) == "secondary"
    fields = dict(
        email=EMAIL,
        password=PASSWORD,
        display_name="Ada",
        level=level.value,
        audience_band=audience_for_level(level).value,
        guardian_consent=secondary,
        adult_confirmation=not secondary,
    )
    fields.update(changes)
    return fields


def register(client, **changes):
    return client.post("/api/v1/auth/register", json=registration(**changes))


def login(client, password=PASSWORD):
    return client.post("/api/v1/auth/jwt/login", data={"username": EMAIL, "password": password})


def mail_token(output, action="verify"):
    matches = re.findall(rf"/auth/{action}#token=([^\s]+)", output)
    assert matches, "Expected a console email link"
    return matches[-1]


def headers(client):
    response = login(client)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_registration_hashes_password_records_consent_and_prints_verification(
    auth_client, db_engine, capsys
):
    response = register(auth_client, is_superuser=True, is_verified=True, is_active=False)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["audience_band"] == "secondary"
    assert body["guardian_consent_at"] is not None and body["adult_confirmed_at"] is None
    assert (
        body["is_superuser"] is False and body["is_verified"] is False and body["is_active"] is True
    )
    assert PASSWORD not in response.text and "hashed_password" not in body
    with db_engine.connect() as connection:
        hashed = connection.scalar(select(User.hashed_password))
    assert hashed.startswith("$argon2") and hashed != PASSWORD
    printed = capsys.readouterr().out
    assert "To: ada@example.com" in printed and "Verify your StudyFlow email" in printed
    assert mail_token(printed) not in response.text


@pytest.mark.parametrize("level", list(EducationLevel))
def test_signup_supports_all_levels_with_correct_band_and_consent(auth_client, level):
    response = register(auth_client, level=level)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["audience_band"] == audience_for_level(level).value
    if body["audience_band"] == "tertiary":
        assert body["age_band"] == "18_plus" and body["adult_confirmed_at"] is not None
        assert body["guardian_consent_at"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"guardian_consent": False},
        {"guardian_consent": "true"},
        {"audience_band": "tertiary"},
        {"guardian_consent_at": "2026-10-15T12:00:00Z"},
        {"level": EducationLevel.UG_100, "adult_confirmation": False},
        {"level": EducationLevel.OTHER, "adult_confirmation": False},
    ],
)
def test_consent_and_band_cannot_be_forged(auth_client, changes):
    response = register(auth_client, **changes)
    assert response.status_code == 422
    assert PASSWORD not in response.text


def test_duplicate_email_and_password_policy(auth_client):
    assert register(auth_client).status_code == 201
    assert register(auth_client, email=EMAIL.upper()).status_code == 400
    assert register(auth_client, email="other@example.com", password="short").status_code == 422


def test_concurrent_registrations_do_not_fail_when_read_snapshots_overlap(auth_client):
    def create(index):
        return register(auth_client, email=f"concurrent-{index}@example.com").status_code

    with ThreadPoolExecutor(max_workers=4) as workers:
        assert list(workers.map(create, range(4))) == [201, 201, 201, 201]


def test_login_profile_and_logout_use_bearer_jwt(auth_client):
    assert auth_client.get("/api/v1/users/me").status_code == 401
    assert register(auth_client).status_code == 201
    assert login(auth_client, "wrong password").status_code == 400
    auth = headers(auth_client)
    assert auth_client.get("/api/v1/users/me", headers=auth).json()["display_name"] == "Ada"
    updated = auth_client.patch(
        "/api/v1/users/me", headers=auth, json={"display_name": "Ada Okafor", "level": "SS3"}
    )
    assert updated.status_code == 200 and updated.json()["level"] == "SS3"
    for payload in [{"is_superuser": True}, {"email": "other@example.com"}, {"display_name": None}]:
        assert auth_client.patch("/api/v1/users/me", headers=auth, json=payload).status_code == 422
    assert auth_client.delete("/api/v1/users/me", headers=auth).status_code == 405
    assert auth_client.get("/api/v1/users/1", headers=auth).status_code == 404
    assert auth_client.post("/api/v1/auth/jwt/logout", headers=auth).status_code == 204


def test_profile_transition_requires_new_consent(auth_client):
    register(auth_client)
    auth = headers(auth_client)
    assert (
        auth_client.patch("/api/v1/users/me", headers=auth, json={"level": "OTHER"}).status_code
        == 422
    )
    response = auth_client.patch(
        "/api/v1/users/me", headers=auth, json={"level": "OTHER", "adult_confirmation": True}
    )
    assert response.status_code == 200 and response.json()["audience_band"] == "tertiary"


def test_profile_band_change_reports_group_conflict_without_partial_update(auth_client, db_engine):
    register(auth_client)
    with Session(db_engine) as session:
        learner = session.scalar(select(User))
        group(session, learner)
        session.commit()
    auth = headers(auth_client)
    response = auth_client.patch(
        "/api/v1/users/me",
        headers=auth,
        json={"level": "OTHER", "adult_confirmation": True},
    )
    assert response.status_code == 409 and "squads" in response.json()["detail"]
    unchanged = auth_client.get("/api/v1/users/me", headers=auth).json()
    assert unchanged["level"] == "SS2" and unchanged["adult_confirmed_at"] is None


def test_verification_is_bound_to_email_audience_and_single_use(auth_client, capsys):
    register(auth_client)
    token = mail_token(capsys.readouterr().out)
    assert (
        auth_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )
    assert auth_client.post("/api/v1/auth/verify", json={"token": "not-a-token"}).status_code == 400
    response = auth_client.post("/api/v1/auth/verify", json={"token": token})
    assert response.status_code == 200 and response.json()["is_verified"] is True
    assert auth_client.post("/api/v1/auth/verify", json={"token": token}).status_code == 400
    assert (
        auth_client.get("/api/v1/users/me", headers=headers(auth_client)).json()["is_verified"]
        is True
    )


def test_verification_request_and_password_request_do_not_disclose_accounts(auth_client, capsys):
    register(auth_client)
    capsys.readouterr()
    for route in ("request-verify-token", "forgot-password"):
        known = auth_client.post(f"/api/v1/auth/{route}", json={"email": EMAIL})
        unknown = auth_client.post(f"/api/v1/auth/{route}", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.content == unknown.content
    output = capsys.readouterr().out
    assert "/auth/verify#token=" in output and "/auth/reset-password#token=" in output


def test_reset_password_changes_hash_and_rejects_reuse(auth_client, capsys):
    register(auth_client)
    capsys.readouterr()
    assert (
        auth_client.post("/api/v1/auth/forgot-password", json={"email": EMAIL}).status_code == 202
    )
    token = mail_token(capsys.readouterr().out, "reset-password")
    invalid = auth_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "short"}
    )
    assert invalid.status_code == 400
    updated = "another-studyflow-password"
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": updated}
        ).status_code
        == 200
    )
    assert login(auth_client).status_code == 400
    assert login(auth_client, updated).status_code == 200
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": PASSWORD}
        ).status_code
        == 400
    )


def test_expired_verification_reset_and_access_tokens_are_rejected(auth_client):
    register(auth_client)
    secret = auth_client.app.state.settings.auth_secret.get_secret_value()
    expired = datetime.now(UTC) - timedelta(seconds=1)
    for route, audience in [
        ("verify", "fastapi-users:verify"),
        ("reset-password", "fastapi-users:reset"),
    ]:
        token = jwt.encode(
            {"sub": "1", "email": EMAIL, "aud": audience, "exp": expired}, secret, algorithm="HS256"
        )
        body = (
            {"token": token, "password": PASSWORD}
            if route == "reset-password"
            else {"token": token}
        )
        assert auth_client.post(f"/api/v1/auth/{route}", json=body).status_code == 400
    token = jwt.encode(
        {"sub": "1", "aud": "fastapi-users:auth", "exp": expired}, secret, algorithm="HS256"
    )
    assert (
        auth_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


def test_inactive_accounts_cannot_log_in(auth_client, db_engine):
    register(auth_client)
    with db_engine.begin() as connection:
        connection.execute(User.__table__.update().values(is_active=False))
    assert login(auth_client).status_code == 400
