from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from config import (
    APP_NAME, APP_VERSION, PROJECT_ROOT, DATA_ROOT, DATABASE_PATH, UPLOADS_DIR,
    BACKUPS_DIR, RUNTIME_DIR, RAILWAY_MODE, RAILWAY_PUBLIC_DOMAIN, PUBLIC_URL,
)
from database import get_db_cursor

RAILWAY_RUNTIME = RUNTIME_DIR / "railway"
SETUP_KEY_FILE = RAILWAY_RUNTIME / "local-setup-key.txt"
EXCLUDED_TOP_LEVEL = {"database", "uploads", "backups", "venv", "logs", "runtime", "deployment", ".git"}
EXCLUDED_FILES = {".env", "api-vault.json", "tunnel-token.txt", ".DS_Store"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _human_size(value: int) -> str:
    value = int(value or 0)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if value < 1024 or unit == "To":
            return ("%.1f %s" % (value, unit)) if unit != "o" else ("%d o" % value)
        value = value / 1024.0
    return "%s o" % value


def ensure_local_setup_key() -> str:
    RAILWAY_RUNTIME.mkdir(parents=True, exist_ok=True)
    if SETUP_KEY_FILE.exists():
        key = SETUP_KEY_FILE.read_text(encoding="utf-8").strip()
        if len(key) >= 20:
            return key
    key = secrets.token_urlsafe(24)
    SETUP_KEY_FILE.write_text(key + "\n", encoding="utf-8")
    try:
        os.chmod(SETUP_KEY_FILE, 0o600)
    except OSError:
        pass
    return key


def variables_text(include_setup_key: bool = True) -> str:
    setup_key = ensure_local_setup_key() if include_setup_key and not RAILWAY_MODE else os.getenv("PICHAT_SETUP_KEY", "CHANGE_ME")
    lines = [
        "PICHAT_DATA_ROOT=/app/data",
        "PICHAT_INTERNET_MODE=1",
        "PICHAT_COOKIE_SECURE=1",
        "PICHAT_TRUST_PROXY=1",
        "PICHAT_REGISTRATION_MODE=approval",
        "PICHAT_ALLOWED_HOSTS=*.up.railway.app,healthcheck.railway.app,localhost,127.0.0.1",
        "PICHAT_SETUP_MODE=1",
        "PICHAT_SETUP_KEY=%s" % setup_key,
    ]
    return "\n".join(lines) + "\n"


def _db_stats() -> Dict[str, int]:
    out = {"users": 0, "admins": 0, "messages": 0}
    try:
        with get_db_cursor() as cursor:
            out["users"] = int(cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            out["admins"] = int(cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0])
            out["messages"] = int(cursor.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
    except Exception:
        pass
    return out


def overview() -> Dict[str, Any]:
    domain = RAILWAY_PUBLIC_DOMAIN.strip()
    public_url = PUBLIC_URL or ("https://" + domain if domain else "")
    mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    data_root = str(DATA_ROOT)
    stats = _db_stats()
    usage_path = DATA_ROOT if DATA_ROOT.exists() else PROJECT_ROOT
    try:
        usage = shutil.disk_usage(usage_path)
        free = int(usage.free)
    except Exception:
        free = 0
    checks: List[Dict[str, Any]] = [
        {"id": "dockerfile", "label": "Dockerfile Railway", "ok": (PROJECT_ROOT / "Dockerfile").exists(), "help": "Le serveur peut être construit automatiquement."},
        {"id": "config", "label": "railway.json", "ok": (PROJECT_ROOT / "railway.json").exists(), "help": "Healthcheck et redémarrage sont configurés."},
        {"id": "volume", "label": "Volume persistant /app/data", "ok": (not RAILWAY_MODE) or bool(mount_path) or str(DATA_ROOT) == "/app/data", "help": "Monte un volume Railway sur /app/data pour conserver SQLite et les fichiers."},
        {"id": "domain", "label": "URL HTTPS permanente", "ok": bool(public_url.startswith("https://")), "help": "Dans Railway : Settings > Networking > Generate Domain."},
        {"id": "admin", "label": "Administrateur présent", "ok": stats["admins"] > 0 or not RAILWAY_MODE, "help": "Sur un nouveau déploiement, ouvre /setup avec la clé de première installation."},
    ]
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "provider": "railway",
        "railway_mode": bool(RAILWAY_MODE),
        "service_name": os.getenv("RAILWAY_SERVICE_NAME", ""),
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", os.getenv("RAILWAY_ENVIRONMENT", "")),
        "public_domain": domain,
        "public_url": public_url,
        "volume_mount_path": mount_path,
        "data_root": data_root,
        "database_path": str(DATABASE_PATH),
        "uploads_path": str(UPLOADS_DIR),
        "backups_path": str(BACKUPS_DIR),
        "free_bytes": free,
        "free_human": _human_size(free),
        "stats": stats,
        "checks": checks,
        "ready": all(bool(x["ok"]) for x in checks if x["id"] not in {"domain", "admin"}) and (not RAILWAY_MODE or bool(public_url)),
        "variables": variables_text(include_setup_key=not RAILWAY_MODE),
        "setup_url": (public_url + "/setup") if public_url else "/setup",
        "status_url": (public_url + "/status") if public_url else "/status",
        "generated_at": _now(),
    }


def _should_skip(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT)
    if rel.parts and rel.parts[0] in EXCLUDED_TOP_LEVEL:
        return True
    if path.name in EXCLUDED_FILES:
        return True
    if "__pycache__" in rel.parts or path.suffix in {".pyc", ".pyo"}:
        return True
    return False


def create_deploy_bundle() -> Path:
    RAILWAY_RUNTIME.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = RAILWAY_RUNTIME / ("PiChat_3.2_Railway_Source_%s.zip" % stamp)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PROJECT_ROOT.rglob("*")):
            if _should_skip(path) or not path.is_file():
                continue
            rel = path.relative_to(PROJECT_ROOT)
            archive.write(path, str(rel))
        archive.writestr("database/.gitkeep", "")
        archive.writestr("uploads/.gitkeep", "")
        archive.writestr("backups/.gitkeep", "")
        archive.writestr("logs/.gitkeep", "")
        archive.writestr("runtime/.gitkeep", "")
        archive.writestr("deployment/.gitkeep", "")
    return output
