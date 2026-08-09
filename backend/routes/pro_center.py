from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from routes.rooms import require_admin
from services.backup_manager_service import create_backup
from services.pro_center_service import create_support_bundle, overview

router = APIRouter()


@router.get("/api/admin/pro")
def pro_overview(request: Request):
    require_admin(request)
    return overview()


@router.post("/api/admin/pro/backup")
def pro_backup(request: Request):
    require_admin(request)
    path = create_backup(label="PRO", note="Backup manuel depuis PiChat PRO")
    return {"ok": True, "name": path.name, "overview": overview()}


@router.post("/api/admin/pro/support-bundle")
def pro_support_bundle(request: Request):
    require_admin(request)
    path = create_support_bundle()
    return {"ok": True, "name": path.name, "download_url": "/api/admin/pro/support-bundle/download/%s" % path.name}


@router.get("/api/admin/pro/support-bundle/download/{name}")
def pro_support_download(name: str, request: Request):
    require_admin(request)
    if not name.startswith("PiChat_PRO_Diagnostic_") or not name.endswith(".zip") or "/" in name or "\\" in name:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Nom de paquet invalide.")
    from config import RUNTIME_DIR
    path = RUNTIME_DIR / "support" / name
    if not path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Paquet introuvable.")
    return FileResponse(path, filename=name, media_type="application/zip")
