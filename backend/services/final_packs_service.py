from __future__ import annotations

import hashlib

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from database import get_db_cursor
from services.backup_manager_service import create_backup, delete_backup
from services.message_service import save_message
from services.room_service import user_can_access_room
from services.moderation_service import restriction_status
from services.automod_service import review_message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _db_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Date d’envoi manquante.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Date d’envoi invalide.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_final_pack_settings() -> dict:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT * FROM final_pack_settings WHERE id=1").fetchone()
    if row is None:
        return {
            "scheduled_messages_enabled": True,
            "social_enabled": True,
            "session_manager_enabled": True,
            "auto_backup_enabled": False,
            "scheduled_max_days": 30,
            "edit_window_minutes": 1440,
            "delete_window_minutes": 60,
            "backup_interval_hours": 24,
            "backup_retention": 7,
        }
    return {
        "scheduled_messages_enabled": bool(row["scheduled_messages_enabled"]),
        "social_enabled": bool(row["social_enabled"]),
        "session_manager_enabled": bool(row["session_manager_enabled"]),
        "auto_backup_enabled": bool(row["auto_backup_enabled"]),
        "scheduled_max_days": int(row["scheduled_max_days"] or 30),
        "edit_window_minutes": int(row["edit_window_minutes"] or 0),
        "delete_window_minutes": int(row["delete_window_minutes"] or 0),
        "backup_interval_hours": int(row["backup_interval_hours"] or 24),
        "backup_retention": int(row["backup_retention"] or 7),
        "updated_at": row["updated_at"],
    }


def update_final_pack_settings(values: dict) -> dict:
    current = get_final_pack_settings()
    allowed = {
        "scheduled_messages_enabled",
        "social_enabled",
        "session_manager_enabled",
        "auto_backup_enabled",
        "scheduled_max_days",
        "edit_window_minutes",
        "delete_window_minutes",
        "backup_interval_hours",
        "backup_retention",
    }
    data = {key: values[key] for key in allowed if key in values}
    merged = {**current, **data}
    merged["scheduled_max_days"] = max(1, min(int(merged["scheduled_max_days"]), 365))
    merged["edit_window_minutes"] = max(0, min(int(merged["edit_window_minutes"]), 525600))
    merged["delete_window_minutes"] = max(0, min(int(merged["delete_window_minutes"]), 525600))
    merged["backup_interval_hours"] = max(1, min(int(merged["backup_interval_hours"]), 720))
    merged["backup_retention"] = max(1, min(int(merged["backup_retention"]), 60))
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE final_pack_settings SET
                scheduled_messages_enabled=?, social_enabled=?, session_manager_enabled=?,
                auto_backup_enabled=?, scheduled_max_days=?, edit_window_minutes=?,
                delete_window_minutes=?, backup_interval_hours=?, backup_retention=?,
                updated_at=datetime('now')
            WHERE id=1
            """,
            (
                1 if merged["scheduled_messages_enabled"] else 0,
                1 if merged["social_enabled"] else 0,
                1 if merged["session_manager_enabled"] else 0,
                1 if merged["auto_backup_enabled"] else 0,
                merged["scheduled_max_days"],
                merged["edit_window_minutes"],
                merged["delete_window_minutes"],
                merged["backup_interval_hours"],
                merged["backup_retention"],
            ),
        )
    return get_final_pack_settings()


def _within_window(created_at: str, minutes: int) -> bool:
    if minutes <= 0:
        return True
    try:
        created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    return _utc_now() <= created + timedelta(minutes=minutes)


def can_edit_own_message(created_at: str) -> bool:
    return _within_window(created_at, get_final_pack_settings()["edit_window_minutes"])


def can_delete_own_message(created_at: str) -> bool:
    return _within_window(created_at, get_final_pack_settings()["delete_window_minutes"])


def create_scheduled_message(user: dict, room_id: int, content: str, send_at: str, reply_to_id: Optional[int] = None) -> dict:
    settings = get_final_pack_settings()
    if not settings["scheduled_messages_enabled"]:
        raise PermissionError("Les messages programmés sont désactivés.")
    if not user_can_access_room(user, room_id):
        raise PermissionError("Tu n’as pas accès à ce salon.")
    restriction = restriction_status(user["id"])
    if restriction and restriction.get("is_muted"):
        raise PermissionError("Tu es en mode muet et ne peux pas programmer de message.")
    clean = (content or "").strip()[:2000]
    if not clean:
        raise ValueError("Le message ne peut pas être vide.")
    decision = review_message(user, room_id, clean)
    if decision.get("blocked") or decision.get("sanction") in {"mute", "temporary_ban"}:
        raise PermissionError("AutoModo refuse ce message programmé.")
    target = _parse_datetime(send_at)
    now = _utc_now()
    if target < now + timedelta(seconds=10):
        raise ValueError("Choisis une heure située au moins 10 secondes dans le futur.")
    if target > now + timedelta(days=settings["scheduled_max_days"]):
        raise ValueError("La date dépasse la limite autorisée par l’administrateur.")
    with get_db_cursor() as cursor:
        if reply_to_id:
            valid = cursor.execute(
                "SELECT 1 FROM messages WHERE id=? AND room_id=?",
                (int(reply_to_id), int(room_id)),
            ).fetchone()
            if valid is None:
                reply_to_id = None
        cursor.execute(
            """
            INSERT INTO scheduled_messages(user_id,room_id,content,reply_to_id,send_at,status)
            VALUES(?,?,?,?,?,'pending')
            """,
            (user["id"], room_id, clean, reply_to_id, _db_datetime(target)),
        )
        scheduled_id = cursor.lastrowid
    return get_scheduled_message(scheduled_id, user["id"])


def _scheduled_dict(row) -> dict:
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "room_id": int(row["room_id"]),
        "room_name": row["room_name"] if "room_name" in row.keys() else "",
        "content": row["content"],
        "reply_to_id": row["reply_to_id"],
        "send_at": row["send_at"],
        "status": row["status"],
        "created_at": row["created_at"],
        "sent_message_id": row["sent_message_id"],
        "error_message": row["error_message"] or "",
    }


def get_scheduled_message(scheduled_id: int, user_id: Optional[int] = None) -> Optional[dict]:
    params: List[object] = [int(scheduled_id)]
    extra = ""
    if user_id is not None:
        extra = " AND sm.user_id=?"
        params.append(int(user_id))
    with get_db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT sm.*,r.name AS room_name FROM scheduled_messages sm
            JOIN rooms r ON r.id=sm.room_id WHERE sm.id=?
            """ + extra,
            tuple(params),
        ).fetchone()
    return _scheduled_dict(row) if row else None


