from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from config import APP_NAME, APP_VERSION, PROJECT_ROOT, RUNTIME_DIR
from services.backup_manager_service import create_backup
from services.pro_center_service import overview as pro_overview
from services.integration_hub_service import public_status as api_status
from services.cloud_runtime_service import status as cloud_status
from services.railway_service import overview as railway_overview
from services.game_studio_service import get_settings as studio_settings
from services.community_service import get_feature_settings
from services.test_lab_service import diagnostics as lab_diagnostics

REPORT_DIR = RUNTIME_DIR / "launch31"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe(call, default):
    try:
        return call()
    except Exception as exc:
        result = dict(default)
        result["error"] = str(exc)[:240]
        return result


def _recommendations(pro: Dict[str, Any], cloud: Dict[str, Any], api: Dict[str, Any], lab: Dict[str, Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    launch = pro.get("launch") or {}
    for check in launch.get("checks") or []:
        if check.get("ok"):
            continue
        check_id = str(check.get("id") or "")
        hints = {
            "database": "Lance le diagnostic puis restaure un backup si l'intégrité SQLite échoue.",
            "admin": "Crée au moins un administrateur avant la mise en ligne.",
            "backup": "Crée un backup récent juste avant l'ouverture au public.",
            "test_accounts": "Supprime les lots du Labo avant d'ouvrir PiChat à de vrais utilisateurs.",
            "disk": "Libère au moins 1 Go sur le Mac avant la mise en ligne.",
            "https": "Ouvre Railway Online pour préparer une URL HTTPS permanente, ou utilise PiChat Cloud pour un test rapide.",
        }
        items.append({"level": "warning", "title": str(check.get("label") or check_id), "text": hints.get(check_id, "Vérifie ce point avant la mise en ligne.")})
    if not api.get("configured"):
        items.append({"level": "info", "title": "API OpenAI facultative", "text": "Ajoute une clé uniquement si tu veux PiAI ou la génération directe de jeux."})
    elif api.get("last_test_status") != "ok":
        items.append({"level": "info", "title": "Tester l'API", "text": "La clé est enregistrée, mais aucun test récent n'est confirmé."})
    if cloud.get("running") and str(cloud.get("public_url") or "").startswith("https://"):
        items.append({"level": "success", "title": "HTTPS actif", "text": "PiChat possède actuellement une adresse publique HTTPS."})
    if int(lab.get("active_batches") or 0) > 0:
        items.append({"level": "warning", "title": "Labo encore actif", "text": "Des lots de test sont encore présents dans la base."})
    if not items:
        items.append({"level": "success", "title": "Prêt", "text": "Les contrôles principaux de PiChat 3.4 sont au vert."})
    return items[:12]


def overview() -> Dict[str, Any]:
    pro = _safe(pro_overview, {"launch": {"score": 0, "ready": False, "checks": []}, "stats": {}})
    cloud = _safe(cloud_status, {"running": False, "public_url": "", "installed": False})
    railway = _safe(railway_overview, {"railway_mode": False, "public_url": ""})
    if railway.get("public_url"):
        cloud = {**cloud, "running": True, "public_url": railway.get("public_url"), "installed": True, "mode": "railway"}
    api = _safe(api_status, {"configured": False, "last_test_status": "never", "model": ""})
    studio = _safe(studio_settings, {"enabled": False, "direct_api_enabled": False})
    features = _safe(get_feature_settings, {})
    lab = _safe(lab_diagnostics, {"active_batches": 0, "test_accounts": 0, "checks": []})
    usage = shutil.disk_usage(PROJECT_ROOT)
    modules = [
        {"id": "chat", "label": "Chat & messages", "enabled": True, "icon": "💬"},
        {"id": "dm", "label": "Messages privés", "enabled": bool(features.get("direct_messages_enabled", True)), "icon": "✉️"},
        {"id": "tutor", "label": "PiTutor+", "enabled": bool(features.get("tutor_plus_enabled", True)), "icon": "📚"},
        {"id": "arcade", "label": "Arcade", "enabled": bool(features.get("arcade_enabled", True)), "icon": "🕹️"},
        {"id": "gaming", "label": "Profils gaming", "enabled": bool(features.get("gaming_profiles_enabled", True)), "icon": "🏅"},
        {"id": "studio", "label": "PiGame Studio", "enabled": bool(features.get("game_studio_enabled", True) and studio.get("enabled", True)), "icon": "🧪"},
        {"id": "api", "label": "API OpenAI", "enabled": bool(api.get("configured")), "icon": "🔑"},
        {"id": "cloud", "label": "URL publique", "enabled": bool(cloud.get("running")), "icon": "🌍"},
    ]
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "edition": "FREE ONLINE",
        "generated_at": _now(),
        "score": int((pro.get("launch") or {}).get("score") or 0),
        "ready": bool((pro.get("launch") or {}).get("ready")),
        "checks": (pro.get("launch") or {}).get("checks") or [],
        "recommendations": _recommendations(pro, cloud, api, lab),
        "railway": railway,
        "cloud": {
            "installed": bool(cloud.get("installed")),
            "running": bool(cloud.get("running")),
            "mode": str(cloud.get("mode") or "stopped"),
            "public_url": str(cloud.get("public_url") or ""),
            "token_configured": bool(cloud.get("token_configured")),
        },
        "api": {
            "configured": bool(api.get("configured")),
            "model": str(api.get("model") or ""),
            "last_test_status": str(api.get("last_test_status") or "never"),
            "piai_enabled": bool(api.get("piai_enabled")),
            "game_generation_enabled": bool(api.get("game_generation_enabled")),
        },
        "studio": {
            "enabled": bool(studio.get("enabled")),
            "direct_api_enabled": bool(studio.get("direct_api_enabled")),
            "require_admin_approval": bool(studio.get("require_admin_approval", True)),
        },
        "lab": {
            "active_batches": int(lab.get("active_batches") or 0),
            "test_accounts": int(lab.get("test_accounts") or 0),
        },
        "stats": pro.get("stats") or {},
        "modules": modules,
        "storage": {
            "free": int(usage.free),
            "total": int(usage.total),
        },
    }


def prepare_launch() -> Dict[str, Any]:
    backup = create_backup(label="PRE-LAUNCH-3.2", note="Backup automatique avant contrôle de mise en ligne PiChat 3.2")
    payload = overview()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = REPORT_DIR / ("PiChat_3.2_Preflight_%s.json" % stamp)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["backup_created"] = backup.name
    payload["report_created"] = report.name
    return payload


def public_status() -> Dict[str, Any]:
    # Route historique conservée pour les clients 3.3, mais alimentée par le
    # diagnostic 3.4 afin de ne plus dépendre de Railway/Cloudflare.
    pro = _safe(pro_overview, {"public": {}, "database": {}, "storage": {}, "server": {}})
    public = pro.get("public") or {}
    database = pro.get("database") or {}
    storage = pro.get("storage") or {}
    server = pro.get("server") or {}
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "edition": "FREE ONLINE",
        "status": "online" if server.get("ok", True) and database.get("ok", False) else "degraded",
        "https": bool(public.get("https")),
        "public_url": str(public.get("url") or ""),
        "hosting": str(public.get("provider") or "custom"),
        "database": str(database.get("backend") or "unknown"),
        "storage": str(storage.get("backend") or "unknown"),
        "updated_at": _now(),
    }
