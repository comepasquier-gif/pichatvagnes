from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from connection_manager import manager
from routes.rooms import get_current_user_or_401
from services.code_lab_service import create_code_message, CodeLabError
from services.community_service import get_feature_settings
from services.pycoin_service import get_economy_settings
from services.room_service import user_can_access_room

router = APIRouter()


class CodeGenerationRequest(BaseModel):
    room_id: int
    prompt: str = Field(min_length=3, max_length=2000)
    title: str = Field(default="Mini-code Python", max_length=80)


@router.get("/api/code-lab/status")
def code_lab_status(request: Request):
    get_current_user_or_401(request)
    settings = get_feature_settings()
    return {"enabled": bool(settings.get("code_lab_enabled")), "cost": get_economy_settings()["code_cost"], "auto_execute": False}


@router.post("/api/code-lab/generate")
async def generate_code(data: CodeGenerationRequest, request: Request):
    user = get_current_user_or_401(request)
    if not get_feature_settings().get("code_lab_enabled"):
        raise HTTPException(status_code=403, detail="PiCode est désactivé.")
    if not user_can_access_room(user, data.room_id):
        raise HTTPException(status_code=403, detail="Tu n'as pas accès à ce salon.")
    try:
        message = await create_code_message(data.room_id, user, data.prompt, data.title)
    except CodeLabError as error:
        raise HTTPException(status_code=422, detail=str(error))
    await manager.broadcast_to_room(data.room_id, {"type": "new_message", "message": message})
    return message
