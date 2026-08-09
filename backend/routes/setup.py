from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config import SETUP_MODE, SETUP_KEY
from database import get_db_cursor, IntegrityError
from security import hash_password
from services.integration_hub_service import IntegrationHubError, add_integration

router = APIRouter()

class SetupRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=10, max_length=128)
    instance_name: str = Field(default='PiChat', min_length=1, max_length=80)
    security_level: str = Field(default='standard', max_length=20)
    registration_mode: str = Field(default='approval', max_length=20)
    api_key: str = Field(default='', max_length=1000)
    ai_model: str = Field(default='gpt-5.6', max_length=120)
    setup_key: str = Field(default='', max_length=200)


def _owner_count() -> int:
    with get_db_cursor() as c:
        cols = [r['name'] for r in c.execute('PRAGMA table_info(users)').fetchall()]
        if 'is_owner' in cols:
            return int(c.execute('SELECT COUNT(*) FROM users WHERE is_owner=1 OR is_admin=1').fetchone()[0])
        return int(c.execute('SELECT COUNT(*) FROM users WHERE is_admin=1').fetchone()[0])

@router.get('/api/setup/status')
def setup_status():
    count = _owner_count()
    return {
        'enabled': bool(SETUP_MODE and count == 0),
        'owner_exists': bool(count > 0),
        'admin_exists': bool(count > 0),
        'key_required': bool(SETUP_KEY),
        'steps': ['proprietaire', 'instance', 'securite', 'ia'],
    }

@router.post('/api/setup/complete')
def setup_complete(data: SetupRequest, request: Request):
    if not SETUP_MODE:
        raise HTTPException(status_code=403, detail='L’assistant de première installation est désactivé.')
    if _owner_count() > 0:
        raise HTTPException(status_code=409, detail='Le propriétaire existe déjà. /setup est verrouillé.')
    if SETUP_KEY and data.setup_key != SETUP_KEY:
        raise HTTPException(status_code=403, detail='Clé de première installation incorrecte.')
    username = data.username.strip()
    if not username or any(ch.isspace() for ch in username):
        raise HTTPException(status_code=422, detail='Le pseudo ne doit pas contenir d’espace.')
    if data.security_level not in {'standard', 'strict'}:
        raise HTTPException(status_code=422, detail='Niveau de sécurité invalide.')
    if data.registration_mode not in {'open', 'approval', 'closed'}:
        raise HTTPException(status_code=422, detail='Mode d’inscription invalide.')
    try:
        with get_db_cursor() as c:
            if c.execute('SELECT id FROM users WHERE lower(username)=lower(?)', (username,)).fetchone():
                raise HTTPException(status_code=409, detail='Ce pseudo existe déjà.')
            c.execute(
                "INSERT INTO users(username,password_hash,is_admin,is_owner,status_message) VALUES (?,?,1,1,?)",
                (username, hash_password(data.password), 'Propriétaire PiChat'),
            )
            owner_id = int(c.lastrowid)
            c.execute(
                """UPDATE instance_settings SET instance_name=?,setup_completed=1,security_level=?,registration_mode=?,updated_at=datetime('now') WHERE id=1""",
                (data.instance_name.strip(), data.security_level, data.registration_mode),
            )
            c.execute(
                "INSERT INTO admin_audit_logs(actor_id,action,target,details) VALUES (?,?,?,?)",
                (owner_id, 'setup_complete', username, 'PiChat 3.4 FREE ONLINE initialisé'),
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail='Le propriétaire existe déjà. /setup est verrouillé.')
    if data.api_key.strip():
        try:
            add_integration('OpenAI', 'openai', data.api_key.strip(), data.ai_model)
            with get_db_cursor() as c:
                c.execute("UPDATE ai_settings SET enabled=1,provider='openai',model=?,updated_at=datetime('now') WHERE id=1", (data.ai_model,))
                c.execute("UPDATE game_studio_settings SET direct_api_enabled=1,updated_at=datetime('now') WHERE id=1")
        except IntegrationHubError as exc:
            # Setup is complete even if optional AI configuration was mistyped.
            return {'ok': True, 'message': 'PiChat est prêt. La configuration IA facultative a été ignorée : ' + str(exc), 'ai_configured': False}
    return {'ok': True, 'message': 'PiChat est prêt. /setup est maintenant verrouillé.', 'ai_configured': bool(data.api_key.strip())}

# Backward-compatible 3.3 endpoint.
@router.post('/api/setup/create-admin')
def setup_create_admin(data: SetupRequest, request: Request):
    return setup_complete(data, request)
