"""
bot.py (models)
---------------
Modèles Pydantic liés aux bots locaux de PiChat.

Un bot est un compte spécial créé par un administrateur. Il ne peut pas se
connecter comme un utilisateur classique. Lorsqu'il est mentionné dans un
salon avec @NomDuBot, PiChat génère automatiquement sa réponse à partir du
modèle de réponse configuré dans l'administration.
"""

from pydantic import BaseModel, Field


class BotCreate(BaseModel):
    """Données nécessaires pour créer un bot."""

    name: str = Field(min_length=3, max_length=32)
    response_template: str = Field(min_length=1, max_length=1000)


class BotToggle(BaseModel):
    """Permet d'activer ou de désactiver un bot."""

    enabled: bool


class BotPublic(BaseModel):
    """Représentation d'un bot renvoyée à l'interface d'administration."""

    id: int
    user_id: int
    name: str
    response_template: str
    enabled: bool
    created_at: str
