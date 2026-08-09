from __future__ import annotations
from fastapi import APIRouter,Request,HTTPException
from models.moderation import ModerationReason,TimedSanctionRequest,ReportDecision,ModeratorNoteCreate,SlowModeUpdate,AdvancedModerationSettingsUpdate
from routes.admin_users import require_moderator_or_admin
from routes.rooms import require_admin
from services.moderation_service import *
from services.message_service import get_message_for_moderation,delete_message
from connection_manager import manager
from permissions import require_moderator_permission

router=APIRouter()

def need(actor, permission):
    if not actor.get("is_admin"):
        require_moderator_permission(actor, permission)


def need_any(actor, permissions):
    if actor.get("is_admin"):
        return
    granted=set(actor.get("moderator_permissions") or [])
    if granted.intersection(permissions):
        return
    raise HTTPException(403,"Aucune des permissions de modération nécessaires n'est activée.")


def translate(error):
    if isinstance(error,ModerationNotFoundError): return HTTPException(404,str(error))
    if isinstance(error,ModerationPermissionError): return HTTPException(403,str(error))
    return HTTPException(422,str(error))

@router.get('/api/moderation/restrictions/{user_id}')
def restrictions(user_id:int,request:Request):
    actor=require_moderator_or_admin(request); need_any(actor,{"users_warn","users_mute","users_kick","users_tempban","users_ban","users_unban","notes_manage"}); target=restriction_status(user_id)
    try: ensure_can_manage(actor,target)
    except Exception as e: raise translate(e)
    return target

@router.post('/api/moderation/users/{user_id}/warn')
async def warn(user_id:int,data:ModerationReason,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"users_warn")
    try: result=warn_user(actor,user_id,data.reason)
    except Exception as e: raise translate(e)
    await manager.send_to_user(user_id,{'type':'moderation_notice','level':'warning','message':'Avertissement : '+(data.reason or 'Merci de respecter le règlement.')})
    return result

@router.post('/api/moderation/users/{user_id}/mute')
async def mute(user_id:int,data:TimedSanctionRequest,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"users_mute")
    try: result=mute_user(actor,user_id,data.duration_minutes,data.reason)
    except Exception as e: raise translate(e)
    await manager.send_to_user(user_id,{'type':'moderation_notice','level':'warning','message':f'Tu es en mode muet pendant {data.duration_minutes} min. '+(data.reason or '')})
    return result

@router.post('/api/moderation/users/{user_id}/unmute')
async def unmute(user_id:int,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"users_mute")
    try: result=unmute_user(actor,user_id)
    except Exception as e: raise translate(e)
    await manager.send_to_user(user_id,{'type':'moderation_notice','level':'success','message':'Ton mode muet est levé.'})
    return result

@router.post('/api/moderation/users/{user_id}/temporary-ban')
async def temp_ban(user_id:int,data:TimedSanctionRequest,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"users_tempban")
    try: result=temp_ban_user(actor,user_id,data.duration_minutes,data.reason)
    except Exception as e: raise translate(e)
    await manager.disconnect_user(user_id); return result

@router.get('/api/moderation/actions')
def actions(request:Request,limit:int=200):
    actor=require_moderator_or_admin(request); need(actor,"history_view"); return list_actions(actor,limit)

@router.get('/api/moderation/users/{user_id}/notes')
def notes(user_id:int,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"notes_manage")
    try: return list_notes(actor,user_id)
    except Exception as e: raise translate(e)

@router.post('/api/moderation/users/{user_id}/notes',status_code=201)
def add_user_note(user_id:int,data:ModeratorNoteCreate,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"notes_manage")
    try: add_note(actor,user_id,data.note); return {'created':True}
    except Exception as e: raise translate(e)

@router.get('/api/moderation/reports')
def reports(request:Request,status_filter:str='open'):
    actor=require_moderator_or_admin(request); need(actor,"reports_view"); return list_reports(actor,status_filter)

@router.patch('/api/moderation/reports/{report_id}')
def report_decision(report_id:int,data:ReportDecision,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"reports_resolve")
    try: decide_report(actor,report_id,data.status,data.note); return {'updated':True}
    except Exception as e: raise translate(e)

@router.delete('/api/moderation/reports/{report_id}/message')
async def delete_reported_message(report_id:int,request:Request):
    actor=require_moderator_or_admin(request); need(actor,'messages_delete'); need(actor,'reports_resolve'); reports=list_reports(actor,'all'); report=next((x for x in reports if x['id']==report_id),None)
    if not report: raise HTTPException(404,'Signalement introuvable.')
    decide_report(actor,report_id,'resolved','Message supprimé.')
    if delete_message(report['message_id']):
        await manager.broadcast_to_room(report['room_id'],{'type':'message_deleted','message_id':report['message_id']})
    return {'deleted':True}

@router.get('/api/moderation/rooms/{room_id}/slow-mode')
def slow_mode(room_id:int,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"slowmode_manage"); room=get_room_slow_mode(room_id)
    if not room: raise HTTPException(404,'Salon introuvable.')
    if not actor.get('is_admin') and room.get('class_code')!=actor.get('moderator_class_code'): raise HTTPException(403,'Accès refusé.')
    return room

@router.patch('/api/moderation/rooms/{room_id}/slow-mode')
def slow_mode_update(room_id:int,data:SlowModeUpdate,request:Request):
    actor=require_moderator_or_admin(request); need(actor,"slowmode_manage")
    try: return set_room_slow_mode(actor,room_id,data.seconds)
    except Exception as e: raise translate(e)

@router.get('/api/admin/advanced-moderation-settings')
def advanced_settings(request:Request):
    require_admin(request); return get_advanced_settings()

@router.patch('/api/admin/advanced-moderation-settings')
def advanced_settings_update(data:AdvancedModerationSettingsUpdate,request:Request):
    require_admin(request); return set_advanced_settings(data.model_dump())
