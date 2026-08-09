from typing import Optional, List
from pydantic import BaseModel, Field

class AdminUserPublic(BaseModel):
    id:int; username:str; class_code:Optional[str]=None
    is_admin:bool; is_moderator:bool=False; moderator_class_code:Optional[str]=None
    is_bot:bool; is_banned:bool; banned_at:Optional[str]=None; banned_reason:str=""; created_at:str
    role:str="player"; role_label:str="JOUEUR"; grade_title:str=""; grade_color:str=""
    moderator_permissions:List[str]=Field(default_factory=list)
    moderator_pack:str="custom"

class BanUserRequest(BaseModel): reason:str=Field(default="",max_length=300)
class UserClassUpdate(BaseModel): class_code:str=Field(min_length=1,max_length=12)
class ModeratorUpdate(BaseModel):
    enabled:bool
    class_code:Optional[str]=Field(default=None,max_length=12)
    permissions:Optional[List[str]]=None
    moderator_pack:Optional[str]=Field(default=None,max_length=24)
class UserRoleUpdate(BaseModel):
    role:str=Field(min_length=3,max_length=16)
    class_code:Optional[str]=Field(default=None,max_length=12)
    permissions:Optional[List[str]]=None
    moderator_pack:Optional[str]=Field(default=None,max_length=24)

class ModeratorPackApply(BaseModel):
    pack:str=Field(min_length=2,max_length=24)
    class_code:Optional[str]=Field(default=None,max_length=12)

class ModeratorPermissionsUpdate(BaseModel):
    permissions:List[str]=Field(default_factory=list)
class RegistrationRequestPublic(BaseModel):
    id:int; username:str; class_code:str; status:str; created_at:str; reviewed_at:Optional[str]=None
class RegistrationDecision(BaseModel): note:str=Field(default="",max_length=300)
class AdminConsoleCommand(BaseModel): command:str=Field(min_length=1,max_length=2000)

class AISettingsUpdate(BaseModel):
    enabled:bool
    provider:str=Field(pattern="^(local|openai)$")
    model:str=Field(min_length=1,max_length=80)
    trigger_name:str=Field(min_length=2,max_length=24)
    instructions:str=Field(min_length=1,max_length=3000)

class UserBadgeUpdate(BaseModel):
    title:str=Field(default="",max_length=24)
    color:str=Field(default="",max_length=16)

class ProfanitySettingsUpdate(BaseModel):
    enabled:bool
    words:str=Field(default="",max_length=4000)

class UISettingsUpdate(BaseModel):
    app_name:str=Field(min_length=1,max_length=40)
    app_subtitle:str=Field(default="",max_length=80)
    welcome_message:str=Field(default="",max_length=160)
    logo_text:str=Field(default="P",min_length=1,max_length=3)
    theme_preset:str=Field(default="neon",pattern="^(neon|ocean|sunset|forest|mono)$")
    primary_color:str=Field(default="#7c5cff",pattern="^#[0-9A-Fa-f]{6}$")
    secondary_color:str=Field(default="#37b5ff",pattern="^#[0-9A-Fa-f]{6}$")
    accent_color:str=Field(default="#22d3a6",pattern="^#[0-9A-Fa-f]{6}$")
    density:str=Field(default="comfortable",pattern="^(comfortable|compact)$")
    show_bot_hint:bool=True
    show_diagnostic:bool=True
