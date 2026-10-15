from fastapi import APIRouter, Request

from app.api.groups import DB, Learner
from app.models import SessionParticipant, StudySession
from app.services.focus import SummaryInput, comparison, own_summary, personal, save_summary
from app.services.groups import fail
from app.services.sessions import participant_for

router = APIRouter()


def enabled(request):
    if not request.app.state.settings.focus_tracker_enabled:
        fail("focus_disabled", "Focus Tracker is switched off.", 404)


async def owner(db, participant_id, user_id):
    p = await db.get(SessionParticipant, participant_id)
    if not p or p.user_id != user_id:
        fail("not_found", "This participation was not found.", 404)
    return p


@router.get("/features")
async def features(request: Request):
    return {"focus_tracker_enabled": request.app.state.settings.focus_tracker_enabled}


@router.post("/participants/{participant_id}/focus-summary", status_code=201)
async def post_summary(
    participant_id: int, data: SummaryInput, db: DB, user: Learner, request: Request
):
    enabled(request)
    p = await owner(db, participant_id, user.id)
    session = await db.get(StudySession, p.session_id)
    row = await save_summary(db, session, p, data, request.app.state.clock())
    await db.commit()
    return {"mine": personal(row)}


@router.get("/participants/{participant_id}/focus-summary")
async def get_summary(participant_id: int, db: DB, user: Learner, request: Request):
    enabled(request)
    p = await owner(db, participant_id, user.id)
    return {"mine": personal(await own_summary(db, p.id))}


@router.get("/sessions/{session_id}/focus-comparison")
async def get_comparison(session_id: int, db: DB, user: Learner, request: Request):
    enabled(request)
    p = await participant_for(db, session_id, user.id)
    if not p:
        fail("not_found", "This session was not found.", 404)
    session = await db.get(StudySession, session_id)
    return await comparison(db, session, p, request.app.state.clock())
