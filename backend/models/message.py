"""
message.py (models)
--------------------
Modèles Pydantic liés aux messages de salon et aux messages privés.

Utilisés à partir du Milestone 4 (chat temps réel), définis dès maintenant
pour que la structure de données du projet soit visible dans son ensemble.
"""

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    """Données envoyées par le client pour poster un message dans un salon."""

    room_id: int
    content: str = Field(min_length=1, max_length=2000)


class MessagePublic(BaseModel):
    """Représentation d'un message telle qu'elle est renvoyée au frontend."""

    id: int
    room_id: int
    user_id: int
    username: str
    content: str
    created_at: str
    is_bot: bool = False
