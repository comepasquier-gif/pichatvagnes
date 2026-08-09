"""Healthcheck public et minimal de PiChat 3.4 FREE ONLINE."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import APP_NAME, APP_VERSION, DATABASE_BACKEND, PUBLIC_URL, RENDER_MODE, STORAGE_BACKEND
from database import get_db_cursor

router = APIRouter()


@router.get("/api/health")
def health_check():
    db_ok = False
    try:
        with get_db_cursor() as cursor:
            row = cursor.execute("SELECT 1 AS ok").fetchone()
            db_ok = bool(row and int(row["ok"]) == 1)
    except Exception:
        db_ok = False
    payload = {
        "status": "ok" if db_ok else "degraded",
        "app": APP_NAME,
        "version": APP_VERSION,
        "edition": "FREE ONLINE",
        "database": {"backend": DATABASE_BACKEND, "ok": db_ok},
        "storage": {"backend": STORAGE_BACKEND},
        "https": bool(PUBLIC_URL.startswith("https://")),
        "public_url": PUBLIC_URL,
        "provider": "render" if RENDER_MODE else ("custom" if PUBLIC_URL else "local"),
    }
    return JSONResponse(payload, status_code=200 if db_ok else 503)
