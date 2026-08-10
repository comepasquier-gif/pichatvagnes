from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ArcadeActionRequest(BaseModel):
    action: str = Field(default="submit", max_length=24)
    guess: Optional[int] = Field(default=None, ge=1, le=100)
    answers: List[int] = Field(default_factory=list, max_length=12)
    moves: Optional[int] = Field(default=None, ge=1, le=500)
    elapsed_ms: Optional[int] = Field(default=None, ge=0, le=300000)
    clicks: Optional[int] = Field(default=None, ge=0, le=500)
    cell: Optional[int] = Field(default=None, ge=0, le=8)
    details: Dict[str, Any] = Field(default_factory=dict)


class ArcadeSettingsUpdate(BaseModel):
    enabled: bool = True
    rewards_enabled: bool = True
    rewarded_plays_per_day: int = Field(default=5, ge=0, le=50)
    daily_coin_cap: int = Field(default=30, ge=0, le=1000)
    daily_challenge_coins: int = Field(default=25, ge=0, le=1000)
    daily_challenge_xp: int = Field(default=40, ge=0, le=5000)
