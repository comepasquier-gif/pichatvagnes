from io import BytesIO

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
import qrcode
import qrcode.image.svg

from models.cloud import CloudPermanentRequest
from routes.rooms import require_admin
from services.cloud_runtime_service import (
    delete_permanent_token,
    install_cloudflared,
    save_permanent_configuration,
    start_permanent_tunnel,
    start_quick_tunnel,
    status,
    stop_tunnel,
)

router = APIRouter()


def _admin(request: Request) -> None:
    require_admin(request)


def _handle(callable_obj):
    try:
        return callable_obj()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/api/admin/cloud")
def cloud_status(request: Request):
    _admin(request)
    return status()


@router.post("/api/admin/cloud/install")
def cloud_install(request: Request):
    _admin(request)
    return _handle(install_cloudflared)


@router.post("/api/admin/cloud/quick/start")
def cloud_quick_start(request: Request):
    _admin(request)
    return _handle(start_quick_tunnel)


@router.post("/api/admin/cloud/permanent/configure")
def cloud_permanent_configure(data: CloudPermanentRequest, request: Request):
    _admin(request)
    return _handle(lambda: save_permanent_configuration(data.token, data.public_url, data.autostart))


@router.post("/api/admin/cloud/permanent/start")
def cloud_permanent_start(request: Request):
    _admin(request)
    return _handle(start_permanent_tunnel)


@router.post("/api/admin/cloud/stop")
def cloud_stop(request: Request):
    _admin(request)
    return _handle(stop_tunnel)


@router.delete("/api/admin/cloud/token")
def cloud_delete_token(request: Request):
    _admin(request)
    return _handle(delete_permanent_token)


@router.get("/api/admin/cloud/qr")
def cloud_qr(request: Request, url: str = ""):
    _admin(request)
    selected = (url or status().get("public_url") or "").strip()
    if not selected.startswith("https://") or len(selected) > 240:
        raise HTTPException(status_code=422, detail="Aucune adresse HTTPS valide à convertir en QR code.")
    image = qrcode.make(
        selected,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=7,
        border=2,
    )
    buffer = BytesIO()
    image.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )
