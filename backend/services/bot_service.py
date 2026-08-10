"""
bot_service.py
--------------
Gestion des bots locaux de PiChat.

Les bots n'appellent aucun service externe : leur réponse est construite à
partir d'un modèle configuré par l'administrateur. Deux variables sont
supportées dans le texte de réponse :
- {user}    : pseudo de la personne qui a appelé le bot
- {message} : contenu envoyé au bot, sans la mention @NomDuBot
"""

import re
import secrets
import sqlite3
from typing import List

from database import get_db_cursor, IntegrityError
from security import hash_password
from services.message_service import save_message


class BotAlreadyExistsError(Exception):
    pass


class BotNotFoundError(Exception):
    pass


class InvalidBotNameError(Exception):
    pass


def _validate_bot_name(name: str) -> str:
    """Nettoie et valide un nom utilisable dans une mention @NomDuBot."""
    clean_name = name.strip()

    # Les espaces rendraient les mentions ambiguës. On autorise lettres,
    # chiffres, tiret et underscore, avec une lettre/chiffre au début.
    if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9_-]{2,31}", clean_name):
        raise InvalidBotNameError(
            "Le nom du bot doit contenir 3 à 32 caractères sans espace "
            "(lettres, chiffres, tiret ou underscore)."
        )

    return clean_name


def list_bots() -> list:
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT bots.id, bots.user_id, users.username AS name,
                   bots.response_template, bots.enabled, bots.created_at
            FROM bots
            JOIN users ON users.id = bots.user_id
            ORDER BY bots.created_at ASC, bots.id ASC
            """
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "response_template": row["response_template"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_bot(name: str, response_template: str) -> dict:
    clean_name = _validate_bot_name(name)
    clean_template = response_template.strip()

    if not clean_template:
        raise ValueError("La réponse du bot ne peut pas être vide.")

    # Le mot de passe n'est jamais communiqué et l'authentification refuse
    # explicitement les comptes is_bot. Le hash sert uniquement à conserver
    # la contrainte NOT NULL de la table users existante.
    disabled_password_hash = hash_password(secrets.token_urlsafe(32))

    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, is_bot, status_message)
                VALUES (?, ?, 1, ?)
                """,
                (clean_name, disabled_password_hash, "Bot PiChat"),
            )
            user_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO bots (user_id, response_template, enabled)
                VALUES (?, ?, 1)
                """,
                (user_id, clean_template),
            )
            bot_id = cursor.lastrowid

            cursor.execute(
                """
                SELECT bots.id, bots.user_id, users.username AS name,
                       bots.response_template, bots.enabled, bots.created_at
                FROM bots
                JOIN users ON users.id = bots.user_id
                WHERE bots.id = ?
                """,
                (bot_id,),
            )
            row = cursor.fetchone()

    except IntegrityError:
        raise BotAlreadyExistsError(f"Le nom '{clean_name}' est déjà utilisé.")

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "response_template": row["response_template"],
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
    }


def set_bot_enabled(bot_id: int, enabled: bool) -> dict:
    with get_db_cursor() as cursor:
        cursor.execute("UPDATE bots SET enabled = ? WHERE id = ?", (int(enabled), bot_id))

        if cursor.rowcount == 0:
            raise BotNotFoundError("Bot introuvable.")

        cursor.execute(
            """
            SELECT bots.id, bots.user_id, users.username AS name,
                   bots.response_template, bots.enabled, bots.created_at
            FROM bots
            JOIN users ON users.id = bots.user_id
            WHERE bots.id = ?
            """,
            (bot_id,),
        )
        row = cursor.fetchone()

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "response_template": row["response_template"],
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
    }


def delete_bot(bot_id: int) -> None:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT user_id FROM bots WHERE id = ?", (bot_id,))
        row = cursor.fetchone()

        if row is None:
            raise BotNotFoundError("Bot introuvable.")

        # La suppression de users entraîne aussi celle du bot et de ses
        # messages grâce aux contraintes ON DELETE CASCADE.
        cursor.execute("DELETE FROM users WHERE id = ?", (row["user_id"],))


def _message_for_bot(content: str, bot_name: str) -> str:
    """Retire la mention du bot pour produire la variable {message}."""
    pattern = re.compile(r"@" + re.escape(bot_name) + r"\b", re.IGNORECASE)
    cleaned = pattern.sub("", content, count=1).strip()
    return cleaned or "(aucun message)"


def build_bot_replies(room_id: int, sender: dict, content: str) -> List[dict]:
    """
    Détecte les bots actifs mentionnés et enregistre leurs réponses.

    Un bot répond au maximum une fois par message. Seuls les messages reçus
    d'un vrai utilisateur passent par cette fonction, ce qui évite toute
    boucle bot -> bot.
    """
    replies = []

    for bot in list_bots():
        if not bot["enabled"]:
            continue

        mention_pattern = re.compile(r"@" + re.escape(bot["name"]) + r"\b", re.IGNORECASE)
        if not mention_pattern.search(content):
            continue

        user_message = _message_for_bot(content, bot["name"])
        response = bot["response_template"]
        response = response.replace("{user}", sender["username"])
        response = response.replace("{message}", user_message)
        response = response[:2000]

        replies.append(save_message(room_id, bot["user_id"], response))

    return replies
