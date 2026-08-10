from fastapi import APIRouter, HTTPException, Query, Request

from config import SESSION_COOKIE_NAME
from models.arcade import ArcadeActionRequest, ArcadeSettingsUpdate
from routes.rooms import require_admin
from services.admin_user_service import log_admin_action
from services.arcade_service import (
    admin_overview,
    dashboard,
    get_arcade_settings,
    play_action,
    start_game,
    update_arcade_settings,
)
from services.auth_service import get_user_from_session
from services.community_service import get_feature_settings

router = APIRouter()


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Non connecté.")
    features = get_feature_settings()
    if not features.get("arcade_enabled", True):
        raise HTTPException(status_code=403, detail="L'Arcade est désactivée.")
    if not get_arcade_settings().get("enabled", True):
        raise HTTPException(status_code=403, detail="L'Arcade est désactivée par l'administration.")
    return user


@router.get("/api/arcade/dashboard")
def arcade_dashboard(request: Request, game: str = Query(default="clicker", max_length=24)):
    user = current_user(request)
    return dashboard(user["id"], game)


@router.post("/api/arcade/start/{game_key}")
def arcade_start(game_key: str, request: Request):
    user = current_user(request)
    try:
        return start_game(user["id"], game_key)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/arcade/sessions/{session_id}/action")
def arcade_action(session_id: str, data: ArcadeActionRequest, request: Request):
    user = current_user(request)
    try:
        return play_action(user["id"], session_id, data.model_dump())
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/api/admin/arcade")
def admin_arcade(request: Request):
    require_admin(request)
    return admin_overview()


@router.patch("/api/admin/arcade/settings")
def admin_arcade_settings(data: ArcadeSettingsUpdate, request: Request):
    admin = require_admin(request)
    try:
        settings = update_arcade_settings(data.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    log_admin_action(admin["id"], "arcade_settings", "arcade", str(settings))
    return settings
