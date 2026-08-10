from __future__ import annotations

from pathlib import Path
import re
import uuid

from fastapi import APIRouter, Request, HTTPException, Query, UploadFile, File

from config import SESSION_COOKIE_NAME, MAX_UPLOAD_BYTES
from services.auth_service import get_user_from_session
from services.message_service import get_room_history, has_older_room_messages, save_message
from services.room_service import user_can_access_room, get_default_room_id_for_user
from services.moderation_service import restriction_status
from connection_manager import manager
from services.storage_service import put_object, StorageError

router = APIRouter()

ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".txt", ".md", ".csv",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp",
    ".zip",
}


def _current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Non connecté ou accès retiré.")
    return user


@router.get("/api/messages/history")
def get_history(
    request: Request,
    room_id: int = Query(default=None),
    before_id: int = Query(default=None, ge=1),
    limit: int = Query(default=60, ge=20, le=100),
):
    user = _current_user(request)

    if room_id is None or not user_can_access_room(user, room_id):
        room_id = get_default_room_id_for_user(user)
    if room_id is None:
        return {"room_id": None, "messages": [], "has_more": False, "oldest_id": None}
    if not user_can_access_room(user, room_id):
        raise HTTPException(status_code=403, detail="Ce serveur appartient à une autre classe.")

    messages = get_room_history(room_id, limit=limit, before_id=before_id)
    oldest_id = messages[0]["id"] if messages else before_id
    return {
        "room_id": room_id,
        "messages": messages,
        "has_more": has_older_room_messages(room_id, oldest_id),
        "oldest_id": oldest_id,
    }


@router.post("/api/rooms/{room_id}/files")
async def upload_room_file(room_id: int, request: Request, file: UploadFile = File(...)):
    """Envoie un fichier dans un salon sans autoriser les exécutables/scripts."""
    user = _current_user(request)
    if not user_can_access_room(user, room_id):
        raise HTTPException(status_code=403, detail="Tu n'as pas accès à ce salon.")
    restriction = restriction_status(user["id"])
    if restriction and restriction.get("is_muted"):
        raise HTTPException(status_code=403, detail="Tu es en mode muet et ne peux pas envoyer de fichier.")

    original_name = Path(file.filename or "fichier").name[:180]
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Type de fichier refusé. Formats autorisés : images, PDF, documents Office, texte et ZIP.",
        )

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux : maximum 12 Mo.")
    if not data:
        raise HTTPException(status_code=422, detail="Le fichier est vide.")

    try:
        stored = put_object(data, original_name, (file.content_type or "application/octet-stream")[:120], user["id"], "chat")
    except StorageError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    message = save_message(
        room_id,
        user["id"],
        f"📎 {original_name}",
        message_type="file",
        metadata={
            "name": original_name,
            "url": stored["url"],
            "mime": stored["mime"],
            "size": stored["size"],
            "sha256": stored["sha256"],
        },
    )
    await manager.broadcast_to_room(room_id, {"type": "new_message", "message": message})
    return message
