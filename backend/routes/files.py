from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from config import SESSION_COOKIE_NAME
from services.auth_service import get_user_from_session
from services.storage_service import get_object

router = APIRouter()


def _require_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail='Connexion requise.')
    return user


@router.get('/api/files/{object_key:path}')
def serve_file(object_key: str, request: Request):
    _require_user(request)
    try:
        obj = get_object(object_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='Fichier introuvable.')
    safe_name = obj['name'].replace('"', '')
    return Response(
        content=obj['data'],
        media_type=obj['mime'],
        headers={
            'Content-Disposition': f'inline; filename="{safe_name}"',
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'private, max-age=3600',
        },
    )