def list_scheduled_messages(user_id: int, include_finished: bool = False) -> List[dict]:
    clause = "" if include_finished else " AND sm.status='pending'"
    with get_db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT sm.*,r.name AS room_name FROM scheduled_messages sm
            JOIN rooms r ON r.id=sm.room_id
            WHERE sm.user_id=?
            """ + clause + " ORDER BY sm.send_at ASC,sm.id ASC LIMIT 200",
            (int(user_id),),
        ).fetchall()
    return [_scheduled_dict(row) for row in rows]


def cancel_scheduled_message(scheduled_id: int, user_id: int, is_admin: bool = False) -> bool:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT user_id,status FROM scheduled_messages WHERE id=?", (scheduled_id,)).fetchone()
        if row is None:
            return False
        if int(row["user_id"]) != int(user_id) and not is_admin:
            raise PermissionError("Tu ne peux annuler que tes propres messages programmés.")
        if row["status"] != "pending":
            raise ValueError("Ce message n’est plus en attente.")
        cursor.execute(
            "UPDATE scheduled_messages SET status='cancelled',cancelled_at=datetime('now') WHERE id=? AND status='pending'",
            (scheduled_id,),
        )
        return cursor.rowcount > 0


def process_due_scheduled_messages(limit: int = 50) -> List[Tuple[int, dict]]:
    now = _db_datetime(_utc_now())
    with get_db_cursor() as cursor:
        due = cursor.execute(
            """
            SELECT id,user_id,room_id,content,reply_to_id FROM scheduled_messages
            WHERE status='pending' AND send_at<=? ORDER BY send_at,id LIMIT ?
            """,
            (now, max(1, min(int(limit), 200))),
        ).fetchall()
    emitted: List[Tuple[int, dict]] = []
    for row in due:
        claimed = False
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE scheduled_messages SET status='processing' WHERE id=? AND status='pending'",
                (row["id"],),
            )
            claimed = cursor.rowcount > 0
        if not claimed:
            continue
        try:
            with get_db_cursor() as cursor:
                active = cursor.execute(
                    """SELECT id,is_banned,is_bot,is_admin,is_moderator,moderator_class_code,class_code,active_space_id
                       FROM users WHERE id=?""",
                    (row["user_id"],),
                ).fetchone()
                room = cursor.execute("SELECT id FROM rooms WHERE id=?", (row["room_id"],)).fetchone()
            if active is None or active["is_banned"] or active["is_bot"] or room is None:
                raise ValueError("Compte ou salon indisponible.")
            active_user = dict(active)
            if not user_can_access_room(active_user, int(row["room_id"])):
                raise PermissionError("Le compte n’a plus accès à ce salon.")
            restriction = restriction_status(int(row["user_id"]))
            if restriction and restriction.get("is_muted"):
                raise PermissionError("Le compte est en mode muet au moment de l’envoi.")
            message = save_message(
                int(row["room_id"]),
                int(row["user_id"]),
                row["content"],
                reply_to_id=row["reply_to_id"],
            )
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE scheduled_messages SET status='sent',sent_at=datetime('now'),sent_message_id=?,error_message=''
                    WHERE id=?
                    """,
                    (message["id"], row["id"]),
                )
            emitted.append((int(row["room_id"]), message))
        except Exception as exc:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "UPDATE scheduled_messages SET status='failed',error_message=? WHERE id=?",
                    (str(exc)[:300], row["id"]),
                )
    return emitted


