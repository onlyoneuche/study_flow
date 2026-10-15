import asyncio
import copy
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.study import cache_key
from app.models import (
    PointsLedger,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    SessionParticipant,
)
from app.models.enums import EducationLevel, QuizVariantStatus
from app.quizzes.schema import QuizDocument, level_descriptor
from app.quizzes.seed import seed_quizzes
from app.quizzes.worker import Job, store_quiz
from tests.test_groups import create

DOCUMENT = json.loads((Path(__file__).parents[1] / "app/quizzes/demo_quizzes.json").read_text())[0]


def valid_document():
    return {"questions": copy.deepcopy(DOCUMENT["questions"])}


@pytest.fixture
def source():
    return SimpleNamespace(requests=[], responses=[], gate=None)


@pytest.fixture
def ollama_transport(source):
    async def respond(request):
        source.requests.append((json.loads(request.content), request.extensions["timeout"]))
        if source.gate:
            await source.gate.wait()
        reply = source.responses.pop(0) if source.responses else valid_document()
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={"message": {"content": content}})

    return httpx.MockTransport(respond)


@pytest.fixture(autouse=True)
def quiz_runtime(auth_client):
    auth_client.portal.call(auth_client.app.state.quizzes.start)


def drain(client):
    client.portal.call(client.app.state.quizzes.queue.join)


def prepare(client, learner, subject="Chemistry", topic="Mole concept"):
    response = client.post(
        "/api/v1/sessions/solo",
        headers=learner.headers,
        json={
            "planned_minutes": 25,
            "subject": subject,
            "topic": topic,
        },
    )
    assert response.status_code == 201, response.text
    drain(client)
    return response.json()


def finish(client, learner, session, clock, db_engine):
    with Session(db_engine) as db:
        db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
        db.get(SessionParticipant, session["mine"]["id"]).active_seconds = 1200
        db.commit()
    clock.now += timedelta(minutes=20)
    response = client.post(f"/api/v1/sessions/{session['id']}/finish", headers=learner.headers)
    assert response.status_code == 200, response.text
    return response.json()


def open_quiz(client, learner, session, method="get"):
    pid = session["mine"]["id"]
    return getattr(client, method)(
        f"/api/v1/participants/{pid}/quiz" + ("/start" if method == "post" else ""),
        headers=learner.headers,
    )


def submit(client, learner, session, answers):
    return client.post(
        f"/api/v1/participants/{session['mine']['id']}/quiz/submit",
        headers=learner.headers,
        json={"answers": answers},
    )


def correct_answers(db_engine, quiz_id=None):
    with Session(db_engine) as db:
        query = select(QuizQuestion).order_by(QuizQuestion.position)
        if quiz_id:
            query = query.where(QuizQuestion.quiz_id == quiz_id)
        return [q.correct_index for q in db.scalars(query).all()]


def test_valid_ollama_request_shuffle_and_no_answers_before_submit(
    auth_client, actor, clock, db_engine, source, monkeypatch
):
    # Deterministic permutation verifies answer remapping rather than relying on chance.
    monkeypatch.setattr("app.quizzes.worker.secrets.SystemRandom.shuffle", lambda _, x: x.reverse())
    learner, stranger = actor(), actor()
    session = prepare(auth_client, learner)
    assert len(source.requests) == 1
    request, timeout = source.requests[0]
    assert request["model"] == "qwen2.5:7b-instruct" and request["stream"] is False
    assert request["format"]["properties"]["questions"]["minItems"] == 15
    assert request["options"] == {"temperature": 0.4} and timeout["read"] == 120
    assert "Mole concept" in request["messages"][1]["content"]
    assert "WAEC/NECO/JAMB" in request["messages"][1]["content"]
    assert open_quiz(auth_client, learner, session).status_code == 409
    finish(auth_client, learner, session, clock, db_engine)
    opened = open_quiz(auth_client, learner, session, "post")
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert (
        len(body["questions"]) == 15
        and body["questions"][0]["options"] == DOCUMENT["questions"][0]["options"][::-1]
    )
    assert "correct_index" not in opened.text and "explanation" not in opened.text
    assert open_quiz(auth_client, stranger, session).status_code == 403
    assert correct_answers(db_engine) == [3] * 15
    assert open_quiz(auth_client, learner, session).json()["started_at"] == body["started_at"]
    result = submit(auth_client, learner, session, [3] * 15)
    assert result.status_code == 200 and result.json()["correct_count"] == 15
    assert result.json()["questions"][0]["correct_index"] == 3
    assert "explanation" in result.json()["questions"][0]
    assert submit(auth_client, learner, session, [3] * 15).status_code == 200
    assert submit(auth_client, learner, session, [0] * 15).status_code == 409
    assert open_quiz(auth_client, learner, session).json()["status"] == "submitted"


