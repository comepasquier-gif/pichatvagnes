from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from models.moderation import AutoModSettingsUpdate, AutoModDecision
from routes.rooms import require_admin, get_current_user_or_401
from permissions import require_role, require_moderator_permission
from services.automod_service import (
    get_automod_settings,
    set_automod_settings,
    list_automod_incidents,
    decide_incident,
    clear_user_automod_points,
)
from database import get_db_cursor

router = APIRouter()


def require_automod_reviewer(request: Request):
    user = get_current_user_or_401(request)
    require_role(user, "moderator")
    if not user.get("is_admin"):
        require_moderator_permission(user, "automod_review")
    return user


def filter_incidents_for_actor(actor: dict, incidents: list[dict]) -> list[dict]:
    if actor.get("is_admin"):
        return incidents
    class_code = actor.get("moderator_class_code")
    return [item for item in incidents if item.get("class_code") == class_code]


def ensure_target_in_scope(actor: dict, user_id: int) -> None:
    if actor.get("is_admin"):
        return
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT class_code,is_admin,is_moderator,is_bot FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    if bool(row["is_admin"]) or bool(row["is_moderator"]) or bool(row["is_bot"]):
        raise HTTPException(status_code=403, detail="Ce compte est protégé.")
    if row["class_code"] != actor.get("moderator_class_code"):
        raise HTTPException(status_code=403, detail="Cet utilisateur appartient à une autre classe.")


@router.get("/api/admin/automod")
def automod_settings(request: Request):
    require_admin(request)
    return get_automod_settings()


@router.patch("/api/admin/automod")
def update_automod(data: AutoModSettingsUpdate, request: Request):
    require_admin(request)
    try:
        return set_automod_settings(data.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/api/admin/automod/incidents")
def automod_incidents(request: Request, status: str = "open", limit: int = 200):
    require_admin(request)
    return list_automod_incidents(limit=limit, status=status)


@router.post("/api/admin/automod/incidents/{incident_id}")
def review_automod_incident(incident_id: int, data: AutoModDecision, request: Request):
    admin = require_admin(request)
    try:
        ok = decide_incident(incident_id, admin["id"], data.status, data.note)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if not ok:
        raise HTTPException(status_code=404, detail="Incident introuvable.")
    return {"ok": True}


@router.post("/api/admin/automod/users/{user_id}/reset-points")
def reset_automod_points(user_id: int, request: Request):
    admin = require_admin(request)
    return {"updated": clear_user_automod_points(user_id, admin["id"])}


# Version limitée aux permissions et à la classe du modérateur.
@router.get("/api/moderation/automod/incidents")
def moderation_automod_incidents(request: Request, status: str = "open", limit: int = 200):
    actor = require_automod_reviewer(request)
    incidents = list_automod_incidents(limit=limit, status=status)
    return filter_incidents_for_actor(actor, incidents)


@router.post("/api/moderation/automod/incidents/{incident_id}")
def moderation_review_automod_incident(incident_id: int, data: AutoModDecision, request: Request):
    actor = require_automod_reviewer(request)
    incidents = filter_incidents_for_actor(actor, list_automod_incidents(limit=500, status="all"))
    if not any(item["id"] == incident_id for item in incidents):
        raise HTTPException(status_code=404, detail="Incident introuvable dans ta classe.")
    try:
        ok = decide_incident(incident_id, actor["id"], data.status, data.note)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if not ok:
        raise HTTPException(status_code=404, detail="Incident introuvable.")
    return {"ok": True}


@router.post("/api/moderation/automod/users/{user_id}/reset-points")
def moderation_reset_automod_points(user_id: int, request: Request):
    actor = require_automod_reviewer(request)
    ensure_target_in_scope(actor, user_id)
    return {"updated": clear_user_automod_points(user_id, actor["id"])}
