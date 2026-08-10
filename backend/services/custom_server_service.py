from __future__ import annotations

import re
import secrets
import sqlite3

from database import get_db_cursor, IntegrityError
from services.pycoin_service import get_economy_settings



class CustomServerError(Exception):
    pass


def _clean_name(value: str) -> str:
    name = re.sub(r"\s+", " ", (value or "").strip())
    if len(name) < 2 or len(name) > 40:
        raise CustomServerError("Le nom doit contenir entre 2 et 40 caractères.")
    return name


def _clean_icon(value: str) -> str:
    icon = (value or "💬").strip()[:8]
    return icon or "💬"


def _server_row(cursor, server_id: int, viewer_id=None):
    row = cursor.execute(
        """SELECT r.id,r.name,r.class_code,r.created_at,r.slow_mode_seconds,r.room_kind,
                  r.owner_user_id,r.description,r.icon,r.invite_code,
                  u.username AS owner_username
           FROM rooms r LEFT JOIN users u ON u.id=r.owner_user_id WHERE r.id=?""",
        (server_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["is_owner"] = viewer_id is not None and int(result.get("owner_user_id") or 0) == int(viewer_id)
    return result


def list_custom_servers(user_id: int, is_admin: bool = False) -> list:
    with get_db_cursor() as cursor:
        if is_admin:
            rows = cursor.execute(
                """SELECT r.id FROM rooms r WHERE r.room_kind='custom' ORDER BY r.created_at DESC"""
            ).fetchall()
        else:
            rows = cursor.execute(
                """SELECT r.id FROM rooms r
                   JOIN custom_server_members m ON m.server_id=r.id
                   WHERE r.room_kind='custom' AND m.user_id=? ORDER BY r.created_at DESC""",
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            server = _server_row(cursor, int(row["id"]), user_id)
            if server:
                result.append(server)
    return result


def create_custom_server(user_id: int, name: str, description: str = "", icon: str = "💬") -> dict:
    settings = get_economy_settings()
    create_cost = settings["server_creation_cost"]
    max_servers = settings["max_owned_servers"]
    name = _clean_name(name)
    description = (description or "").strip()[:160]
    icon = _clean_icon(icon)
    invite_code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10].upper()
    with get_db_cursor() as cursor:
        owned = cursor.execute(
            "SELECT COUNT(*) AS n FROM rooms WHERE room_kind='custom' AND owner_user_id=?",
            (user_id,),
        ).fetchone()["n"]
        if int(owned) >= max_servers:
            raise CustomServerError(f"Tu possèdes déjà {max_servers} serveurs personnels, la limite maximale.")
        user = cursor.execute("SELECT coins FROM users WHERE id=?", (user_id,)).fetchone()
        if user is None:
            raise CustomServerError("Compte introuvable.")
        if int(user["coins"] or 0) < create_cost:
            raise CustomServerError(f"Il faut {create_cost} PyCoins pour créer un serveur.")
        try:
            cursor.execute(
                """INSERT INTO rooms
                   (name,class_code,room_kind,owner_user_id,description,icon,invite_code)
                   VALUES (?,NULL,'custom',?,?,?,?)""",
                (name, user_id, description, icon, invite_code),
            )
        except IntegrityError:
            raise CustomServerError("Un salon ou serveur porte déjà ce nom.")
        server_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO custom_server_members (server_id,user_id,member_role) VALUES (?,?,'owner')",
            (server_id, user_id),
        )
        cursor.execute("UPDATE users SET coins=coins-? WHERE id=?", (create_cost, user_id))
        balance = cursor.execute("SELECT coins FROM users WHERE id=?", (user_id,)).fetchone()["coins"]
        cursor.execute(
            """INSERT INTO pycoin_transactions
               (user_id,amount,balance_after,kind,details)
               VALUES (?,?,?,?,?)""",
            (user_id, -create_cost, int(balance), "server_creation", f"Création du serveur {name}"),
        )
        return _server_row(cursor, server_id, user_id)


def join_custom_server(user_id: int, invite_code: str) -> dict:
    code = re.sub(r"[^A-Za-z0-9]", "", (invite_code or "").upper())[:16]
    if not code:
        raise CustomServerError("Code d'invitation manquant.")
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT id FROM rooms WHERE room_kind='custom' AND invite_code=?",
            (code,),
        ).fetchone()
        if row is None:
            raise CustomServerError("Code d'invitation invalide.")
        server_id = int(row["id"])
        cursor.execute(
            "INSERT OR IGNORE INTO custom_server_members (server_id,user_id) VALUES (?,?)",
            (server_id, user_id),
        )
        return _server_row(cursor, server_id, user_id)


