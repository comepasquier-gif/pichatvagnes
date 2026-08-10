from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from connection_manager import manager
from routes.rooms import require_admin
from services.message_service import save_message
from services.room_service import get_default_room_id_for_user, user_can_access_room
from services.test_lab_service import (
    TestLabError,
    create_batch,
    delete_all_active_batches,
    delete_batch,
    diagnostics,
    list_batches,
    simulate_connections,
)

router = APIRouter()


class CreateBatchRequest(BaseModel):
    account_count: int = Field(default=20, ge=1, le=100)
    prefix: str = Field(default="test", min_length=1, max_length=12)
    password: str = Field(default="PiChatTest2026!", min_length=8, max_length=128)
    sample_data: bool = True
    include_staff: bool = True




class SimulateConnectionsRequest(BaseModel):
    count: int = Field(default=12, ge=2, le=100)
    batch_id: Optional[int] = None


class TestMessageRequest(BaseModel):
    room_id: Optional[int] = None
    content: str = Field(default="✅ Message de diagnostic : le bouton d'envoi et le serveur fonctionnent.", min_length=1, max_length=500)


@router.get("/api/admin/test-lab")
def test_lab_status(request: Request):
    require_admin(request)
    return {"batches": list_batches(), "diagnostics": diagnostics()}


@router.post("/api/admin/test-lab/batches")
def create_test_batch(data: CreateBatchRequest, request: Request):
    admin = require_admin(request)
    try:
        return create_batch(
            admin_id=int(admin["id"]),
            account_count=data.account_count,
            prefix=data.prefix,
            password=data.password,
            sample_data=data.sample_data,
            include_staff=data.include_staff,
        )
    except TestLabError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail="Création du lot impossible : %s" % error)


@router.delete("/api/admin/test-lab/batches/{batch_id}")
def remove_test_batch(batch_id: int, request: Request):
    require_admin(request)
    try:
        return delete_batch(batch_id)
    except TestLabError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.delete("/api/admin/test-lab/batches")
def remove_all_test_batches(request: Request):
    require_admin(request)
    return delete_all_active_batches()


@router.post("/api/admin/test-lab/simulate-connections")
def simulate_test_connections(data: SimulateConnectionsRequest, request: Request):
    require_admin(request)
    try:
        return simulate_connections(data.count, data.batch_id)
    except TestLabError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/admin/test-lab/send-message")
async def send_test_message(data: TestMessageRequest, request: Request):
    admin = require_admin(request)
    room_id = data.room_id
    if room_id is None or not user_can_access_room(admin, room_id):
        room_id = get_default_room_id_for_user(admin)
    if room_id is None:
        raise HTTPException(status_code=422, detail="Aucun salon disponible.")
    message = save_message(int(room_id), int(admin["id"]), data.content.strip())
    await manager.broadcast_to_room(int(room_id), {"type": "new_message", "message": message})
    return {"ok": True, "room_id": int(room_id), "message": message}
