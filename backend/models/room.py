from typing import Optional
from pydantic import BaseModel, Field, field_validator


class RoomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    class_code: Optional[str] = Field(default=None, max_length=12)

    @field_validator("class_code")
    @classmethod
    def normalize_optional_class(cls, value):
        if value is None:
            return None
        value = value.strip().upper()
        return value or None


class RoomPublic(BaseModel):
    id: int
    name: str
    class_code: Optional[str] = None
    created_at: str
    slow_mode_seconds: int = 0
    room_kind: str = "standard"
    owner_user_id: Optional[int] = None
    description: str = ""
    icon: str = "💬"
    invite_code: Optional[str] = None
    is_owner: bool = False
    space_id: Optional[int] = None
    space_name: Optional[str] = None
    space_icon: Optional[str] = None
    category: Optional[str] = None
    position: int = 0
