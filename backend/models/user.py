from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

class UserRegister(BaseModel):
    username:str=Field(min_length=3,max_length=32)
    password:str=Field(min_length=8,max_length=128)
    class_code:str=Field(min_length=1,max_length=12)
    @field_validator("class_code")
    @classmethod
    def uppercase_class(cls,value:str)->str: return value.strip().upper()
class UserLogin(BaseModel): username:str; password:str
class UserPublic(BaseModel):
    id:int; username:str; avatar_path:Optional[str]=None; status_message:str=""
    is_admin:bool=False; is_moderator:bool=False; class_code:Optional[str]=None; moderator_class_code:Optional[str]=None
    role:str="player"; role_label:str="JOUEUR"; grade_title:str=""; grade_color:str=""
    moderator_permissions:List[str]=Field(default_factory=list)
    grade_visibility:str="full"; profile_bio:str=""; profile_color:str="#5865f2"
    xp:int=0; coins:int=0; game_wins:int=0; game_losses:int=0
    support_mode:bool=False; support_admin_id:Optional[int]=None; support_admin_username:Optional[str]=None; support_expires_at:Optional[str]=None