def _pair(first: int, second: int) -> Tuple[int, int]:
    a, b = int(first), int(second)
    return (a, b) if a < b else (b, a)


def _shared_space(user_id: int, target_id: int) -> bool:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT 1 FROM space_members a JOIN space_members b ON b.space_id=a.space_id
            WHERE a.user_id=? AND b.user_id=? LIMIT 1
            """,
            (user_id, target_id),
        ).fetchone()
    return row is not None


def _is_blocked(user_id: int, target_id: int) -> bool:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT 1 FROM user_blocks
            WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?) LIMIT 1
            """,
            (user_id, target_id, target_id, user_id),
        ).fetchone()
    return row is not None


def send_friend_request(user: dict, target_id: int) -> dict:
    settings = get_final_pack_settings()
    if not settings["social_enabled"]:
        raise PermissionError("Le pack Social est désactivé.")
    target_id = int(target_id)
    if target_id == int(user["id"]):
        raise ValueError("Tu ne peux pas t’ajouter toi-même.")
    with get_db_cursor() as cursor:
        target = cursor.execute(
            "SELECT id,username,is_bot,is_banned FROM users WHERE id=?",
            (target_id,),
        ).fetchone()
    if target is None or target["is_bot"] or target["is_banned"]:
        raise ValueError("Compte indisponible.")
    if not user.get("is_admin") and not _shared_space(user["id"], target_id):
        raise PermissionError("Vous devez partager un établissement PiChat.")
    if _is_blocked(user["id"], target_id):
        raise PermissionError("Cette relation est bloquée.")
    low, high = _pair(user["id"], target_id)
    with get_db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id,requested_by,status FROM friendships WHERE user_low_id=? AND user_high_id=?",
            (low, high),
        ).fetchone()
        if existing:
            if existing["status"] == "accepted":
                raise ValueError("Vous êtes déjà amis.")
            if existing["status"] == "pending":
                if int(existing["requested_by"]) == target_id:
                    cursor.execute(
                        "UPDATE friendships SET status='accepted',responded_at=datetime('now') WHERE id=?",
                        (existing["id"],),
                    )
                    return {"accepted": True, "friendship_id": int(existing["id"])}
                raise ValueError("Demande déjà envoyée.")
            cursor.execute(
                """
                UPDATE friendships SET requested_by=?,status='pending',created_at=datetime('now'),responded_at=NULL
                WHERE id=?
                """,
                (user["id"], existing["id"]),
            )
            friendship_id = existing["id"]
        else:
            cursor.execute(
                """
                INSERT INTO friendships(user_low_id,user_high_id,requested_by,status)
                VALUES(?,?,?,'pending')
                """,
                (low, high, user["id"]),
            )
            friendship_id = cursor.lastrowid
    return {"accepted": False, "friendship_id": int(friendship_id)}


