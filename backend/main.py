"""
main.py
-------
Point d'entrée du serveur PiChat.

Rôle de ce fichier :
1. Créer l'application FastAPI.
2. Brancher les routes de l'API (ex: /api/health).
3. Servir les fichiers du frontend (HTML/CSS/JS) au navigateur.

Pour lancer le serveur (voir README.md pour le détail) :
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from security_middleware import SecurityHeadersMiddleware, RateLimitMiddleware, PerformanceHeadersMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from config import APP_NAME, APP_VERSION, FRONTEND_DIR, UPLOADS_DIR, INTERNET_MODE, ALLOWED_HOSTS, RAILWAY_MODE, NORTHFLANK_MODE, RENDER_MODE
from database import init_database, get_db_cursor
from routes.health import router as health_router
from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.rooms import router as rooms_router
from routes.websocket import router as websocket_router
from routes.bots import router as bots_router
from routes.admin_users import router as admin_users_router
from routes.ai import router as ai_router
from routes.ui_settings import router as ui_settings_router
from routes.community import router as community_router
from routes.moderation import router as moderation_router
from routes.automod import router as automod_router
from routes.backups import router as backups_router
from routes.support import router as support_router
from routes.economy import router as economy_router
from routes.code_lab import router as code_lab_router
from routes.spaces import router as spaces_router
from routes.direct_messages import router as direct_messages_router
from routes.messaging_v21 import router as messaging_v21_router
from routes.tutor_plus import router as tutor_plus_router
from routes.gaming_profiles import router as gaming_profiles_router
from routes.deployment import router as deployment_router
from routes.arcade import router as arcade_router
from routes.game_studio import router as game_studio_router
from routes.test_lab import router as test_lab_router
from routes.final_packs import router as final_packs_router
from routes.cloud_runtime import router as cloud_runtime_router
from routes.integration_hub import router as integration_hub_router
from routes.pro_center import router as pro_center_router
from routes.launch31 import router as launch31_router
from routes.railway import router as railway_router
from routes.setup import router as setup_router
from routes.files import router as files_router

# Création de l'application FastAPI.
# Les infos "title"/"version" apparaissent notamment dans la documentation
# automatique générée par FastAPI (accessible sur /docs).
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PerformanceHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=900)
if INTERNET_MODE and ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


@app.on_event("startup")
async def on_startup():
    """Restaure l'état hébergé, crée/migre la base puis lance les workers."""
    if NORTHFLANK_MODE:
        try:
            from services.northflank_state_service import restore_latest_snapshot
            restored = await asyncio.to_thread(restore_latest_snapshot)
            print("[Northflank] état restauré" if restored else "[Northflank] nouveau coffre")
        except Exception as exc:
            print("[Northflank] restauration impossible:", exc)
    init_database()
    from services.final_packs_service import final_pack_worker
    app.state.final_pack_worker = asyncio.create_task(final_pack_worker())
    if NORTHFLANK_MODE:
        from services.northflank_state_service import snapshot_worker
        app.state.northflank_snapshot_worker = asyncio.create_task(snapshot_worker(APP_VERSION))
    if not RAILWAY_MODE and not NORTHFLANK_MODE and not RENDER_MODE:
        from services.cloud_runtime_service import autostart_configured_tunnel
        app.state.cloud_autostart_task = asyncio.create_task(asyncio.to_thread(autostart_configured_tunnel))


