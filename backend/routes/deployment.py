from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from models.v21 import DeploymentSettingsRequest
from routes.rooms import require_admin
from services.deployment_service import get_settings, update_settings, build_caddyfile, write_deployment_files, readiness

router = APIRouter()


@router.get("/api/admin/deployment")
def deployment_settings(request: Request):
    require_admin(request)
    return readiness()


@router.patch("/api/admin/deployment")
def deployment_update(data: DeploymentSettingsRequest, request: Request):
    require_admin(request)
    try:
        return update_settings(data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/api/admin/deployment/generate")
def deployment_generate(request: Request):
    require_admin(request)
    settings = get_settings()
    try:
        return write_deployment_files(settings.get("public_url") or "")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/api/admin/deployment/caddyfile", response_class=PlainTextResponse)
def deployment_caddyfile(request: Request):
    require_admin(request)
    return build_caddyfile(get_settings().get("public_url") or "")