def respond_friend_request(user_id: int, friendship_id: int, accept: bool) -> dict:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT * FROM friendships WHERE id=? AND status='pending'",
            (friendship_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Demande introuvable.")
        if int(row["requested_by"]) == int(user_id) or int(user_id) not in {int(row["user_low_id"]), int(row["user_high_id"])}:
            raise PermissionError("Cette demande ne t’est pas destinée.")
        status = "accepted" if accept else "rejected"
        cursor.execute(
            "UPDATE friendships SET status=?,responded_at=datetime('now') WHERE id=?",
            (status, friendship_id),
        )
    return {"id": int(friendship_id), "status": status}


def remove_friend(user_id: int, target_id: int) -> bool:
    low, high = _pair(user_id, target_id)
    with get_db_cursor() as cursor:
        cursor.execute(
            "DELETE FROM friendships WHERE user_low_id=? AND user_high_id=?",
            (low, high),
        )
        return cursor.rowcount > 0


def block_user(user_id: int, target_id: int) -> None:
    target_id = int(target_id)
    if target_id == int(user_id):
        raise ValueError("Tu ne peux pas te bloquer toi-même.")
    with get_db_cursor() as cursor:
        target = cursor.execute("SELECT id,is_admin FROM users WHERE id=?", (target_id,)).fetchone()
        if target is None:
            raise ValueError("Compte introuvable.")
        if target["is_admin"]:
            raise PermissionError("Un administrateur ne peut pas être bloqué.")
        cursor.execute(
            "INSERT OR IGNORE INTO user_blocks(blocker_id,blocked_id) VALUES(?,?)",
            (user_id, target_id),
        )
        low, high = _pair(user_id, target_id)
        cursor.execute("DELETE FROM friendships WHERE user_low_id=? AND user_high_id=?", (low, high))


def unblock_user(user_id: int, target_id: int) -> bool:
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM user_blocks WHERE blocker_id=? AND blocked_id=?", (user_id, target_id))
        return cursor.rowcount > 0


def _public_user(row) -> dict:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "class_code": row["class_code"],
        "profile_color": row["profile_color"] or "#5865f2",
        "status_message": row["status_message"] or "",
    }


def social_overview(user_id: int) -> dict:
    with get_db_cursor() as cursor:
        friendships = cursor.execute(
            """
            SELECT f.*,
                   low.username AS low_username,low.class_code AS low_class,low.profile_color AS low_color,low.status_message AS low_status,
                   high.username AS high_username,high.class_code AS high_class,high.profile_color AS high_color,high.status_message AS high_status
            FROM friendships f
            JOIN users low ON low.id=f.user_low_id JOIN users high ON high.id=f.user_high_id
            WHERE f.user_low_id=? OR f.user_high_id=? ORDER BY f.created_at DESC
            """,
            (user_id, user_id),
        ).fetchall()
        blocked = cursor.execute(
            """
            SELECT u.id,u.username,u.class_code,u.profile_color,u.status_message
            FROM user_blocks b JOIN users u ON u.id=b.blocked_id
            WHERE b.blocker_id=? ORDER BY u.username COLLATE NOCASE
            """,
            (user_id,),
        ).fetchall()
    friends, incoming, outgoing = [], [], []
    for row in friendships:
        other_low = int(row["user_low_id"]) != int(user_id)
        other = {
            "id": int(row["user_low_id"] if other_low else row["user_high_id"]),
            "username": row["low_username"] if other_low else row["high_username"],
            "class_code": row["low_class"] if other_low else row["high_class"],
            "profile_color": (row["low_color"] if other_low else row["high_color"]) or "#5865f2",
            "status_message": (row["low_status"] if other_low else row["high_status"]) or "",
            "friendship_id": int(row["id"]),
        }
        if row["status"] == "accepted":
            friends.append(other)
        elif row["status"] == "pending":
            if int(row["requested_by"]) == int(user_id):
                outgoing.append(other)
            else:
                incoming.append(other)
    return {
        "friends": friends,
        "incoming": incoming,
        "outgoing": outgoing,
        "blocked": [_public_user(row) for row in blocked],
    }


def search_social_users(user: dict, query: str) -> List[dict]:
    clean = (query or "").strip()
    if len(clean) < 2:
        return []
    with get_db_cursor() as cursor:
        if user.get("is_admin"):
            rows = cursor.execute(
                """
                SELECT id,username,class_code,profile_color,status_message FROM users
                WHERE id!=? AND is_bot=0 AND is_banned=0 AND username LIKE ?
                ORDER BY username COLLATE NOCASE LIMIT 30
                """,
                (user["id"], "%" + clean + "%"),
            ).fetchall()
        else:
            rows = cursor.execute(
                """
                SELECT DISTINCT u.id,u.username,u.class_code,u.profile_color,u.status_message
                FROM space_members mine JOIN space_members other ON other.space_id=mine.space_id
                JOIN users u ON u.id=other.user_id
                WHERE mine.user_id=? AND u.id!=? AND u.is_bot=0 AND u.is_banned=0 AND u.username LIKE ?
                ORDER BY u.username COLLATE NOCASE LIMIT 30
                """,
                (user["id"], user["id"], "%" + clean + "%"),
            ).fetchall()
    overview = social_overview(user["id"])
    friend_ids = {item["id"] for item in overview["friends"]}
    incoming_ids = {item["id"] for item in overview["incoming"]}
    outgoing_ids = {item["id"] for item in overview["outgoing"]}
    blocked_ids = {item["id"] for item in overview["blocked"]}
    result = []
    for row in rows:
        item = _public_user(row)
        uid = item["id"]
        item["relation"] = (
            "friend" if uid in friend_ids else
            "incoming" if uid in incoming_ids else
            "outgoing" if uid in outgoing_ids else
            "blocked" if uid in blocked_ids else
            "none"
        )
        result.append(item)
    return result


