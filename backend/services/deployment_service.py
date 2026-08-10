from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from database import get_db_cursor
from config import PROJECT_ROOT, DEPLOYMENT_DIR




def get_settings():
    with get_db_cursor() as c:
        row = c.execute("SELECT * FROM deployment_settings WHERE id=1").fetchone()
    if not row:
        return {"public_url": "", "allowed_hosts": "localhost,127.0.0.1", "proxy_headers": False, "https_enabled": False, "internet_ready": False}
    result = dict(row)
    for key in ("proxy_headers", "https_enabled", "internet_ready"):
        result[key] = bool(result[key])
    return result


def update_settings(values: dict):
    public_url = (values.get("public_url") or "").strip().rstrip("/")[:240]
    if public_url and not public_url.startswith(("https://", "http://")):
        raise ValueError("L'URL doit commencer par https:// ou http://.")
    allowed = (values.get("allowed_hosts") or "localhost,127.0.0.1").strip()[:500]
    with get_db_cursor() as c:
        c.execute(
            """UPDATE deployment_settings SET public_url=?,allowed_hosts=?,proxy_headers=?,https_enabled=?,internet_ready=?,updated_at=datetime('now') WHERE id=1""",
            (public_url, allowed, 1 if values.get("proxy_headers") else 0, 1 if values.get("https_enabled") else 0, 1 if values.get("internet_ready") else 0),
        )
    return get_settings()


def domain_from_url(public_url: str):
    parsed = urlparse(public_url or "")
    return parsed.hostname or "chat.exemple.fr"


def build_caddyfile(public_url: str):
    domain = domain_from_url(public_url)
    return f"""# PiChat 2.1 — reverse proxy HTTPS automatique\n{domain} {{\n    encode zstd gzip\n    reverse_proxy 127.0.0.1:8000\n    header {{\n        Strict-Transport-Security \"max-age=31536000; includeSubDomains\"\n        X-Content-Type-Options \"nosniff\"\n        Referrer-Policy \"strict-origin-when-cross-origin\"\n        Permissions-Policy \"camera=(), microphone=(), geolocation=()\"\n    }}\n}}\n"""


def write_deployment_files(public_url: str):
    if not public_url.startswith("https://"):
        raise ValueError("Une URL Internet PiChat doit utiliser https://.")
    DEPLOYMENT_DIR.mkdir(parents=True, exist_ok=True)
    domain = domain_from_url(public_url)
    caddy = build_caddyfile(public_url)
    env = "\n".join([
        "PICHAT_INTERNET_MODE=1",
        "PICHAT_COOKIE_SECURE=1",
        "PICHAT_TRUST_PROXY=1",
        f"PICHAT_PUBLIC_URL={public_url}",
        f"PICHAT_ALLOWED_HOSTS={domain},localhost,127.0.0.1",
        "",
    ])
    (DEPLOYMENT_DIR / "Caddyfile").write_text(caddy, encoding="utf-8")
    (DEPLOYMENT_DIR / "pichat.production.env").write_text(env, encoding="utf-8")
    return {"directory": str(DEPLOYMENT_DIR), "caddyfile": caddy, "env": env, "domain": domain}


def readiness():
    settings = get_settings()
    checks = {
        "public_url_https": bool(settings.get("public_url", "").startswith("https://")),
        "allowed_hosts": bool(settings.get("allowed_hosts")),
        "proxy_headers": bool(settings.get("proxy_headers")),
        "https_enabled": bool(settings.get("https_enabled")),
        "caddyfile_exists": (DEPLOYMENT_DIR / "Caddyfile").exists(),
        "production_env_exists": (DEPLOYMENT_DIR / "pichat.production.env").exists(),
    }
    return {"ready": all(checks.values()), "checks": checks, "settings": settings}
