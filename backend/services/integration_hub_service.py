from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from cryptography.fernet import Fernet, InvalidToken

from config import PICHAT_SECRET_KEY
from database import get_db_cursor

OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.6"


class IntegrationHubError(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalise_model(value: str) -> str:
    model = (value or DEFAULT_MODEL).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,120}", model):
        raise IntegrationHubError("Le nom du modèle contient des caractères non autorisés.")
    return model


def _master_secret() -> str:
    secret = (PICHAT_SECRET_KEY or os.getenv("PICHAT_SECRET_KEY", "")).strip()
    if secret:
        return secret
    # Local-only compatibility fallback. Production diagnostics flag this as unsafe.
    return "pichat-local-development-key-change-me"


def _fernet() -> Fernet:
    digest = hashlib.sha256(_master_secret().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def _key_hint(key: str) -> str:
    if not key:
        return ""
    return "••••" if len(key) <= 10 else "%s••••%s" % (key[:4], key[-4:])


def _row_public(row) -> Dict[str, Any]:
    key = _decrypt(str(row["encrypted_api_key"] or ""))
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "provider": str(row["provider"]),
        "model": str(row["model"] or ""),
        "enabled": bool(row["enabled"]),
        "configured": bool(key),
        "key_hint": _key_hint(key),
        "last_test_status": str(row["last_test_status"] or "never"),
        "last_test_message": str(row["last_test_message"] or "")[:400],
        "last_test_at": row["last_test_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_integrations() -> list[dict]:
    with get_db_cursor() as c:
        rows = c.execute("SELECT * FROM api_integrations ORDER BY enabled DESC,id ASC").fetchall()
    return [_row_public(r) for r in rows]


def add_integration(name: str, provider: str, api_key: str, model: str) -> Dict[str, Any]:
    clean_name = (name or provider or "API").strip()[:80]
    clean_provider = re.sub(r"[^a-z0-9._-]+", "", (provider or "openai").lower())[:40]
    clean_model = _normalise_model(model)
    key = (api_key or "").strip()
    if len(key) < 12 or any(ch.isspace() for ch in key):
        raise IntegrationHubError("La clé API semble incomplète ou contient des espaces.")
    with get_db_cursor() as c:
        c.execute(
            """INSERT INTO api_integrations(name,provider,model,encrypted_api_key,enabled)
               VALUES (?,?,?,?,1)""",
            (clean_name, clean_provider, clean_model, _encrypt(key)),
        )
        iid = int(c.lastrowid)
        row = c.execute("SELECT * FROM api_integrations WHERE id=?", (iid,)).fetchone()
    return _row_public(row)


def update_integration(integration_id: int, *, name: Optional[str] = None, provider: Optional[str] = None,
                       api_key: Optional[str] = None, model: Optional[str] = None,
                       enabled: Optional[bool] = None) -> Dict[str, Any]:
    with get_db_cursor() as c:
        row = c.execute("SELECT * FROM api_integrations WHERE id=?", (integration_id,)).fetchone()
        if not row:
            raise IntegrationHubError("Intégration introuvable.")
        fields, args = [], []
        if name is not None:
            fields.append("name=?"); args.append((name or "API").strip()[:80])
        if provider is not None:
            fields.append("provider=?"); args.append(re.sub(r"[^a-z0-9._-]+", "", provider.lower())[:40])
        if model is not None:
            fields.append("model=?"); args.append(_normalise_model(model))
        if api_key is not None and api_key.strip():
            key = api_key.strip()
            if len(key) < 12 or any(ch.isspace() for ch in key):
                raise IntegrationHubError("La clé API semble invalide.")
            fields.append("encrypted_api_key=?"); args.append(_encrypt(key))
        if enabled is not None:
            fields.append("enabled=?"); args.append(1 if enabled else 0)
        if fields:
            fields.append("updated_at=datetime('now')")
            args.append(integration_id)
            c.execute("UPDATE api_integrations SET " + ",".join(fields) + " WHERE id=?", tuple(args))
        row = c.execute("SELECT * FROM api_integrations WHERE id=?", (integration_id,)).fetchone()
    return _row_public(row)


def delete_integration(integration_id: int) -> None:
    with get_db_cursor() as c:
        c.execute("DELETE FROM api_integrations WHERE id=?", (integration_id,))


def _get_private_integration(integration_id: int):
    with get_db_cursor() as c:
        return c.execute("SELECT * FROM api_integrations WHERE id=?", (integration_id,)).fetchone()


def _test_openai_key(key: str) -> tuple[bool, str, int]:
    req = urlrequest.Request(
        OPENAI_API_BASE + "/models",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": "PiChat/3.5"},
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        count = len(payload.get("data") or []) if isinstance(payload, dict) else 0
        return True, "Connexion réussie.", count
    except HTTPError as error:
        detail = ""
        try:
            detail = str(json.loads(error.read().decode("utf-8")).get("error", {}).get("message") or "")
        except Exception:
            pass
        return False, detail[:300] or "Clé refusée (HTTP %s)." % error.code, 0
    except (URLError, TimeoutError):
        return False, "Impossible de joindre le fournisseur.", 0


def test_integration(integration_id: int) -> Dict[str, Any]:
    row = _get_private_integration(integration_id)
    if not row:
        raise IntegrationHubError("Intégration introuvable.")
    key = _decrypt(str(row["encrypted_api_key"] or ""))
    if not key:
        raise IntegrationHubError("La clé API ne peut pas être déchiffrée. Vérifie PICHAT_SECRET_KEY.")
    provider = str(row["provider"]).lower()
    if provider == "openai":
        ok, message, count = _test_openai_key(key)
    else:
        # Generic providers can be stored/disabled safely. Network tests are explicit per provider.
        raise IntegrationHubError("Le test automatique est actuellement disponible pour OpenAI.")
    with get_db_cursor() as c:
        c.execute(
            "UPDATE api_integrations SET last_test_status=?,last_test_message=?,last_test_at=datetime('now'),updated_at=datetime('now') WHERE id=?",
            ("ok" if ok else "error", message, integration_id),
        )
    if not ok:
        raise IntegrationHubError(message)
    result = update_integration(integration_id)
    result["models_visible"] = count
    result["message"] = message
    return result


def get_openai_api_key() -> str:
    with get_db_cursor() as c:
        row = c.execute(
            "SELECT encrypted_api_key FROM api_integrations WHERE lower(provider)='openai' AND enabled=1 ORDER BY id LIMIT 1"
        ).fetchone()
    if row:
        key = _decrypt(str(row["encrypted_api_key"] or ""))
        if key:
            return key
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_openai_model() -> str:
    with get_db_cursor() as c:
        row = c.execute(
            "SELECT model FROM api_integrations WHERE lower(provider)='openai' AND enabled=1 ORDER BY id LIMIT 1"
        ).fetchone()
        if row and row["model"]:
            return str(row["model"])
        old = c.execute("SELECT model FROM ai_settings WHERE id=1").fetchone()
    return str(old["model"] if old and old["model"] else DEFAULT_MODEL)


def public_status() -> Dict[str, Any]:
    with get_db_cursor() as c:
        row = c.execute(
            "SELECT * FROM api_integrations WHERE lower(provider)='openai' ORDER BY enabled DESC,id LIMIT 1"
        ).fetchone()
        ai = c.execute("SELECT enabled,provider FROM ai_settings WHERE id=1").fetchone()
        gs = c.execute("SELECT direct_api_enabled FROM game_studio_settings WHERE id=1").fetchone()
    if row:
        result = _row_public(row)
        result["source"] = "encrypted_database"
    else:
        env = os.getenv("OPENAI_API_KEY", "").strip()
        result = {
            "provider": "openai", "configured": bool(env), "key_hint": _key_hint(env),
            "source": "environment" if env else "none", "model": get_openai_model(),
            "last_test_status": "never", "last_test_at": None, "last_error": "", "saved_at": None,
        }
    result["piai_enabled"] = bool(ai and ai["enabled"] and ai["provider"] == "openai")
    result["game_generation_enabled"] = bool(gs and gs["direct_api_enabled"])
    return result


def save_openai(api_key: Optional[str], model: str, enable_piai: bool, enable_game_generation: bool) -> Dict[str, Any]:
    clean_model = _normalise_model(model)
    with get_db_cursor() as c:
        row = c.execute("SELECT id FROM api_integrations WHERE lower(provider)='openai' ORDER BY id LIMIT 1").fetchone()
    if row:
        update_integration(int(row["id"]), api_key=api_key if api_key else None, model=clean_model, enabled=True)
    else:
        key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            raise IntegrationHubError("Colle une clé API OpenAI avant d’enregistrer.")
        add_integration("OpenAI", "openai", key, clean_model)
    with get_db_cursor() as c:
        c.execute("UPDATE ai_settings SET enabled=?,provider=?,model=?,updated_at=datetime('now') WHERE id=1",
                  (1 if enable_piai else 0, "openai" if enable_piai else "local", clean_model))
        c.execute("UPDATE game_studio_settings SET direct_api_enabled=?,updated_at=datetime('now') WHERE id=1",
                  (1 if enable_game_generation else 0,))
    return public_status()


def remove_openai() -> Dict[str, Any]:
    with get_db_cursor() as c:
        rows = c.execute("SELECT id FROM api_integrations WHERE lower(provider)='openai'").fetchall()
        for row in rows:
            c.execute("DELETE FROM api_integrations WHERE id=?", (row["id"],))
        c.execute("UPDATE ai_settings SET enabled=1,provider='local',updated_at=datetime('now') WHERE id=1")
        c.execute("UPDATE game_studio_settings SET direct_api_enabled=0,updated_at=datetime('now') WHERE id=1")
    return public_status()


def test_openai_connection() -> Dict[str, Any]:
    with get_db_cursor() as c:
        row = c.execute("SELECT id FROM api_integrations WHERE lower(provider)='openai' AND enabled=1 ORDER BY id LIMIT 1").fetchone()
    if not row:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise IntegrationHubError("Aucune clé API OpenAI n’est configurée.")
        ok, message, count = _test_openai_key(key)
        if not ok:
            raise IntegrationHubError(message)
        out = public_status(); out["message"] = message; out["models_visible"] = count; return out
    return test_integration(int(row["id"]))
