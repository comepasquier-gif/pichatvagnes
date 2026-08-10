"""
bots.py (routes)
-----------------
API d'administration des bots PiChat.
"""

from typing import List

from fastapi import APIRouter, Request, HTTPException, status

from models.bot import BotCreate, BotPublic, BotToggle
from routes.rooms import require_admin
from services.bot_service import (
    list_bots,
    create_bot,
    set_bot_enabled,
    delete_bot,
    BotAlreadyExistsError,
    BotNotFoundError,
    InvalidBotNameError,
)

router = APIRouter()


@router.get("/api/admin/bots", response_model=List[BotPublic])
def get_bots(request: Request):
    require_admin(request)
    return list_bots()


@router.post("/api/admin/bots", response_model=BotPublic, status_code=status.HTTP_201_CREATED)
def add_bot(bot_data: BotCreate, request: Request):
    require_admin(request)

    try:
        return create_bot(bot_data.name, bot_data.response_template)
    except BotAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom est déjà utilisé par un utilisateur ou un bot.",
        )
    except InvalidBotNameError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


@router.patch("/api/admin/bots/{bot_id}", response_model=BotPublic)
def toggle_bot(bot_id: int, bot_data: BotToggle, request: Request):
    require_admin(request)

    try:
        return set_bot_enabled(bot_id, bot_data.enabled)
    except BotNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot introuvable.")


@router.delete("/api/admin/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_bot(bot_id: int, request: Request):
    require_admin(request)

    try:
        delete_bot(bot_id)
    except BotNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot introuvable.")