def add_member(server_id: int, actor_id: int, username: str, is_admin: bool = False) -> dict:
    with get_db_cursor() as cursor:
        server = _server_row(cursor, server_id, actor_id)
        if not server or server.get("room_kind") != "custom":
            raise CustomServerError("Serveur introuvable.")
        if not is_admin and int(server.get("owner_user_id") or 0) != int(actor_id):
            raise CustomServerError("Seul le propriétaire peut ajouter un membre.")
        user = cursor.execute(
            "SELECT id,username,is_bot FROM users WHERE username=? COLLATE NOCASE",
            ((username or "").strip(),),
        ).fetchone()
        if user is None or bool(user["is_bot"]):
            raise CustomServerError("Compte introuvable.")
        cursor.execute(
            "INSERT OR IGNORE INTO custom_server_members (server_id,user_id) VALUES (?,?)",
            (server_id, int(user["id"])),
        )
        return {"server_id": server_id, "user_id": int(user["id"]), "username": user["username"]}


def customize_server(server_id: int, actor_id: int, name: str, description: str, icon: str, is_admin=False) -> dict:
    customize_cost = get_economy_settings()["server_customization_cost"]
    name = _clean_name(name)
    description = (description or "").strip()[:160]
    icon = _clean_icon(icon)
    with get_db_cursor() as cursor:
        server = _server_row(cursor, server_id, actor_id)
        if not server or server.get("room_kind") != "custom":
            raise CustomServerError("Serveur introuvable.")
        if not is_admin and int(server.get("owner_user_id") or 0) != int(actor_id):
            raise CustomServerError("Seul le propriétaire peut modifier ce serveur.")
        if not is_admin:
            balance = cursor.execute("SELECT coins FROM users WHERE id=?", (actor_id,)).fetchone()["coins"]
            if int(balance or 0) < customize_cost:
                raise CustomServerError(f"Il faut {customize_cost} PyCoins pour modifier le serveur.")
        try:
            cursor.execute(
                "UPDATE rooms SET name=?,description=?,icon=? WHERE id=?",
                (name, description, icon, server_id),
            )
        except IntegrityError:
            raise CustomServerError("Ce nom est déjà utilisé.")
        if not is_admin:
            cursor.execute("UPDATE users SET coins=coins-? WHERE id=?", (customize_cost, actor_id))
            balance = cursor.execute("SELECT coins FROM users WHERE id=?", (actor_id,)).fetchone()["coins"]
            cursor.execute(
                """INSERT INTO pycoin_transactions
                   (user_id,amount,balance_after,kind,details)
                   VALUES (?,?,?,?,?)""",
                (actor_id, -customize_cost, int(balance), "server_customization", f"Modification du serveur {name}"),
            )
        return _server_row(cursor, server_id, actor_id)


def leave_custom_server(server_id: int, user_id: int) -> None:
    with get_db_cursor() as cursor:
        server = _server_row(cursor, server_id, user_id)
        if not server or server.get("room_kind") != "custom":
            raise CustomServerError("Serveur introuvable.")
        if int(server.get("owner_user_id") or 0) == int(user_id):
            raise CustomServerError("Le propriétaire doit supprimer son serveur au lieu de le quitter.")
        cursor.execute("DELETE FROM custom_server_members WHERE server_id=? AND user_id=?", (server_id, user_id))


def delete_custom_server(server_id: int, actor_id: int, is_admin=False) -> None:
    with get_db_cursor() as cursor:
        server = _server_row(cursor, server_id, actor_id)
        if not server or server.get("room_kind") != "custom":
            raise CustomServerError("Serveur introuvable.")
        if not is_admin and int(server.get("owner_user_id") or 0) != int(actor_id):
            raise CustomServerError("Seul le propriétaire peut supprimer ce serveur.")
        cursor.execute("DELETE FROM rooms WHERE id=?", (server_id,))
