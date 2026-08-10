from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from routes.rooms import get_current_user_or_401
from services.pibrawl_registry import get_head_path, load_roster

router = APIRouter()


@router.get("/api/pibrawl/roster")
def pibrawl_roster(request: Request):
    user = get_current_user_or_401(request)
    fighters, errors = load_roster()
    return {
        "version": "1.0",
        "engine": "PiBrawl Open Arena",
        "license": "MIT (moteur PiBrawl ajouté à PiChat)",
        "player": {"id": int(user["id"]), "username": user.get("username") or "joueur"},
        "fighters": fighters,
        "loader_errors": errors,
        "plugin_format": "personnages/<id>/fighter.py + head.png",
        "safe_python": True,
    }


@router.get("/api/pibrawl/characters/{fighter_id}/head", include_in_schema=False)
def pibrawl_head(fighter_id: str):
    try:
        path = get_head_path(fighter_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Combattant introuvable")
    suffix = path.suffix.lower()
    media = {
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media, headers={"Cache-Control": "public, max-age=300"})
