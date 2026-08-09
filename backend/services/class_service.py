from __future__ import annotations
"""Utilitaires pour les classes et les serveurs de classe PiChat."""
from typing import Optional

import re
from database import get_db_cursor

CLASS_RE = re.compile(r"[A-Z0-9][A-Z0-9_-]{0,11}")


class InvalidClassCodeError(ValueError):
    pass


def normalize_class_code(value: Optional[str], *, required: bool = True) -> Optional[str]:
    if value is None:
        if required:
            raise InvalidClassCodeError("La classe est obligatoire.")
        return None
    code = value.strip().upper()
    if not code:
        if required:
            raise InvalidClassCodeError("La classe est obligatoire.")
        return None
    if not CLASS_RE.fullmatch(code):
        raise InvalidClassCodeError(
            "Classe invalide. Utilise 1 à 12 caractères : lettres, chiffres, tiret ou underscore (ex. 5C, 6C)."
        )
    return code


def ensure_class_room(class_code: str) -> dict:
    """Crée le serveur/salon principal d'une classe s'il n'existe pas."""
    code = normalize_class_code(class_code)
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id, name, class_code, created_at FROM rooms WHERE class_code = ? ORDER BY id ASC LIMIT 1",
            (code,),
        )
        row = cursor.fetchone()
        if row is None:
            name = f"Serveur {code}"
            # Si le nom existe déjà pour une autre raison, on ajoute la classe.
            cursor.execute("SELECT id FROM rooms WHERE name = ?", (name,))
            if cursor.fetchone() is not None:
                name = f"Classe {code}"
            cursor.execute("INSERT INTO rooms (name, class_code) VALUES (?, ?)", (name, code))
            room_id = cursor.lastrowid
            cursor.execute(
                "SELECT id, name, class_code, created_at FROM rooms WHERE id = ?",
                (room_id,),
            )
            row = cursor.fetchone()
            central = cursor.execute("SELECT id FROM spaces WHERE slug='pichat-central'").fetchone()
            if central is not None:
                cursor.execute("INSERT OR IGNORE INTO space_rooms(space_id,room_id,category,position) VALUES(?,?,'CLASSES',?)", (central["id"], room_id, room_id))
    return dict(row)
