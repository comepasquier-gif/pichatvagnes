"""
config.py
---------
Point de configuration UNIQUE du projet PiChat.

But : éviter que des valeurs importantes (port, chemins, noms...)
soient codées en dur un peu partout dans le code. Si on doit changer
un réglage plus tard (par exemple pour le déploiement sur Raspberry Pi 5),
on modifie uniquement ce fichier.
"""

from pathlib import Path
import os

# ---------------------------------------------------------------------------
# Informations générales de l'application
# ---------------------------------------------------------------------------
APP_NAME = "PiChat"
APP_VERSION = "3.6.2"  # Version incrémentée à chaque milestone majeur

# ---------------------------------------------------------------------------
# Réseau
# ---------------------------------------------------------------------------
# En développement, on écoute sur toutes les interfaces (0.0.0.0) pour pouvoir
# tester depuis un autre appareil du réseau local (ex: téléphone).
# C'est aussi la configuration qui sera utilisée sur le Raspberry Pi.
HOST = "0.0.0.0"
PORT = 8000

# ---------------------------------------------------------------------------
# Chemins du projet
# ---------------------------------------------------------------------------
# BASE_DIR pointe vers le dossier "backend/". On remonte ensuite d'un niveau
# pour obtenir la racine du projet (PiChat/), afin que les chemins
# fonctionnent quel que soit l'endroit d'où le script est lancé.
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Données persistantes. Sur Mac, elles restent dans le dossier PiChat.
# Sur Railway, PICHAT_DATA_ROOT=/app/data permet de monter un volume unique
# qui conserve SQLite, les uploads, les backups et les réglages privés.
RAILWAY_MODE = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_ID") or os.getenv("RAILWAY_PROJECT_ID"))
RENDER_MODE = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_EXTERNAL_URL"))
ORACLE_MODE = os.getenv("PICHAT_ORACLE_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
NORTHFLANK_MODE = os.getenv("PICHAT_NORTHFLANK_MODE", "0").strip().lower() in {"1", "true", "yes", "on"} or bool(os.getenv("NORTHFLANK_PROJECT_ID") or os.getenv("NORTHFLANK_SERVICE_ID"))
RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
_data_root_env = os.getenv("PICHAT_DATA_ROOT", "").strip()
DATA_ROOT = Path(_data_root_env).expanduser() if _data_root_env else PROJECT_ROOT
DATABASE_DIR = DATA_ROOT / "database"
UPLOADS_DIR = DATA_ROOT / "uploads"
BACKUPS_DIR = DATA_ROOT / "backups"
LOGS_DIR = DATA_ROOT / "logs"
RUNTIME_DIR = DATA_ROOT / "runtime"
DEPLOYMENT_DIR = DATA_ROOT / "deployment"

# Chemin du fichier de base de données SQLite
DATABASE_PATH = DATABASE_DIR / "pichat.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE_BACKEND = "postgresql" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"

# Les fichiers publics peuvent être stockés dans PostgreSQL (zéro disque persistant requis)
# ou dans un stockage S3 compatible pour les instances plus importantes.
STORAGE_BACKEND = os.getenv("PICHAT_STORAGE_BACKEND", "database" if DATABASE_BACKEND == "postgresql" else "local").strip().lower()
if STORAGE_BACKEND not in {"local", "database", "s3"}:
    STORAGE_BACKEND = "database" if DATABASE_BACKEND == "postgresql" else "local"
MAX_UPLOAD_BYTES = max(1024 * 1024, int(os.getenv("PICHAT_MAX_UPLOAD_MB", "20")) * 1024 * 1024)
S3_BUCKET = os.getenv("PICHAT_S3_BUCKET", "").strip()
S3_ENDPOINT_URL = os.getenv("PICHAT_S3_ENDPOINT_URL", "").strip()
S3_REGION = os.getenv("PICHAT_S3_REGION", "auto").strip() or "auto"
S3_ACCESS_KEY_ID = os.getenv("PICHAT_S3_ACCESS_KEY_ID", "").strip()
S3_SECRET_ACCESS_KEY = os.getenv("PICHAT_S3_SECRET_ACCESS_KEY", "").strip()
PICHAT_SECRET_KEY = os.getenv("PICHAT_SECRET_KEY", "").strip()

# ---------------------------------------------------------------------------
# URL locale conviviale sur le Mac
# ---------------------------------------------------------------------------
# La v1.0.2 n'utilise plus Bonjour/mDNS. Le guide ajoute pichat.test dans
# /etc/hosts, ce qui est plus fiable sur le Mac hôte. Pour les téléphones du
# même Wi-Fi, on utilise l'adresse IP locale affichée au lancement réseau.
FRIENDLY_LOCAL_HOST = "pichat.test"
FRIENDLY_LOCAL_URL = f"http://{FRIENDLY_LOCAL_HOST}:{PORT}"

# ---------------------------------------------------------------------------
# Mode debug
# ---------------------------------------------------------------------------
# À mettre sur False en production (Raspberry Pi exposé sur Internet).
# Utile pour activer/désactiver le rechargement automatique d'Uvicorn.
DEBUG_MODE = True

# ---------------------------------------------------------------------------
# Cookie de session
# ---------------------------------------------------------------------------
SESSION_COOKIE_NAME = "pichat_session"

# COOKIE_SECURE : si True, le navigateur n'envoie le cookie que via HTTPS.
# On le laisse à False tant que le projet tourne en HTTP local (réseau local,
# développement). Il FAUDRA le passer à True lors de l'ouverture sur
# Internet (Milestone 10), une fois HTTPS mis en place, sinon le cookie
# de session pourrait être intercepté sur le réseau.
COOKIE_SECURE = RENDER_MODE or RAILWAY_MODE or ORACLE_MODE or NORTHFLANK_MODE or os.getenv("PICHAT_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes", "on"}

# Durée de vie d'une session, en secondes (ici : 7 jours).
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def secure_cookie_for_request(request) -> bool:
    """Active Secure pour HTTPS direct ou transmis par Cloudflare/proxy."""
    if COOKIE_SECURE:
        return True
    try:
        if str(request.url.scheme).lower() == "https":
            return True
        forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
        if forwarded == "https":
            return True
        cf_visitor = request.headers.get("cf-visitor", "").lower()
        return '"scheme":"https"' in cf_visitor.replace(" ", "")
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Inscriptions
# ---------------------------------------------------------------------------
# open     : inscription immédiate, sans validation admin (défaut v1.0.0)
# approval : ancienne logique avec demande à accepter/refuser
# closed   : aucune nouvelle inscription publique
REGISTRATION_MODE = os.getenv("PICHAT_REGISTRATION_MODE", "approval").strip().lower()
if REGISTRATION_MODE not in {"open", "approval", "closed"}:
    REGISTRATION_MODE = "approval"


# ---------------------------------------------------------------------------
# Déploiement PiChat 2.1
# ---------------------------------------------------------------------------
PUBLIC_URL = os.getenv("PICHAT_PUBLIC_URL", "").strip().rstrip("/")
if not PUBLIC_URL and RAILWAY_PUBLIC_DOMAIN:
    PUBLIC_URL = "https://" + RAILWAY_PUBLIC_DOMAIN
if not PUBLIC_URL and os.getenv("RENDER_EXTERNAL_URL"):
    PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
INTERNET_MODE = RENDER_MODE or RAILWAY_MODE or ORACLE_MODE or os.getenv("PICHAT_INTERNET_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [h.strip() for h in os.getenv("PICHAT_ALLOWED_HOSTS", "").split(",") if h.strip()]
if RENDER_MODE:
    for host in ["*.onrender.com", "localhost", "127.0.0.1"]:
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)
if RAILWAY_MODE:
    defaults = ["*.up.railway.app", "healthcheck.railway.app", "localhost", "127.0.0.1"]
    if RAILWAY_PUBLIC_DOMAIN:
        defaults.append(RAILWAY_PUBLIC_DOMAIN)
    for host in defaults:
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)
TRUST_PROXY_HEADERS = RENDER_MODE or RAILWAY_MODE or ORACLE_MODE or os.getenv("PICHAT_TRUST_PROXY", "0").strip().lower() in {"1", "true", "yes", "on"}

# Assistant de première installation publique. Il est automatiquement inutilisable
# dès qu'un administrateur existe en base.
SETUP_MODE = RENDER_MODE or os.getenv("PICHAT_SETUP_MODE", "1" if DATABASE_BACKEND == "postgresql" else "0").strip().lower() in {"1", "true", "yes", "on"}
SETUP_KEY = os.getenv("PICHAT_SETUP_KEY", "").strip()

# ---------------------------------------------------------------------------
# Administration
# ---------------------------------------------------------------------------
# Aucun identifiant administrateur n'est embarqué dans le code.
# Le premier compte admin est créé lors de l'installation via create_admin.py.
