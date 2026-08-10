from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class TextMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    reply_to_id: Optional[int] = Field(default=None, ge=1)


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class DirectMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    reply_to_id: Optional[int] = Field(default=None, ge=1)


class TutorPlusRequest(BaseModel):
    subject: str = Field(default="Général", max_length=60)
    mode: str = Field(default="hint", pattern="^(hint|method|explain|check|quiz|flashcards|revision|similar)$")
    prompt: str = Field(min_length=2, max_length=5000)
    student_answer: str = Field(default="", max_length=4000)
    difficulty: str = Field(default="adaptée", max_length=30)
    count: int = Field(default=5, ge=2, le=20)


class StudySetCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    subject: str = Field(default="Général", max_length=60)
    kind: str = Field(default="flashcards", pattern="^(flashcards|quiz|notes)$")
    items: list[dict] = Field(default_factory=list, max_length=50)


class StudyAttemptRequest(BaseModel):
    score: int = Field(ge=0)
    total: int = Field(ge=0)
    answers: list = Field(default_factory=list, max_length=100)


class RPGClassRequest(BaseModel):
    rpg_class: str = Field(pattern="^(aventurier|mage|gardien|éclaireur|eclaireur)$")


class RPGItemRequest(BaseModel):
    item_code: str = Field(min_length=2, max_length=40)


class RPGBossAttackRequest(BaseModel):
    style: str = Field(default="normal", pattern="^(normal|power|careful)$")


class DeploymentSettingsRequest(BaseModel):
    public_url: str = Field(default="", max_length=240)
    allowed_hosts: str = Field(default="localhost,127.0.0.1", max_length=500)
    proxy_headers: bool = False
    https_enabled: bool = False
    internet_ready: bool = False
