from fastapi import APIRouter, Request, HTTPException
from models.admin_user import UISettingsUpdate
from routes.rooms import require_admin
from services.ui_settings_service import get_ui_settings, update_ui_settings, reset_ui_settings
from services.admin_user_service import log_admin_action

router = APIRouter()

@router.get('/api/ui-settings')
def public_ui_settings():
    return get_ui_settings()

@router.get('/api/admin/ui-settings')
def admin_ui_settings(request: Request):
    require_admin(request)
    return get_ui_settings()

@router.patch('/api/admin/ui-settings')
def save_ui_settings(data: UISettingsUpdate, request: Request):
    admin = require_admin(request)
    try:
        result = update_ui_settings(data.dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    log_admin_action(admin['id'], 'ui_settings', 'interface', result['theme_preset'])
    return result

@router.post('/api/admin/ui-settings/reset')
def restore_ui_settings(request: Request):
    admin = require_admin(request)
    result = reset_ui_settings()
    log_admin_action(admin['id'], 'ui_settings_reset', 'interface', '')
    return result
