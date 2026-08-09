from fastapi import APIRouter,Request,HTTPException
from models.admin_user import AISettingsUpdate
from routes.rooms import require_admin
from services.ai_service import get_ai_settings,update_ai_settings,AIError
router=APIRouter()
@router.get("/api/ai/status")
def ai_status():
    s=get_ai_settings(); return {"enabled":s["enabled"],"provider":s["provider"],"trigger_name":s["trigger_name"]}
@router.get("/api/admin/ai")
def admin_ai(request:Request): require_admin(request); return get_ai_settings()
@router.patch("/api/admin/ai")
def admin_ai_update(data:AISettingsUpdate,request:Request):
    require_admin(request)
    try: return update_ai_settings(data.enabled,data.provider,data.model,data.trigger_name,data.instructions)
    except AIError as e: raise HTTPException(status_code=422,detail=str(e))
