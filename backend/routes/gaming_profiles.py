from fastapi import APIRouter, HTTPException, Request

from config import SESSION_COOKIE_NAME
from models.gaming_profile import BadgeAward, BadgeCreate, BadgeUpdate, GamingProfilesUpdate
from routes.rooms import require_admin
from services.auth_service import get_user_from_session
from services.admin_user_service import log_admin_action
from services.community_service import get_feature_settings, public_profile
from services.gaming_profile_service import (
    award_badge,
    create_badge,
    delete_game_profile,
    get_game_catalog,
    get_user_badges,
    list_badge_catalog,
    list_games,
    replace_games,
    revoke_badge,
    update_badge,
)

router = APIRouter()


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Non connecté.")
    if not get_feature_settings().get("gaming_profiles_enabled", True):
        raise HTTPException(status_code=403, detail="Profils gaming désactivés.")
    return user


@router.get("/api/gaming/catalog")
def gaming_catalog(request: Request):
    current_user(request)
    return get_game_catalog()


@router.get("/api/profile/me/games")
def my_games(request: Request):
    user = current_user(request)
    return list_games(user["id"], include_private=True)


@router.put("/api/profile/me/games")
def save_my_games(data: GamingProfilesUpdate, request: Request):
    user = current_user(request)
    games = replace_games(user["id"], [item.model_dump() for item in data.games])
    return {"games": games, "profile": public_profile(user["id"])}




@router.get("/api/admin/users/{user_id}/gaming-profile")
def admin_user_gaming_profile(user_id: int, request: Request):
    require_admin(request)
    return {"games": list_games(user_id, include_private=True), "badges": get_user_badges(user_id, active_only=False)}


@router.delete("/api/admin/users/{user_id}/games/{game_profile_id}")
def admin_delete_game_profile(user_id: int, game_profile_id: int, request: Request):
    admin = require_admin(request)
    try:
        games = delete_game_profile(user_id, game_profile_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    log_admin_action(admin["id"], "gaming_profile_delete", str(user_id), str(game_profile_id))
    return {"user_id": user_id, "games": games}


@router.get("/api/admin/badges")
def admin_badges(request: Request):
    require_admin(request)
    return list_badge_catalog(include_inactive=True)


@router.post("/api/admin/badges")
def admin_create_badge(data: BadgeCreate, request: Request):
    admin = require_admin(request)
    try:
        result = create_badge(data.model_dump())
    except Exception as error:
        if "UNIQUE" in str(error).upper():
            raise HTTPException(status_code=409, detail="Ce code de badge existe déjà.")
        raise HTTPException(status_code=422, detail=str(error))
    log_admin_action(admin["id"], "badge_create", result["code"], result["name"])
    return result


@router.patch("/api/admin/badges/{badge_id}")
def admin_update_badge(badge_id: int, data: BadgeUpdate, request: Request):
    admin = require_admin(request)
    try:
        result = update_badge(badge_id, data.model_dump(exclude_none=True))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    log_admin_action(admin["id"], "badge_update", result["code"], result["name"])
    return result


@router.get("/api/admin/users/{user_id}/badges")
def admin_user_badges(user_id: int, request: Request):
    require_admin(request)
    return get_user_badges(user_id, active_only=False)


@router.post("/api/admin/users/{user_id}/badges/{badge_id}")
def admin_award_badge(user_id: int, badge_id: int, data: BadgeAward, request: Request):
    admin = require_admin(request)
    try:
        result = award_badge(user_id, badge_id, admin["id"], data.reason, data.showcased)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    log_admin_action(admin["id"], "badge_award", str(user_id), str(badge_id))
    return result


@router.delete("/api/admin/users/{user_id}/badges/{badge_id}")
def admin_revoke_badge(user_id: int, badge_id: int, request: Request):
    admin = require_admin(request)
    try:
        result = revoke_badge(user_id, badge_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    log_admin_action(admin["id"], "badge_revoke", str(user_id), str(badge_id))
    return result
