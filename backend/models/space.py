from typing import Optional
from pydantic import BaseModel, Field

class SpaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    icon: str = Field(default="🏫", max_length=12)
    description: str = Field(default="", max_length=240)
    visibility: str = Field(default="invite", pattern="^(invite|public)$")

class SpaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=50)
    icon: Optional[str] = Field(default=None, max_length=12)
    description: Optional[str] = Field(default=None, max_length=240)
    visibility: Optional[str] = Field(default=None, pattern="^(invite|public)$")

class SpaceJoin(BaseModel):
    invite_code: str = Field(min_length=3, max_length=32)

class SpaceRoomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    category: str = Field(default="SALONS", max_length=30)
    class_code: Optional[str] = Field(default=None, max_length=12)

class SpaceMemberRole(BaseModel):
    role: str = Field(pattern="^(member|moderator|admin)$")
