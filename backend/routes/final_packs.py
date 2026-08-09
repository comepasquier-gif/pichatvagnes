from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from config import SESSION_COOKIE_NAME
from services.auth_service import get_user_from_session
from services.final_packs_service import (
    auto_backup_status,
    block_user,
    cancel_scheduled_message,
    create_scheduled_message,
    get_final_pack_settings,
    list_scheduled_messages,
    list_user_sessions,
    remove_friend,
    respond_friend_request,
    revoke_other_sessions,
    revoke_user_session,
    run_auto_backup,
    search_social_users,
    send_friend_request,
    social_overview,
    unblock_user,
    update_final_pack_settings,
)

router = APIRouter()


class ScheduleMessageRequest(BaseModel):
    room_id: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=2000)
    send_at: str = Field(min_length=8, max_length=80)
    reply_to_id: Optional[int] = Field(default=None, ge=1)


class FriendRequestBody(BaseModel):
    user_id: int = Field(ge=1)


class FriendResponseBody(BaseModel):
    accept: bool


class FinalPackSettingsBody(BaseModel):
    scheduled_messages_enabled: bool = True
    social_enabled: bool = True
    session_manager_enabled: bool = True
    auto_backup_enabled: bool = False
    scheduled_max_days: int = Field(default=30, ge=1, le=365)
    edit_window_minutes: int = Field(default=1440, ge=0, le=525600)
    delete_window_minutes: int = Field(default=60, ge=0, le=525600)
    backup_interval_hours: int = Field(default=24, ge=1, le=720)
    backup_retention: int = Field(default=7, ge=1, le=60)


def _current(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Non connecté.")
    return user


def _admin(request: Request) -> dict:
    user = _current(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs.")
    return user


def _error(exc: Exception):
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc))
    raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api/final-packs/status")
def final_pack_status(request: Request):
    _current(request)
    return {"settings": get_final_pack_settings()}


@router.get("/api/scheduled-messages")
def scheduled_list(request: Request, include_finished: bool = Query(default=False)):
    user = _current(request)
    return {"messages": list_scheduled_messages(user["id"], include_finished=include_finished)}


@router.post("/api/scheduled-messages")
def scheduled_create(data: ScheduleMessageRequest, request: Request):
    user = _current(request)
    try:
        return create_scheduled_message(user, data.room_id, data.content, data.send_at, data.reply_to_id)
    except Exception as exc:
        _error(exc)


@router.delete("/api/scheduled-messages/{scheduled_id}")
def scheduled_cancel(scheduled_id: int, request: Request):
    user = _current(request)
    try:
        if not cancel_scheduled_message(scheduled_id, user["id"], bool(user.get("is_admin"))):
            raise HTTPException(status_code=404, detail="Message programmé introuvable.")
        return {"cancelled": True, "id": scheduled_id}
    except HTTPException:
        raise
    except Exception as exc:
        _error(exc)


@router.get("/api/social")
def social_home(request: Request):
    user = _current(request)
    if not get_final_pack_settings()["social_enabled"]:
        raise HTTPException(status_code=403, detail="Le pack Social est désactivé.")
    return social_overview(user["id"])


@router.get("/api/social/search")
def social_search(request: Request, q: str = Query(min_length=2, max_length=40)):
    user = _current(request)
    return {"users": search_social_users(user, q)}


@router.post("/api/social/request")
def social_request(data: FriendRequestBody, request: Request):
    user = _current(request)
    try:
        return send_friend_request(user, data.user_id)
    except Exception as exc:
        _error(exc)


@router.post("/api/social/requests/{friendship_id}/respond")
def social_respond(friendship_id: int, data: FriendResponseBody, request: Request):
    user = _current(request)
    try:
        return respond_friend_request(user["id"], friendship_id, data.accept)
    except Exception as exc:
        _error(exc)


@router.delete("/api/social/friends/{target_id}")
def social_remove(target_id: int, request: Request):
    user = _current(request)
    return {"removed": remove_friend(user["id"], target_id)}


@router.post("/api/social/block/{target_id}")
def social_block(target_id: int, request: Request):
    user = _current(request)
    try:
        block_user(user["id"], target_id)
        return {"blocked": True}
    except Exception as exc:
        _error(exc)


@router.delete("/api/social/block/{target_id}")
def social_unblock(target_id: int, request: Request):
    user = _current(request)
    return {"unblocked": unblock_user(user["id"], target_id)}


@router.get("/api/my-sessions")
def my_sessions(request: Request):
    user = _current(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        return {"sessions": list_user_sessions(user["id"], token)}
    except Exception as exc:
        _error(exc)


@router.delete("/api/my-sessions/{session_id}")
def remove_session(session_id: int, request: Request):
    user = _current(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        return {"revoked": revoke_user_session(user["id"], session_id, token)}
    except Exception as exc:
        _error(exc)


@router.delete("/api/my-sessions")
def remove_other_sessions(request: Request):
    user = _current(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return {"revoked": revoke_other_sessions(user["id"], token)}


@router.get("/api/admin/final-packs")
def admin_final_packs(request: Request):
    _admin(request)
    settings = get_final_pack_settings()
    social = {"friends": 0, "pending": 0}
    scheduled = {"pending": 0, "failed": 0}
    sessions = 0
    from database import get_db_cursor
    with get_db_cursor() as cursor:
        social["friends"] = int(cursor.execute("SELECT COUNT(*) AS n FROM friendships WHERE status='accepted'").fetchone()["n"])
        social["pending"] = int(cursor.execute("SELECT COUNT(*) AS n FROM friendships WHERE status='pending'").fetchone()["n"])
        scheduled["pending"] = int(cursor.execute("SELECT COUNT(*) AS n FROM scheduled_messages WHERE status='pending'").fetchone()["n"])
        scheduled["failed"] = int(cursor.execute("SELECT COUNT(*) AS n FROM scheduled_messages WHERE status='failed'").fetchone()["n"])
        sessions = int(cursor.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"])
    return {
        "settings": settings,
        "stats": {"social": social, "scheduled": scheduled, "sessions": sessions, "backups": auto_backup_status()},
    }


@router.patch("/api/admin/final-packs")
def admin_update_final_packs(data: FinalPackSettingsBody, request: Request):
    _admin(request)
    return {"settings": update_final_pack_settings(data.model_dump())}


@router.post("/api/admin/final-packs/backup-now")
def admin_backup_now(request: Request):
    _admin(request)
    try:
        result = run_auto_backup(force=True)
        return {"backup": result, "status": auto_backup_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Sauvegarde impossible : " + str(exc))
