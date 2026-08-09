from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from routes.rooms import require_admin
from services.backup_manager_service import create_backup
from services.railway_service import RAILWAY_RUNTIME, create_deploy_bundle, overview, variables_text

router = APIRouter()


@router.get("/api/admin/railway")
def railway_overview(request: Request):
    require_admin(request)
    return overview()


@router.post("/api/admin/railway/prepare")
def railway_prepare(request: Request):
    require_admin(request)
    backup = create_backup(label="RAILWAY-3.2", note="Backup automatique avant préparation Railway")
    bundle = create_deploy_bundle()
    data = overview()
    data.update({"ok": True, "backup_created": backup.name, "bundle": bundle.name, "download_url": "/api/admin/railway/bundle/" + bundle.name})
    return data


@router.post("/api/admin/railway/bundle")
def railway_bundle(request: Request):
    require_admin(request)
    bundle = create_deploy_bundle()
    return {"ok": True, "name": bundle.name, "download_url": "/api/admin/railway/bundle/" + bundle.name}


@router.get("/api/admin/railway/bundle/{name}")
def railway_bundle_download(name: str, request: Request):
    require_admin(request)
    if not name.startswith("PiChat_3.2_Railway_Source_") or not name.endswith(".zip") or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Nom de paquet invalide.")
    path = RAILWAY_RUNTIME / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Paquet Railway introuvable.")
    return FileResponse(path, filename=name, media_type="application/zip")


@router.get("/api/admin/railway/variables", response_class=PlainTextResponse)
def railway_variables(request: Request):
    require_admin(request)
    return variables_text(include_setup_key=True)