def test_invalid_then_valid_retries_once_with_feedback(
    auth_client, actor, clock, db_engine, source
):
    source.responses = [{"questions": []}, valid_document()]
    learner = actor()
    session = prepare(auth_client, learner)
    assert len(source.requests) == 2
    assert "Your previous answer was invalid" in source.requests[1][0]["messages"][1]["content"]
    finish(auth_client, learner, session, clock, db_engine)
    assert open_quiz(auth_client, learner, session).json()["status"] == "ready"


@pytest.mark.parametrize("failure", ["invalid", "timeout", "bad_json"])
def test_two_failures_award_time_only_base_without_attempt(
    auth_client, actor, clock, db_engine, source, failure
):
    source.responses = (
        [{"questions": []}] * 2
        if failure == "invalid"
        else [httpx.ReadTimeout("offline")] * 2
        if failure == "timeout"
        else ["not json"] * 2
    )
    learner = actor()
    create(auth_client, learner)
    session = prepare(auth_client, learner)
    assert len(source.requests) == 2
    finished = finish(auth_client, learner, session, clock, db_engine)
    assert finished["mine"]["status"] == "completed"
    response = open_quiz(auth_client, learner, session)
    assert response.json()["status"] == "time_only" and response.json()["points"][0]["points"] == 8
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(QuizAttempt)) == 0
        assert db.scalar(select(func.count()).select_from(PointsLedger)) == 1


def test_seed_is_idempotent_and_exact_cache_precedes_llm(
    auth_client, actor, clock, db_engine, source
):
    async def seed():
        assert await seed_quizzes(auth_client.app.state.database) == 3
        assert await seed_quizzes(auth_client.app.state.database) == 0

    auth_client.portal.call(seed)
    learner = actor()
    session = prepare(auth_client, learner, subject=" CHEM ", topic="  MOLE   concept ")
    assert source.requests == []
    finish(auth_client, learner, session, clock, db_engine)
    quiz = open_quiz(auth_client, learner, session).json()
    assert quiz["source"] == "fallback" and not quiz["related_topic"]


def test_related_cache_after_llm_failure_stays_at_same_subject_level(
    auth_client, actor, clock, db_engine, source
):
    auth_client.portal.call(seed_quizzes, auth_client.app.state.database)
    source.responses = [{"questions": []}] * 2
    learner = actor()
    session = prepare(auth_client, learner, topic="Chemical calculations")
    assert len(source.requests) == 2
    finish(auth_client, learner, session, clock, db_engine)
    assert open_quiz(auth_client, learner, session).json()["related_topic"]
    source.responses = [{"questions": []}] * 2
    adult = actor(EducationLevel.OTHER)
    other = prepare(auth_client, adult)
    with Session(db_engine) as db:
        assert db.get(SessionParticipant, other["mine"]["id"]).quiz_status == "unavailable"


def test_user_never_repeats_an_attempted_variant(auth_client, actor, clock, db_engine, source):
    learner = actor()
    first = prepare(auth_client, learner)
    finish(auth_client, learner, first, clock, db_engine)
    first_quiz = open_quiz(auth_client, learner, first).json()
    second = prepare(auth_client, learner)
    finish(auth_client, learner, second, clock, db_engine)
    second_quiz = open_quiz(auth_client, learner, second).json()
    assert first_quiz["questions"][0]["id"] != second_quiz["questions"][0]["id"]
    assert len(source.requests) == 2


@pytest.mark.parametrize(
    "start_delay,submit_delay,accepted",
    [(0, 20, True), (0, 20.01, False), (15, 15, True), (15, 15.01, False), (30.01, 0, False)],
)
def test_both_quiz_deadlines_and_time_only_fallback(
    auth_client, actor, clock, db_engine, start_delay, submit_delay, accepted
):
    learner = actor()
    create(auth_client, learner)
    session = prepare(auth_client, learner)
    finish(auth_client, learner, session, clock, db_engine)
    clock.now += timedelta(minutes=start_delay)
    opened = open_quiz(auth_client, learner, session)
    if start_delay > 30:
        assert opened.status_code == 410
    else:
        assert opened.status_code == 200
        clock.now += timedelta(minutes=submit_delay)
        response = submit(auth_client, learner, session, correct_answers(db_engine))
        assert response.status_code == (200 if accepted else 410), response.text
    with Session(db_engine) as db:
        participant = db.get(SessionParticipant, session["mine"]["id"])
        assert participant.status == "completed"
        if not accepted:
            attempt = db.scalar(select(QuizAttempt))
            assert not attempt or not attempt.counts_for_baseline
            assert db.scalar(select(PointsLedger.points)) == 8


