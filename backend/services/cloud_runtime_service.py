from __future__ import annotations

import json
import os
import platform
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import PROJECT_ROOT, RUNTIME_DIR as PICHAT_RUNTIME_DIR
from database import init_database
from services.deployment_service import update_settings, write_deployment_files

RUNTIME_DIR = PICHAT_RUNTIME_DIR / "cloud"
HOME_DIR = RUNTIME_DIR / "home"
BINARY_PATH = RUNTIME_DIR / "cloudflared"
STATE_PATH = RUNTIME_DIR / "state.json"
LOG_PATH = RUNTIME_DIR / "cloudflared.log"
TOKEN_PATH = RUNTIME_DIR / "tunnel-token.txt"

QUICK_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
TOKEN_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{40,4096}$")

DOWNLOADS = {
    ("Darwin", "arm64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz",
    ("Darwin", "x86_64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
    ("Darwin", "amd64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(RUNTIME_DIR, 0o700)
        os.chmod(HOME_DIR, 0o700)
    except OSError:
        pass


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except (OSError, ValueError, TypeError):
        return dict(default)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    _ensure_runtime()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _load_state() -> Dict[str, Any]:
    return _read_json(
        STATE_PATH,
        {
            "mode": "stopped",
            "pid": None,
            "public_url": "",
            "started_at": "",
            "last_error": "",
            "autostart": False,
        },
    )


def _save_state(**changes: Any) -> Dict[str, Any]:
    state = _load_state()
    state.update(changes)
    _write_json(STATE_PATH, state)
    return state


def _process_command(pid: int) -> str:
    if pid <= 0:
        return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _process_alive(pid: Optional[int]) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    command = _process_command(pid)
    return bool(command and "cloudflared" in command.lower())


def _binary_version() -> str:
    if not BINARY_PATH.exists():
        return ""
    try:
        result = subprocess.run(
            [str(BINARY_PATH), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
        text = (result.stdout or result.stderr).strip()
        return text[:180]
    except (OSError, subprocess.SubprocessError):
        return ""


def _log_tail(max_lines: int = 35) -> str:
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    text = "\n".join(lines[-max_lines:])
    # Le jeton n'est normalement jamais écrit dans le log, mais on masque
    # tout fragment ressemblant à un JWT par précaution.
    text = re.sub(r"eyJ[A-Za-z0-9._~-]{30,}", "[JETON MASQUÉ]", text)
    return text[-7000:]


def _download_url() -> str:
    key = (platform.system(), platform.machine().lower())
    url = DOWNLOADS.get(key)
    if not url:
        raise RuntimeError(
            "Installation automatique disponible uniquement sur macOS Intel ou Apple Silicon."
        )
    return url


def install_cloudflared() -> Dict[str, Any]:
    """Télécharge cloudflared depuis le dépôt officiel dans le dossier privé PiChat."""
    _ensure_runtime()
    if _process_alive(_load_state().get("pid")):
        raise RuntimeError("Arrête d'abord le tunnel avant de réinstaller cloudflared.")

    url = _download_url()
    with tempfile.TemporaryDirectory(prefix="pichat-cloud-") as tmp_dir:
        tmp = Path(tmp_dir)
        archive = tmp / "cloudflared.tgz"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "PiChat-Cloud/3.2.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response, archive.open("wb") as out:
                if getattr(response, "status", 200) not in (200, 206):
                    raise RuntimeError("Téléchargement Cloudflare refusé.")
                shutil.copyfileobj(response, out)
        except Exception as exc:
            raise RuntimeError("Impossible de télécharger cloudflared : %s" % exc) from exc

        if archive.stat().st_size < 1_000_000:
            raise RuntimeError("Le fichier cloudflared téléchargé paraît incomplet.")

        extracted = tmp / "extracted"
        extracted.mkdir()
        try:
            with tarfile.open(archive, mode="r:gz") as tar:
                safe_members = []
                for member in tar.getmembers():
                    if member.issym() or member.islnk():
                        continue
                    name = Path(member.name).name
                    if name == "cloudflared" and member.isfile():
                        member.name = "cloudflared"
                        safe_members.append(member)
                if len(safe_members) != 1:
                    raise RuntimeError("Archive cloudflared inattendue.")
                tar.extractall(extracted, members=safe_members)
        except (tarfile.TarError, OSError) as exc:
            raise RuntimeError("Archive cloudflared invalide.") from exc

        candidate = extracted / "cloudflared"
        if not candidate.exists() or candidate.stat().st_size < 1_000_000:
            raise RuntimeError("Exécutable cloudflared introuvable dans l'archive.")

        staged = BINARY_PATH.with_suffix(".new")
        shutil.copy2(candidate, staged)
        os.chmod(staged, 0o755)
        try:
            result = subprocess.run(
                [str(staged), "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            staged.unlink(missing_ok=True)
            raise RuntimeError("cloudflared ne peut pas être exécuté sur ce Mac.") from exc
        if result.returncode != 0 or "cloudflared" not in (result.stdout + result.stderr).lower():
            staged.unlink(missing_ok=True)
            raise RuntimeError("La vérification de cloudflared a échoué.")
        os.replace(staged, BINARY_PATH)

    return status()


def _start_process(args: list, mode: str, public_url: str) -> Dict[str, Any]:
    _ensure_runtime()
    if not BINARY_PATH.exists():
        raise RuntimeError("Installe d'abord cloudflared depuis le panneau PiChat Cloud.")

    current = _load_state()
    if _process_alive(current.get("pid")):
        raise RuntimeError("Un tunnel PiChat est déjà actif.")

    LOG_PATH.write_text("", encoding="utf-8")
    log_handle = LOG_PATH.open("ab", buffering=0)
    env = os.environ.copy()
    env["HOME"] = str(HOME_DIR)
    env["NO_AUTOUPDATE"] = "true"
    try:
        process = subprocess.Popen(
            [str(BINARY_PATH)] + [str(arg) for arg in args],
            cwd=str(RUNTIME_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        log_handle.close()
        raise RuntimeError("Impossible de lancer cloudflared : %s" % exc) from exc
    finally:
        try:
            log_handle.close()
        except OSError:
            pass

    _save_state(
        mode=mode,
        pid=process.pid,
        public_url=public_url,
        started_at=_now_iso(),
        last_error="",
    )
    return _load_state()


def start_quick_tunnel(timeout_seconds: int = 35) -> Dict[str, Any]:
    """Crée une URL trycloudflare.com temporaire pour tester PiChat."""
    _start_process(
        [
            "tunnel",
            "--no-autoupdate",
            "--loglevel",
            "info",
            "--url",
            "http://127.0.0.1:8000",
        ],
        mode="quick",
        public_url="",
    )

    deadline = time.monotonic() + max(5, min(timeout_seconds, 60))
    found = ""
    while time.monotonic() < deadline:
        state = _load_state()
        if not _process_alive(state.get("pid")):
            error = _log_tail() or "Le tunnel s'est arrêté sans fournir d'adresse."
            _save_state(mode="stopped", pid=None, last_error=error)
            raise RuntimeError(error)
        log_text = _log_tail(100)
        match = QUICK_URL_RE.search(log_text)
        if match:
            found = match.group(0)
            break
        time.sleep(0.5)

    if not found:
        stop_tunnel()
        raise RuntimeError(
            "Cloudflare n'a pas fourni d'URL dans le délai prévu. Vérifie ta connexion Internet."
        )

    host = found.split("//", 1)[1]
    try:
        init_database()
        update_settings(
            {
                "public_url": found,
                "allowed_hosts": "%s,localhost,127.0.0.1" % host,
                "proxy_headers": True,
                "https_enabled": True,
                "internet_ready": True,
            }
        )
        write_deployment_files(found)
    except Exception:
        # Le tunnel reste utilisable même si la génération des fichiers échoue.
        pass

    _save_state(public_url=found, last_error="")
    return status()


def save_permanent_configuration(token: str, public_url: str, autostart: bool = True) -> Dict[str, Any]:
    token = (token or "").strip()
    public_url = (public_url or "").strip().rstrip("/")
    if not public_url.startswith("https://"):
        raise ValueError("L'adresse permanente doit commencer par https://")
    if not TOKEN_RE.match(token):
        raise ValueError("Le jeton Cloudflare semble incomplet ou invalide.")

    _ensure_runtime()
    TOKEN_PATH.write_text(token, encoding="utf-8")
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass

    host = public_url.split("//", 1)[1].split("/", 1)[0]
    init_database()
    update_settings(
        {
            "public_url": public_url,
            "allowed_hosts": "%s,localhost,127.0.0.1" % host,
            "proxy_headers": True,
            "https_enabled": True,
            "internet_ready": True,
        }
    )
    write_deployment_files(public_url)
    _save_state(public_url=public_url, autostart=bool(autostart), last_error="")
    return status()


def start_permanent_tunnel() -> Dict[str, Any]:
    state = _load_state()
    public_url = str(state.get("public_url") or "").strip()
    if not TOKEN_PATH.exists():
        raise RuntimeError("Aucun jeton Cloudflare permanent n'est enregistré.")
    if not public_url.startswith("https://"):
        raise RuntimeError("Indique d'abord l'adresse HTTPS permanente.")

    _start_process(
        [
            "tunnel",
            "--no-autoupdate",
            "--loglevel",
            "info",
            "run",
            "--token-file",
            str(TOKEN_PATH),
        ],
        mode="permanent",
        public_url=public_url,
    )

    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        state = _load_state()
        if not _process_alive(state.get("pid")):
            error = _log_tail() or "Le tunnel permanent s'est arrêté."
            _save_state(mode="stopped", pid=None, last_error=error)
            raise RuntimeError(error)
        log_text = _log_tail(80).lower()
        if "registered tunnel connection" in log_text or "connection" in log_text:
            break
        time.sleep(0.5)

    return status()


def stop_tunnel() -> Dict[str, Any]:
    state = _load_state()
    pid = state.get("pid")
    if _process_alive(pid):
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except (OSError, ValueError):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (OSError, ValueError):
                pass
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and _process_alive(pid):
            time.sleep(0.2)
        if _process_alive(pid):
            try:
                os.killpg(int(pid), signal.SIGKILL)
            except (OSError, ValueError):
                pass
    _save_state(mode="stopped", pid=None, started_at="")
    return status()


def delete_permanent_token() -> Dict[str, Any]:
    state = _load_state()
    if state.get("mode") == "permanent" and _process_alive(state.get("pid")):
        stop_tunnel()
    try:
        TOKEN_PATH.unlink()
    except FileNotFoundError:
        pass
    _save_state(autostart=False)
    return status()


def autostart_configured_tunnel() -> bool:
    """Démarre le tunnel permanent au lancement de PiChat si cela a été choisi."""
    state = _load_state()
    if not state.get("autostart") or not TOKEN_PATH.exists() or not BINARY_PATH.exists():
        return False
    if _process_alive(state.get("pid")):
        return True
    try:
        start_permanent_tunnel()
        return True
    except Exception as exc:
        _save_state(mode="stopped", pid=None, last_error=str(exc))
        return False


def status() -> Dict[str, Any]:
    _ensure_runtime()
    state = _load_state()
    running = _process_alive(state.get("pid"))
    if not running and state.get("mode") not in ("", "stopped"):
        state = _save_state(mode="stopped", pid=None)

    url = str(state.get("public_url") or "")
    return {
        "supported": platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "x86_64", "amd64"},
        "platform": "%s %s" % (platform.system(), platform.machine()),
        "installed": BINARY_PATH.exists(),
        "binary_path": str(BINARY_PATH),
        "version": _binary_version(),
        "running": running,
        "mode": state.get("mode") if running else "stopped",
        "pid": state.get("pid") if running else None,
        "public_url": url if (running or TOKEN_PATH.exists()) else "",
        "started_at": state.get("started_at") if running else "",
        "token_configured": TOKEN_PATH.exists(),
        "autostart": bool(state.get("autostart")),
        "last_error": str(state.get("last_error") or "")[:1000],
        "log_tail": _log_tail(),
        "quick_tunnel_warning": "Adresse temporaire réservée aux tests ; elle change après arrêt.",
    }
