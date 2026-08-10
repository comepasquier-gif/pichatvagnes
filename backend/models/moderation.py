from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional

class ModerationReason(BaseModel):
    reason: str = Field(default="", max_length=400)

class TimedSanctionRequest(ModerationReason):
    duration_minutes: int = Field(ge=1, le=43200)

class ReportDecision(BaseModel):
    status: str = Field(pattern="^(resolved|rejected|open)$")
    note: str = Field(default="", max_length=500)

class ModeratorNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=1000)

class SlowModeUpdate(BaseModel):
    seconds: int = Field(ge=0, le=21600)

class AdvancedModerationSettingsUpdate(BaseModel):
    profanity_enabled: bool = True
    profanity_words: str = Field(default="", max_length=4000)
    duplicate_enabled: bool = True
    duplicate_window_seconds: int = Field(default=45, ge=3, le=600)
    similarity_enabled: bool = True
    similarity_ratio: float = Field(default=0.88, ge=0.65, le=1.0)
    similarity_min_length: int = Field(default=12, ge=5, le=200)
    similarity_window_seconds: int = Field(default=90, ge=5, le=900)
    burst_enabled: bool = True
    burst_count: int = Field(default=5, ge=2, le=30)
    burst_window_seconds: int = Field(default=4, ge=1, le=60)
    uppercase_enabled: bool = True
    uppercase_min_length: int = Field(default=14, ge=5, le=100)
    uppercase_ratio: float = Field(default=0.82, ge=0.5, le=1.0)
    rate_limit_count: int = Field(default=12, ge=2, le=100)
    rate_limit_window_seconds: int = Field(default=20, ge=2, le=300)
    repeated_char_limit: int = Field(default=14, ge=4, le=100)
    punctuation_limit: int = Field(default=12, ge=4, le=100)
    emoji_limit: int = Field(default=16, ge=1, le=100)
    word_repeat_limit: int = Field(default=7, ge=2, le=30)
    cooldown_base_seconds: int = Field(default=2, ge=1, le=30)
    cooldown_max_seconds: int = Field(default=30, ge=2, le=300)
    rapid_count: int = Field(default=3, ge=2, le=10)
    rapid_window_seconds: float = Field(default=1.8, ge=0.5, le=10.0)

class AutoModSettingsUpdate(BaseModel):
    enabled: bool = True
    announce_actions: bool = True
    exempt_staff: bool = True
    profanity_mode: str = Field(default="blur", pattern="^(allow|blur|block)$")
    link_mode: str = Field(default="warn", pattern="^(allow|warn|block)$")
    max_links: int = Field(default=2, ge=0, le=20)
    max_mentions: int = Field(default=5, ge=1, le=50)
    warn_points: int = Field(default=1, ge=1, le=50)
    mute_points: int = Field(default=4, ge=2, le=100)
    mute_minutes: int = Field(default=10, ge=1, le=10080)
    temp_ban_points: int = Field(default=8, ge=3, le=200)
    temp_ban_minutes: int = Field(default=60, ge=1, le=43200)
    point_window_minutes: int = Field(default=1440, ge=5, le=43200)

class AutoModDecision(BaseModel):
    status: str = Field(pattern="^(resolved|ignored|open)$")
    note: str = Field(default="", max_length=500)
