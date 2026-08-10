from __future__ import annotations
from pydantic import BaseModel, Field

class ProfileUpdate(BaseModel):
    status_message: str = Field(default="", max_length=120)
    profile_bio: str = Field(default="", max_length=280)
    profile_color: str = Field(default="#5865f2", pattern="^#[0-9A-Fa-f]{6}$")
    grade_visibility: str = Field(default="full", pattern="^(full|subtle|hidden)$")

class ReactionRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=12)

class ReportRequest(BaseModel):
    reason: str = Field(default="", max_length=300)

class DuelActionRequest(BaseModel):
    action: str = Field(pattern="^(accept|decline|attack|risky|heal|defend|special|forfeit)$")

class TutorRequest(BaseModel):
    subject: str = Field(default="Général", max_length=40)
    mode: str = Field(default="hint", pattern="^(hint|method|explain|check)$")
    prompt: str = Field(min_length=2, max_length=4000)
    student_answer: str = Field(default="", max_length=3000)

class FeatureSettingsUpdate(BaseModel):
    games_enabled: bool = True
    tutor_enabled: bool = True
    reactions_enabled: bool = True
    reports_enabled: bool = True
    member_panel: bool = True
    pycoins_enabled: bool = True
    custom_servers_enabled: bool = True
    code_lab_enabled: bool = True
    support_access_enabled: bool = True
    direct_messages_enabled: bool = True
    message_edit_enabled: bool = True
    pins_enabled: bool = True
    search_enabled: bool = True
    tutor_plus_enabled: bool = True
    rpg_enabled: bool = False
    gaming_profiles_enabled: bool = True
    internet_mode_enabled: bool = False
    arcade_enabled: bool = True
    game_studio_enabled: bool = True
