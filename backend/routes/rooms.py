from typing import List
from fastapi import APIRouter, Request, HTTPException, status

from config import SESSION_COOKIE_NAME
from models.room import RoomCreate, RoomPublic
from permissions import require_role
from services.auth_service import get_user_from_session
from services.room_service import list_rooms, create_room, delete_room, RoomAlreadyExistsError, RoomNotFoundError
from services.class_service import InvalidClassCodeError

router = APIRouter()


def get_current_user_or_401(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Non connecté ou accès retiré.")
    return user


def require_admin(request: Request) -> dict:
    user = get_current_user_or_401(request)
    require_role(user, "admin")
    return user


@router.get("/api/rooms", response_model=List[RoomPublic])
def get_rooms(request: Request):
    user = get_current_user_or_401(request)
    return list_rooms(user)


@router.post("/api/admin/rooms", response_model=RoomPublic, status_code=201)
def add_room(room_data: RoomCreate, request: Request):
    require_admin(request)
    try:
        return create_room(room_data.name, room_data.class_code)
    except RoomAlreadyExistsError:
        raise HTTPException(status_code=409, detail="Un salon avec ce nom existe déjà.")
    except InvalidClassCodeError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.delete("/api/admin/rooms/{room_id}", status_code=204)
def remove_room(room_id: int, request: Request):
    require_admin(request)
    try:
        delete_room(room_id)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Ce salon n'existe pas.")
