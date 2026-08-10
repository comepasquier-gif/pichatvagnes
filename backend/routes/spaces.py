from fastapi import APIRouter, Request, HTTPException, status
from models.space import SpaceCreate, SpaceUpdate, SpaceJoin, SpaceRoomCreate, SpaceMemberRole
from routes.rooms import get_current_user_or_401
from services.space_service import (list_spaces,create_space,switch_space,join_space,update_space,regenerate_invite,list_space_rooms,create_space_room,list_members,set_member_role,remove_member,delete_space,SpaceError)

router=APIRouter()

def fail(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except SpaceError as e: raise HTTPException(status_code=422,detail=str(e))

@router.get('/api/spaces')
def spaces(request:Request): return list_spaces(get_current_user_or_401(request))

@router.post('/api/spaces',status_code=201)
def add(data:SpaceCreate,request:Request): return fail(create_space,get_current_user_or_401(request),data.name,data.icon,data.description,data.visibility)

@router.post('/api/spaces/join')
def join(data:SpaceJoin,request:Request): return fail(join_space,get_current_user_or_401(request)['id'],data.invite_code)

@router.post('/api/spaces/{space_id}/switch')
def switch(space_id:int,request:Request): return fail(switch_space,get_current_user_or_401(request)['id'],space_id)

@router.patch('/api/spaces/{space_id}')
def edit(space_id:int,data:SpaceUpdate,request:Request): return fail(update_space,get_current_user_or_401(request),space_id,data.model_dump())

@router.post('/api/spaces/{space_id}/invite/regenerate')
def invite(space_id:int,request:Request): return {'invite_code':fail(regenerate_invite,get_current_user_or_401(request),space_id)}

@router.get('/api/spaces/{space_id}/rooms')
def rooms(space_id:int,request:Request): return fail(list_space_rooms,get_current_user_or_401(request),space_id)

@router.post('/api/spaces/{space_id}/rooms',status_code=201)
def add_room(space_id:int,data:SpaceRoomCreate,request:Request): return fail(create_space_room,get_current_user_or_401(request),space_id,data.name,data.category,data.class_code)

@router.get('/api/spaces/{space_id}/members')
def members(space_id:int,request:Request): return fail(list_members,get_current_user_or_401(request),space_id)

@router.patch('/api/spaces/{space_id}/members/{user_id}')
def role(space_id:int,user_id:int,data:SpaceMemberRole,request:Request): return fail(set_member_role,get_current_user_or_401(request),space_id,user_id,data.role)

@router.delete('/api/spaces/{space_id}/members/{user_id}',status_code=204)
def remove(space_id:int,user_id:int,request:Request): fail(remove_member,get_current_user_or_401(request),space_id,user_id)

@router.delete('/api/spaces/{space_id}',status_code=204)
def delete(space_id:int,request:Request): fail(delete_space,get_current_user_or_401(request),space_id)