def test_validation_and_start_required_before_submission(auth_client, actor, clock, db_engine):
    learner = actor()
    session = prepare(auth_client, learner)
    finish(auth_client, learner, session, clock, db_engine)
    assert submit(auth_client, learner, session, [0] * 15).status_code == 409
    open_quiz(auth_client, learner, session)
    for answers in ([0] * 14, [0] * 16, [4] * 15, [True] * 15, ["0"] * 15):
        assert submit(auth_client, learner, session, answers).status_code == 422


def test_question_flags_require_submission_and_retire_after_three_unique_users(
    auth_client, actor, clock, db_engine, source
):
    learners = [actor() for _ in range(3)]
    ids = []
    question_id = None
    for learner in learners:
        session = prepare(auth_client, learner)
        finish(auth_client, learner, session, clock, db_engine)
        body = open_quiz(auth_client, learner, session).json()
        question_id = body["questions"][0]["id"]
        ids.append(session["mine"]["id"])
        path = f"/api/v1/questions/{question_id}/flags"
        assert (
            auth_client.post(path, headers=learner.headers, json={"reason": "unclear"}).status_code
            == 403
        )
        assert submit(auth_client, learner, session, correct_answers(db_engine)).status_code == 200
    assert len(source.requests) == 1
    for index, learner in enumerate(learners):
        path = f"/api/v1/questions/{question_id}/flags"
        response = auth_client.post(
            path, headers=learner.headers, json={"reason": "unclear", "note": "Check the wording."}
        )
        assert response.status_code == 201, response.text
        assert (
            auth_client.post(path, headers=learner.headers, json={"reason": "unclear"}).status_code
            == 409
        )
        with Session(db_engine) as db:
            question = db.get(QuizQuestion, question_id)
            assert question.flag_count == index + 1
            assert question.is_disabled == (index == 2)
            assert all(db.get(QuizAttempt, aid).score_pct == 100 for aid in ids)
    with Session(db_engine) as db:
        assert db.get(Quiz, question.quiz_id).status == "retired"


def test_inappropriate_flag_retires_immediately_and_excludes_variant(
    auth_client, actor, clock, db_engine, source
):
    learner = actor()
    session = prepare(auth_client, learner)
    finish(auth_client, learner, session, clock, db_engine)
    body = open_quiz(auth_client, learner, session).json()
    qid = body["questions"][0]["id"]
    submit(auth_client, learner, session, correct_answers(db_engine))
    assert (
        auth_client.post(
            f"/api/v1/questions/{qid}/flags",
            headers=learner.headers,
            json={"reason": "inappropriate"},
        ).status_code
        == 201
    )
    prepare(auth_client, actor())
    assert len(source.requests) == 2
    with Session(db_engine) as db:
        assert db.get(QuizQuestion, qid).is_disabled


def test_cache_keeps_five_active_variants_and_preserves_history(auth_client):
    async def fill():
        worker = auth_client.app.state.quizzes
        job = Job(
            cache_key("chemistry", "mole concept", "SS2"),
            "Chemistry",
            "Mole concept",
            "chemistry",
            "mole concept",
            EducationLevel.SS2,
        )
        async with worker.database(write=True) as db:
            for _ in range(6):
                await store_quiz(db, job, QuizDocument.model_validate(valid_document()), "test")
            await db.commit()
            variants = list((await db.scalars(select(Quiz).order_by(Quiz.id))).all())
            assert len(variants) == 6 and variants[0].status == QuizVariantStatus.RETIRED
            assert sum(q.status == "active" for q in variants) == 5

    auth_client.portal.call(fill)


def test_queue_deduplicates_matching_participants(auth_client, actor, source):
    learners = [actor() for _ in range(4)]

    async def hold():
        source.gate = asyncio.Event()

    auth_client.portal.call(hold)
    sessions = []
    for learner in learners:
        response = auth_client.post(
            "/api/v1/sessions/solo",
            headers=learner.headers,
            json={"planned_minutes": 25, "subject": "Chemistry", "topic": "Mole concept"},
        )
        sessions.append(response.json())

    async def release():
        source.gate.set()

    auth_client.portal.call(release)
    drain(auth_client)
    assert len(source.requests) == 1

    async def verify():
        async with auth_client.app.state.quizzes.database() as db:
            participants = (await db.scalars(select(SessionParticipant))).all()
            assert len({p.quiz_id for p in participants}) == 1
            assert all(p.quiz_status == "ready" for p in participants)

    auth_client.portal.call(verify)


