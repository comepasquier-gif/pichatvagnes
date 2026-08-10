from fastapi import APIRouter, Request

from routes.rooms import require_admin
from services.launch31_service import overview, prepare_launch, public_status

router = APIRouter()


@router.get("/api/admin/launch31")
def launch31_overview(request: Request):
    require_admin(request)
    return overview()


@router.post("/api/admin/launch31/prepare")
def launch31_prepare(request: Request):
    require_admin(request)
    return prepare_launch()


@router.get("/api/public/status31")
def launch31_public_status():
    return public_status()