@app.on_event("shutdown")
async def on_shutdown():
    if NORTHFLANK_MODE:
        task_nf = getattr(app.state, "northflank_snapshot_worker", None)
        if task_nf is not None:
            task_nf.cancel()
            try:
                await task_nf
            except asyncio.CancelledError:
                pass
        try:
            from services.northflank_state_service import save_snapshot
            await asyncio.to_thread(save_snapshot, APP_VERSION)
        except Exception as exc:
            print("[Northflank] sauvegarde finale impossible:", exc)
    task = getattr(app.state, "final_pack_worker", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Branchement des routes de l'API
# ---------------------------------------------------------------------------
# On utilise un "router" séparé (routes/health.py) plutôt que de définir
# la route directement ici : cela garde main.py léger et lisible, même
# quand le nombre de routes augmentera dans les prochains milestones.
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(rooms_router)
app.include_router(websocket_router)
app.include_router(bots_router)
app.include_router(admin_users_router)
app.include_router(ai_router)
app.include_router(ui_settings_router)
app.include_router(community_router)
app.include_router(moderation_router)
app.include_router(automod_router)
app.include_router(backups_router)
app.include_router(support_router)
app.include_router(economy_router)
app.include_router(code_lab_router)
app.include_router(spaces_router)
app.include_router(direct_messages_router)
app.include_router(messaging_v21_router)
app.include_router(tutor_plus_router)
app.include_router(gaming_profiles_router)
app.include_router(deployment_router)
app.include_router(arcade_router)
app.include_router(game_studio_router)
app.include_router(test_lab_router)
app.include_router(final_packs_router)
app.include_router(cloud_runtime_router)
app.include_router(integration_hub_router)
app.include_router(pro_center_router)
app.include_router(launch31_router)
app.include_router(railway_router)
app.include_router(setup_router)
app.include_router(files_router)

# ---------------------------------------------------------------------------
# Service des fichiers statiques du frontend (CSS, JS, images...)
# ---------------------------------------------------------------------------
# On monte le dossier "frontend/css" et "frontend/js" sous des chemins dédiés
# plutôt que tout le dossier frontend, pour garder le contrôle sur les routes
# HTML (index.html, login.html...) qui seront ajoutées progressivement.
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.get("/manifest.webmanifest", include_in_schema=False)
def serve_web_manifest():
    return FileResponse(
        FRONTEND_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/service-worker.js", include_in_schema=False)
def serve_service_worker():
    # Le fichier doit être servi depuis la racine pour contrôler toute la PWA.
    return FileResponse(
        FRONTEND_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
        },
    )


@app.get("/offline.html", include_in_schema=False)
def serve_offline_page():
    return FileResponse(FRONTEND_DIR / "offline.html")


@app.get("/")
def serve_home_page():
    """
    Sert la page d'accueil de PiChat (frontend/index.html).

    On ne monte pas tout "frontend/" en StaticFiles pour la racine "/",
    car FastAPI a besoin de garder la main sur "/" afin de pouvoir,
    plus tard, ajouter de la logique (ex: rediriger vers /login si
    l'utilisateur n'est pas connecté).

    Note de sécurité : servir ce fichier HTML ne vérifie PAS que
    l'utilisateur est connecté. La vraie vérification a lieu côté
    JavaScript (app.js appelle /api/me) et surtout côté API pour
    toute action sensible (chaque route protégée doit revalider la
    session elle-même). Un utilisateur non connecté qui accède à "/"
    verra juste la page se rediriger vers /login une fois le JS exécuté.
    """
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/login")
def serve_login_page():
    """Sert la page de connexion (frontend/login.html)."""
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/register")
def serve_register_page():
    """Sert la page d'inscription (frontend/register.html)."""
    return FileResponse(FRONTEND_DIR / "register.html")


@app.get("/admin")
def serve_admin_page():
    """
    Sert la page d'administration (frontend/admin.html).

    Comme pour "/", cette route ne vérifie pas elle-même les droits :
    la vraie protection (utilisateur connecté ET administrateur) est
    faite côté JavaScript (admin.js appelle /api/me puis vérifie
    is_admin) et surtout côté API (chaque route /api/admin/* revérifie
    les droits indépendamment, voir routes/rooms.py).
    """
    return FileResponse(FRONTEND_DIR / "admin.html")

@app.get("/moderation")
def serve_moderation_page():
    return FileResponse(FRONTEND_DIR / "moderation.html")

@app.get("/spaces")
def serve_spaces_page():
    return FileResponse(FRONTEND_DIR / "spaces.html")


@app.get("/status")
def serve_status_page():
    return FileResponse(FRONTEND_DIR / "status.html")


@app.get("/setup")
def serve_setup_page():
    # Verrouillage serveur : l’assistant n’est plus servi après création du propriétaire.
    try:
        with get_db_cursor() as c:
            cols=[r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()]
            where="is_owner=1 OR is_admin=1" if "is_owner" in cols else "is_admin=1"
            exists=int(c.execute("SELECT COUNT(*) AS n FROM users WHERE "+where).fetchone()["n"] or 0)>0
        if exists:
            return RedirectResponse(url="/", status_code=303)
    except Exception:
        pass
    return FileResponse(FRONTEND_DIR / "setup.html")