@pytest.mark.parametrize(
    "change",
    [
        "size",
        "option_size",
        "duplicate_options",
        "empty_option",
        "index",
        "duplicate_questions",
        "banned_option",
        "content",
        "boolean_index",
    ],
)
def test_quiz_document_validation(change):
    document = valid_document()
    question = document["questions"][0]
    if change == "size":
        document["questions"].pop()
    elif change == "option_size":
        question["options"].pop()
    elif change == "duplicate_options":
        question["options"][1] = question["options"][0].upper() + ". "
    elif change == "empty_option":
        question["options"][0] = "   "
    elif change == "index":
        question["correct_index"] = 4
    elif change == "boolean_index":
        question["correct_index"] = True
    elif change == "duplicate_questions":
        document["questions"][1]["question"] = question["question"]
    elif change == "banned_option":
        question["options"][1] = "All of the above"
    else:
        question["explanation"] = "This contains pornography."
    with pytest.raises(ValidationError):
        QuizDocument.model_validate(document)


def test_all_level_descriptors_and_cache_separation():
    assert all(level_descriptor(level) for level in EducationLevel)
    assert "adult" in level_descriptor(EducationLevel.OTHER)
    assert cache_key("maths", "indices", "SS2") != cache_key("maths", "indices", "SS3")


def test_scheduled_start_enqueues_saved_participant_level(auth_client, actor, clock, source):
    learner = actor()
    group = create(auth_client, learner)
    starts = clock.now + timedelta(minutes=1)
    session = auth_client.post(
        f"/api/v1/groups/{group['id']}/sessions",
        headers=learner.headers,
        json={"planned_minutes": 25, "scheduled_at": starts.isoformat()},
    ).json()
    auth_client.post(
        f"/api/v1/sessions/{session['id']}/join",
        headers=learner.headers,
        json={"subject": "Chemistry", "topic": "Mole concept"},
    )
    drain(auth_client)
    assert source.requests == []
    auth_client.patch("/api/v1/users/me", headers=learner.headers, json={"level": "SS3"})
    clock.now = starts
    auth_client.portal.call(auth_client.app.state.presence.tick)
    drain(auth_client)
    assert len(source.requests) == 1
    assert "senior secondary year 2" in source.requests[0][0]["messages"][1]["content"]


def test_pending_returns_202_without_starting_an_attempt(
    auth_client, actor, clock, db_engine, source
):
    async def hold():
        source.gate = asyncio.Event()

    auth_client.portal.call(hold)
    learner = actor()
    session = auth_client.post(
        "/api/v1/sessions/solo",
        headers=learner.headers,
        json={"planned_minutes": 25, "subject": "Chemistry", "topic": "Mole concept"},
    ).json()
    finish(auth_client, learner, session, clock, db_engine)
    response = open_quiz(auth_client, learner, session)
    assert response.status_code == 202 and response.json()["status"] == "preparing"
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(QuizAttempt)) == 0

    async def release():
        source.gate.set()

    auth_client.portal.call(release)
    drain(auth_client)
    assert open_quiz(auth_client, learner, session).json()["status"] == "ready"


def test_one_flag_removes_variant_from_new_cache_assignments(
    auth_client, actor, clock, db_engine, source
):
    learner = actor()
    session = prepare(auth_client, learner)
    finish(auth_client, learner, session, clock, db_engine)
    qid = open_quiz(auth_client, learner, session).json()["questions"][0]["id"]
    submit(auth_client, learner, session, correct_answers(db_engine))
    auth_client.post(
        f"/api/v1/questions/{qid}/flags", headers=learner.headers, json={"reason": "unclear"}
    )
    prepare(auth_client, actor())
    assert len(source.requests) == 2
    with Session(db_engine) as db:
        assert not db.get(QuizQuestion, qid).is_disabled


def test_insufficient_time_never_earns_fallback_points(
    auth_client, actor, clock, db_engine, source
):
    source.responses = [{"questions": []}] * 2
    learner = actor()
    create(auth_client, learner)
    session = prepare(auth_client, learner)
    clock.now += timedelta(minutes=26)
    auth_client.portal.call(auth_client.app.state.presence.tick)
    assert open_quiz(auth_client, learner, session).status_code == 409
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(PointsLedger)) == 0
