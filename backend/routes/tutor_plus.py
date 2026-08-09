from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from config import SESSION_COOKIE_NAME
from services.auth_service import get_user_from_session
from services.community_service import get_feature_settings
from models.v21 import TutorPlusRequest, StudySetCreateRequest, StudyAttemptRequest
from services.tutor_plus_service import (
    ask_and_record, list_history, toggle_favorite, delete_history,
    create_study_set, get_study_set, list_study_sets, delete_study_set,
    record_attempt, tutor_dashboard,
)

router = APIRouter()


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Non connecté.")
    if not get_feature_settings().get("tutor_plus_enabled", True):
        raise HTTPException(status_code=403, detail="PiTutor+ est désactivé.")
    return user


@router.post("/api/tutor/v2/ask")
async def tutor_plus_ask(data: TutorPlusRequest, request: Request):
    user = current_user(request)
    return await ask_and_record(data.subject, data.mode, data.prompt, data.student_answer, user, data.difficulty, data.count)


@router.get("/api/tutor/v2/dashboard")
def tutor_plus_dashboard(request: Request):
    user = current_user(request)
    return tutor_dashboard(user["id"])


@router.get("/api/tutor/v2/history")
def tutor_plus_history(request: Request):
    user = current_user(request)
    return list_history(user["id"])


@router.post("/api/tutor/v2/history/{history_id}/favorite")
def tutor_plus_favorite(history_id: int, request: Request):
    user = current_user(request)
    value = toggle_favorite(user["id"], history_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
    return {"favorite": value}


@router.delete("/api/tutor/v2/history/{history_id}")
def tutor_plus_delete_history(history_id: int, request: Request):
    user = current_user(request)
    if not delete_history(user["id"], history_id):
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
    return {"deleted": True}


@router.get("/api/tutor/v2/sets")
def tutor_sets(request: Request):
    user = current_user(request)
    return list_study_sets(user["id"])


@router.post("/api/tutor/v2/sets")
def tutor_create_set(data: StudySetCreateRequest, request: Request):
    user = current_user(request)
    return create_study_set(user["id"], data.title, data.subject, data.kind, data.items)


@router.get("/api/tutor/v2/sets/{set_id}")
def tutor_get_set(set_id: int, request: Request):
    user = current_user(request)
    result = get_study_set(user["id"], set_id)
    if not result:
        raise HTTPException(status_code=404, detail="Fiche introuvable.")
    return result


@router.delete("/api/tutor/v2/sets/{set_id}")
def tutor_delete_set(set_id: int, request: Request):
    user = current_user(request)
    if not delete_study_set(user["id"], set_id):
        raise HTTPException(status_code=404, detail="Fiche introuvable.")
    return {"deleted": True}


@router.post("/api/tutor/v2/sets/{set_id}/attempt")
def tutor_attempt(set_id: int, data: StudyAttemptRequest, request: Request):
    user = current_user(request)
    result = record_attempt(user["id"], set_id, data.score, data.total, data.answers)
    if not result:
        raise HTTPException(status_code=404, detail="Fiche introuvable.")
    return result
