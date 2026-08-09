from typing import List, Optional
from pydantic import BaseModel, Field


class GameIdentityInput(BaseModel):
    game_key: str = Field(default="", max_length=48)
    game_name: str = Field(min_length=1, max_length=48)
    username: str = Field(default="", max_length=80)
    platform: str = Field(default="", max_length=32)
    is_public: bool = True


class GamingProfilesUpdate(BaseModel):
    games: List[GameIdentityInput] = Field(default_factory=list, max_length=12)


class BadgeCreate(BaseModel):
    code: str = Field(default="", max_length=40)
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=180)
    icon: str = Field(default="🏅", min_length=1, max_length=12)
    color: str = Field(default="#f0b232", pattern="^#[0-9A-Fa-f]{6}$")
    category: str = Field(default="custom", max_length=24)


class BadgeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    description: Optional[str] = Field(default=None, max_length=180)
    icon: Optional[str] = Field(default=None, min_length=1, max_length=12)
    color: Optional[str] = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    category: Optional[str] = Field(default=None, max_length=24)
    is_active: Optional[bool] = None


class BadgeAward(BaseModel):
    reason: str = Field(default="", max_length=180)
    showcased: bool = True
