from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from config import SESSION_COOKIE_NAME
from services.auth_service import get_user_from_session
from services.community_service import get_feature_settings
from services.direct_message_service import (
    users_available_for_dm, list_conversations, direct_history, send_direct_message,
    edit_direct_message, delete_direct_message, can_dm,
)
from models.v21 import DirectMessageRequest, EditMessageRequest
from connection_manager import manager

router = APIRouter()


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Non connecté.")
    if not get_feature_settings().get("direct_messages_enabled", True):
        raise HTTPException(status_code=403, detail="Messages privés désactivés.")
    return user


@router.get("/api/dm/users")
def dm_users(request: Request):
    return users_available_for_dm(current_user(request))


@router.get("/api/dm/conversations")
def dm_conversations(request: Request):
    user = current_user(request)
    return list_conversations(user["id"])


@router.get("/api/dm/{other_id}/messages")
def dm_history(other_id: int, request: Request, before_id: Optional[int] = Query(default=None, ge=1), limit: int = Query(default=60, ge=10, le=100)):
    user = current_user(request)
    if not can_dm(user, other_id):
        raise HTTPException(status_code=403, detail="Conversation inaccessible.")
    return {"messages": direct_history(user["id"], other_id, before_id, limit)}


@router.post("/api/dm/{receiver_id}/messages")
async def dm_send(receiver_id: int, data: DirectMessageRequest, request: Request):
    user = current_user(request)
    try:
        message = send_direct_message(user, receiver_id, data.content, data.reply_to_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await manager.send_to_user(receiver_id, {"type": "direct_message", "message": message})
    return message


@router.patch("/api/dm/messages/{message_id}")
async def dm_edit(message_id: int, data: EditMessageRequest, request: Request):
    user = current_user(request)
    try:
        message = edit_direct_message(message_id, user["id"], data.content)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not message:
        raise HTTPException(status_code=404, detail="Message introuvable.")
    other = message["receiver_id"] if message["sender_id"] == user["id"] else message["sender_id"]
    await manager.send_to_user(other, {"type": "direct_message_updated", "message": message})
    return message


@router.delete("/api/dm/messages/{message_id}")
async def dm_delete(message_id: int, request: Request):
    user = current_user(request)
    try:
        ok = delete_direct_message(message_id, user["id"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Message introuvable.")
    return {"deleted": True, "message_id": message_id}
