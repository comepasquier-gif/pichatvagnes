from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, Query
from config import SESSION_COOKIE_NAME
from models.v21 import EditMessageRequest
from services.auth_service import get_user_from_session
from services.community_service import get_feature_settings
from services.message_service import (
    get_message, edit_text_message, delete_message, search_room_messages,
    list_pinned_messages, toggle_pin,
)
from services.room_service import user_can_access_room
from permissions import moderator_has_permission
from database import get_db_cursor
from connection_manager import manager
from services.final_packs_service import can_edit_own_message, can_delete_own_message

router = APIRouter()


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Non connecté.")
    return user


def can_moderate_room(user: dict, room_id: int) -> bool:
    if user.get("is_admin"):
        return True
    if not user.get("is_moderator") or not moderator_has_permission(user, "messages_delete"):
        return False
    with get_db_cursor() as c:
        room = c.execute("SELECT class_code FROM rooms WHERE id=?", (room_id,)).fetchone()
    return bool(room and room["class_code"] and room["class_code"] == user.get("moderator_class_code"))


@router.get("/api/messages/search")
def search_messages(
    request: Request,
    room_id: int = Query(ge=1),
    q: str = Query(min_length=2, max_length=200),
    author: str = Query(default="", max_length=32),
    limit: int = Query(default=80, ge=1, le=200),
):
    user = current_user(request)
    if not get_feature_settings().get("search_enabled", True):
        raise HTTPException(status_code=403, detail="Recherche désactivée.")
    if not user_can_access_room(user, room_id):
        raise HTTPException(status_code=403, detail="Accès refusé.")
    return {"messages": search_room_messages(room_id, q, limit, author), "query": q}


@router.get("/api/rooms/{room_id}/pins")
def room_pins(room_id: int, request: Request):
    user = current_user(request)
    if not get_feature_settings().get("pins_enabled", True):
        raise HTTPException(status_code=403, detail="Épingles désactivées.")
    if not user_can_access_room(user, room_id):
        raise HTTPException(status_code=403, detail="Accès refusé.")
    return {"messages": list_pinned_messages(room_id)}


@router.patch("/api/messages/{message_id}")
async def edit_message(message_id: int, data: EditMessageRequest, request: Request):
    user = current_user(request)
    if not get_feature_settings().get("message_edit_enabled", True):
        raise HTTPException(status_code=403, detail="Modification désactivée.")
    message = get_message(message_id)
    if not message or not user_can_access_room(user, message["room_id"]):
        raise HTTPException(status_code=404, detail="Message introuvable.")
    own = int(message["user_id"]) == int(user["id"])
    if own and not user.get("is_admin") and not can_edit_own_message(message.get("created_at")):
        raise HTTPException(status_code=403, detail="Le délai de modification de ce message est dépassé.")
    try:
        updated = edit_text_message(message_id, user["id"], data.content, is_admin=bool(user.get("is_admin")))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await manager.broadcast_to_room(message["room_id"], {"type": "message_updated", "message": updated})
    return updated


@router.delete("/api/messages/{message_id}")
async def remove_message(message_id: int, request: Request):
    user = current_user(request)
    message = get_message(message_id)
    if not message or not user_can_access_room(user, message["room_id"]):
        raise HTTPException(status_code=404, detail="Message introuvable.")
    own = int(message["user_id"]) == int(user["id"])
    privileged = bool(user.get("is_admin")) or can_moderate_room(user, message["room_id"])
    if not own and not privileged:
        raise HTTPException(status_code=403, detail="Tu ne peux pas supprimer ce message.")
    if own and not privileged and not can_delete_own_message(message.get("created_at")):
        raise HTTPException(status_code=403, detail="Le délai de suppression de ce message est dépassé.")
    if not delete_message(message_id):
        raise HTTPException(status_code=404, detail="Message introuvable.")
    await manager.broadcast_to_room(message["room_id"], {"type": "message_deleted", "message_id": message_id})
    return {"deleted": True, "message_id": message_id}


@router.post("/api/messages/{message_id}/pin")
async def pin_message(message_id: int, request: Request):
    user = current_user(request)
    if not get_feature_settings().get("pins_enabled", True):
        raise HTTPException(status_code=403, detail="Épingles désactivées.")
    message = get_message(message_id)
    if not message or not user_can_access_room(user, message["room_id"]):
        raise HTTPException(status_code=404, detail="Message introuvable.")
    if not can_moderate_room(user, message["room_id"]):
        raise HTTPException(status_code=403, detail="Réservé aux admins ou modos autorisés de la classe.")
    updated = toggle_pin(message_id, user["id"])
    await manager.broadcast_to_room(message["room_id"], {"type": "message_updated", "message": updated})
    return updated
