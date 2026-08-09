from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from database import get_db_cursor
from security import generate_session_token


class SupportAccessError(Exception):
    pass


def _utc_sql(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_support_link(admin: dict, target_user_id: int, reason: str = "", validity_minutes: int = 5) -> dict:
    if not admin.get("is_admin"):
        raise SupportAccessError("Réservé aux administrateurs.")
    with get_db_cursor() as cursor:
        target = cursor.execute(
            "SELECT id,username,is_admin,is_bot FROM users WHERE id=?",
            (target_user_id,),
        ).fetchone()
        if target is None:
            raise SupportAccessError("Compte introuvable.")
        if bool(target["is_bot"]):
            raise SupportAccessError("Impossible d'ouvrir un accès assistance sur un bot.")
        if bool(target["is_admin"]):
            raise SupportAccessError("L'accès assistance vers un autre administrateur est désactivé.")
        if int(target["id"]) == int(admin["id"]):
            raise SupportAccessError("Tu es déjà connecté à ton compte.")
        raw_token = secrets.token_urlsafe(32)
        expires_at = _utc_sql(max(1, min(int(validity_minutes), 15)))
        cursor.execute(
            """INSERT INTO support_access_links
               (token_hash,admin_id,target_user_id,reason,expires_at)
               VALUES (?,?,?,?,?)""",
            (_hash_token(raw_token), admin["id"], target_user_id, (reason or "")[:240], expires_at),
        )
    return {
        "token": raw_token,
        "url": f"/support/{raw_token}",
        "target_username": target["username"],
        "expires_at": expires_at,
        "one_time": True,
    }


def consume_support_link(raw_token: str, admin: dict, session_minutes: int = 10) -> dict:
    if not admin.get("is_admin"):
        raise SupportAccessError("Tu dois être connecté en administrateur.")
    token_hash = _hash_token(raw_token)
    now_sql = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_cursor() as cursor:
        link = cursor.execute(
            """SELECT id,admin_id,target_user_id,reason,expires_at,used_at
               FROM support_access_links WHERE token_hash=?""",
            (token_hash,),
        ).fetchone()
        if link is None:
            raise SupportAccessError("Lien d'assistance invalide.")
        if int(link["admin_id"]) != int(admin["id"]):
            raise SupportAccessError("Ce lien appartient à un autre administrateur.")
        if link["used_at"]:
            raise SupportAccessError("Ce lien a déjà été utilisé.")
        if str(link["expires_at"]) <= now_sql:
            raise SupportAccessError("Ce lien a expiré.")
        target = cursor.execute(
            "SELECT id,username,is_banned,is_bot FROM users WHERE id=?",
            (link["target_user_id"],),
        ).fetchone()
        if target is None or bool(target["is_bot"]):
            raise SupportAccessError("Compte cible indisponible.")
        if bool(target["is_banned"]):
            raise SupportAccessError("Le compte cible est actuellement banni.")
        cursor.execute("UPDATE support_access_links SET used_at=datetime('now') WHERE id=?", (link["id"],))
        session_token = generate_session_token()
        cursor.execute("INSERT INTO sessions (token,user_id) VALUES (?,?)", (session_token, target["id"]))
        session_expires = _utc_sql(max(1, min(int(session_minutes), 30)))
        cursor.execute(
            """INSERT INTO support_sessions
               (token,admin_id,target_user_id,expires_at) VALUES (?,?,?,?)""",
            (session_token, admin["id"], target["id"], session_expires),
        )
    return {
        "session_token": session_token,
        "target_user_id": int(target["id"]),
        "target_username": target["username"],
        "expires_at": session_expires,
        "reason": link["reason"] or "",
    }


def get_support_session(session_token: str):
    if not session_token:
        return None
    now_sql = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_cursor() as cursor:
        row = cursor.execute(
            """SELECT ss.token,ss.admin_id,ss.target_user_id,ss.expires_at,
                      a.username AS admin_username,t.username AS target_username
               FROM support_sessions ss
               JOIN users a ON a.id=ss.admin_id
               JOIN users t ON t.id=ss.target_user_id
               WHERE ss.token=?""",
            (session_token,),
        ).fetchone()
        if row is None:
            return None
        if str(row["expires_at"]) <= now_sql:
            cursor.execute("DELETE FROM support_sessions WHERE token=?", (session_token,))
            cursor.execute("DELETE FROM sessions WHERE token=?", (session_token,))
            return None
        return dict(row)


def end_support_session(session_token: str) -> dict:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT admin_id,target_user_id FROM support_sessions WHERE token=?",
            (session_token,),
        ).fetchone()
        if row is None:
            raise SupportAccessError("Aucune session d'assistance active.")
        admin = cursor.execute(
            "SELECT id,username,is_admin FROM users WHERE id=?",
            (row["admin_id"],),
        ).fetchone()
        if admin is None or not bool(admin["is_admin"]):
            raise SupportAccessError("Le compte administrateur n'est plus disponible.")
        cursor.execute("DELETE FROM support_sessions WHERE token=?", (session_token,))
        cursor.execute("DELETE FROM sessions WHERE token=?", (session_token,))
        new_token = generate_session_token()
        cursor.execute("INSERT INTO sessions (token,user_id) VALUES (?,?)", (new_token, admin["id"]))
    return {"session_token": new_token, "admin_id": int(admin["id"]), "admin_username": admin["username"]}
