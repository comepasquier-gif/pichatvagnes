from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from config import SESSION_COOKIE_NAME
from models.community import ProfileUpdate,ReactionRequest,ReportRequest,DuelActionRequest,TutorRequest,FeatureSettingsUpdate
from services.auth_service import get_user_from_session
from services.community_service import update_profile,public_profile,room_members,get_feature_settings,set_feature_settings
from services.message_service import toggle_reaction,report_message,get_message
from services.room_service import user_can_access_room
from services.game_service import duel_action,get_profile
from services.tutor_service import tutor_answer
from connection_manager import manager
from routes.rooms import require_admin

router=APIRouter()

def current_user(request:Request):
    token=request.cookies.get(SESSION_COOKIE_NAME)
    user=get_user_from_session(token) if token else None
    if not user: raise HTTPException(status_code=401,detail="Non connecté.")
    return user

@router.get('/api/community/features')
def features(request:Request):
    current_user(request); return get_feature_settings()

@router.get('/api/profile/me')
def my_profile(request:Request):
    u=current_user(request); p=public_profile(u['id']); p['grade_visibility']=u.get('grade_visibility') or 'full';
    from services.gaming_profile_service import list_games
    p['games']=list_games(u['id'],include_private=True); return p

@router.patch('/api/profile/me')
def edit_profile(data:ProfileUpdate,request:Request):
    u=current_user(request); update_profile(u['id'],data.status_message,data.profile_bio,data.profile_color,data.grade_visibility);
    from services.gaming_profile_service import sync_automatic_badges,list_games
    sync_automatic_badges(u['id']); p=public_profile(u['id']); p['grade_visibility']=data.grade_visibility; p['games']=list_games(u['id'],include_private=True); return p

@router.get('/api/profiles/{user_id}')
def profile(user_id:int,request:Request):
    current_user(request); p=public_profile(user_id)
    if not p: raise HTTPException(status_code=404,detail='Profil introuvable.')
    return p

@router.get('/api/rooms/{room_id}/members')
def members(room_id:int,request:Request):
    u=current_user(request)
    if not user_can_access_room(u,room_id): raise HTTPException(status_code=403,detail='Accès refusé.')
    return room_members(room_id,u,manager.online_user_ids(room_id),manager.special_presence_map())

@router.post('/api/presence/admin')
def admin_presence(request:Request):
    u=current_user(request)
    if not u.get('is_admin'):
        raise HTTPException(status_code=403,detail='Réservé aux administrateurs.')
    manager.set_special_presence(u['id'],'🕵️ En train de manigancer quelque chose…','admin_scheming',45)
    return {'online':True,'status':'🕵️ En train de manigancer quelque chose…'}

@router.post('/api/presence/admin/leave')
def admin_presence_leave(request:Request):
    u=current_user(request)
    manager.clear_special_presence(u['id'])
    return {'online':False}

@router.post('/api/messages/{message_id}/reaction')
async def react(message_id:int,data:ReactionRequest,request:Request):
    u=current_user(request); msg=get_message(message_id)
    if not msg or not user_can_access_room(u,msg['room_id']): raise HTTPException(status_code=404,detail='Message introuvable.')
    if not get_feature_settings()['reactions_enabled']: raise HTTPException(status_code=403,detail='Réactions désactivées.')
    reactions=toggle_reaction(message_id,u['id'],data.emoji)
    await manager.broadcast_to_room(msg['room_id'],{'type':'reactions_updated','message_id':message_id,'reactions':reactions or []})
    return {'reactions':reactions or []}

@router.post('/api/messages/{message_id}/report')
def report(message_id:int,data:ReportRequest,request:Request):
    u=current_user(request); msg=get_message(message_id)
    if not msg or not user_can_access_room(u,msg['room_id']): raise HTTPException(status_code=404,detail='Message introuvable.')
    if not get_feature_settings()['reports_enabled']: raise HTTPException(status_code=403,detail='Signalements désactivés.')
    report_message(message_id,u['id'],data.reason); return {'reported':True}

@router.get('/api/game/profile')
def game_profile(request:Request):
    u=current_user(request); return get_profile(u['id'])

@router.post('/api/games/duels/{duel_id}/action')
async def duel_action_route(duel_id:int,data:DuelActionRequest,request:Request):
    u=current_user(request)
    try: msg,meta=duel_action(duel_id,u,data.action)
    except PermissionError as e: raise HTTPException(status_code=403,detail=str(e))
    except ValueError as e: raise HTTPException(status_code=422,detail=str(e))
    if msg: await manager.broadcast_to_room(msg['room_id'],{'type':'message_updated','message':msg})
    return {'message':msg,'duel':meta}

@router.post('/api/tutor/ask')
async def tutor(data:TutorRequest,request:Request):
    u=current_user(request)
    if not get_feature_settings()['tutor_enabled']: raise HTTPException(status_code=403,detail='Aide aux devoirs désactivée.')
    return await tutor_answer(data.subject,data.mode,data.prompt,data.student_answer,u)

@router.get('/api/admin/features')
def admin_features(request:Request):
    require_admin(request); return get_feature_settings()

@router.patch('/api/admin/features')
def admin_features_update(data:FeatureSettingsUpdate,request:Request):
    require_admin(request); return set_feature_settings(data.model_dump())

@router.get('/api/admin/reports')
def admin_reports(request:Request):
    require_admin(request)
    from database import get_db_cursor
    with get_db_cursor() as c:
        rows=c.execute('''SELECT mr.id,mr.message_id,mr.reason,mr.status,mr.created_at,r.username AS reporter,u.username AS author,m.content FROM message_reports mr JOIN users r ON r.id=mr.reporter_id JOIN messages m ON m.id=mr.message_id JOIN users u ON u.id=m.user_id ORDER BY mr.created_at DESC LIMIT 200''').fetchall()
    return [dict(x) for x in rows]