def _session_public_id(token: str) -> int:
    # Identifiant stable non secret : évite le rowid SQLite, inexistant sur PostgreSQL.
    raw = hashlib.sha256((token or "").encode("utf-8")).digest()[:8]
    return int.from_bytes(raw, "big") & 0x7FFFFFFFFFFFFFFF


def list_user_sessions(user_id: int, current_token: Optional[str]) -> List[dict]:
    settings = get_final_pack_settings()
    if not settings["session_manager_enabled"]:
        raise PermissionError("Le gestionnaire de sessions est désactivé.")
    with get_db_cursor() as cursor:
        rows = cursor.execute(
            """SELECT token,created_at,last_seen_at,user_agent,ip_address
               FROM sessions WHERE user_id=? ORDER BY COALESCE(last_seen_at,created_at) DESC""",
            (user_id,),
        ).fetchall()
    result = []
    for row in rows:
        result.append({
            "id": _session_public_id(row["token"]),
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"] or row["created_at"],
            "user_agent": row["user_agent"] or "Appareil inconnu",
            "ip_address": row["ip_address"] or "—",
            "current": bool(current_token and row["token"] == current_token),
        })
    return result


def revoke_user_session(user_id: int, session_id: int, current_token: Optional[str]) -> bool:
    with get_db_cursor() as cursor:
        rows = cursor.execute("SELECT token FROM sessions WHERE user_id=?", (user_id,)).fetchall()
        token = next((row["token"] for row in rows if _session_public_id(row["token"]) == int(session_id)), None)
        if not token:
            return False
        if current_token and token == current_token:
            raise ValueError("Utilise le bouton Déconnexion pour fermer la session actuelle.")
        cursor.execute("DELETE FROM sessions WHERE token=? AND user_id=?", (token, user_id))
        return cursor.rowcount > 0


def revoke_other_sessions(user_id: int, current_token: Optional[str]) -> int:
    with get_db_cursor() as cursor:
        if current_token:
            cursor.execute("DELETE FROM sessions WHERE user_id=? AND token!=?", (user_id, current_token))
        else:
            cursor.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return int(cursor.rowcount)


def auto_backup_status() -> dict:
    with get_db_cursor() as cursor:
        latest = cursor.execute(
            "SELECT * FROM auto_backup_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        count = cursor.execute("SELECT COUNT(*) AS count FROM auto_backup_runs").fetchone()["count"]
    return {
        "count": int(count or 0),
        "last": dict(latest) if latest else None,
    }


def run_auto_backup(force: bool = False) -> Optional[dict]:
    settings = get_final_pack_settings()
    if not force and not settings["auto_backup_enabled"]:
        return None
    status = auto_backup_status()
    if not force and status["last"]:
        raw = status["last"].get("created_at")
        try:
            last = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            last = _utc_now() - timedelta(days=999)
        if _utc_now() < last + timedelta(hours=settings["backup_interval_hours"]):
            return None
    backup_path = create_backup(
        label="Sauvegarde automatique",
        note="Créée par le Pack Maintenance PiChat 2.2.",
    )
    expired_names = []
    with get_db_cursor() as cursor:
        cursor.execute(
            "INSERT INTO auto_backup_runs(backup_name,status) VALUES(?,'success')",
            (backup_path.name,),
        )
        rows = cursor.execute(
            "SELECT id,backup_name FROM auto_backup_runs ORDER BY id DESC"
        ).fetchall()
        for old in rows[settings["backup_retention"]:]:
            expired_names.append(str(old["backup_name"]))
            cursor.execute("DELETE FROM auto_backup_runs WHERE id=?", (old["id"],))
    # Supprime également l’archive persistante (PostgreSQL), pas seulement le cache disque.
    for old_name in expired_names:
        try:
            delete_backup(old_name)
        except Exception:
            pass
    return {"name": backup_path.name, "path": str(backup_path)}


async def final_pack_worker() -> None:
    from connection_manager import manager

    while True:
        try:
            for room_id, message in process_due_scheduled_messages():
                await manager.broadcast_to_room(room_id, {"type": "new_message", "message": message})
            await asyncio.to_thread(run_auto_backup, False)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Le worker ne doit jamais faire tomber le chat. Les erreurs sont
            # visibles dans les statuts des messages ou au prochain diagnostic.
            pass
        await asyncio.sleep(5)
