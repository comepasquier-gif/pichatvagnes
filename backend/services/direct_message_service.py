from __future__ import annotations
from typing import Optional

from database import get_db_cursor


def _user_public(row):
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "class_code": row["class_code"],
        "profile_color": row["profile_color"] or "#5865f2",
        "status_message": row["status_message"] or "",
        "is_admin": bool(row["is_admin"]),
        "is_moderator": bool(row["is_moderator"]),
    }


def users_available_for_dm(user: dict):
    """Membres joignables : amis, même classe, espace ou serveur partagé.

    Cette logique garde la compatibilité avec les anciennes instances PiChat où
    ``space_members`` peut être vide après une migration 3.x.
    """
    uid = int(user["id"])
    class_code = str(user.get("class_code") or "").strip()
    with get_db_cursor() as c:
        if user.get("is_admin"):
            rows = c.execute(
                """SELECT id,username,class_code,profile_color,status_message,is_admin,is_moderator
                   FROM users WHERE id!=? AND is_bot=0 AND is_banned=0
                   ORDER BY username COLLATE NOCASE LIMIT 500""",
                (uid,),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT DISTINCT u.id,u.username,u.class_code,u.profile_color,u.status_message,u.is_admin,u.is_moderator
                   FROM users u
                   WHERE u.id!=? AND u.is_bot=0 AND u.is_banned=0 AND (
                     (? != '' AND COALESCE(u.class_code,'')=?)
                     OR EXISTS (
                       SELECT 1 FROM friendships f
                       WHERE f.status='accepted'
                         AND ((f.user_low_id=? AND f.user_high_id=u.id) OR (f.user_high_id=? AND f.user_low_id=u.id))
                     )
                     OR EXISTS (
                       SELECT 1 FROM space_members mine JOIN space_members other ON other.space_id=mine.space_id
                       WHERE mine.user_id=? AND other.user_id=u.id
                     )
                     OR EXISTS (
                       SELECT 1 FROM custom_server_members mine JOIN custom_server_members other ON other.server_id=mine.server_id
                       WHERE mine.user_id=? AND other.user_id=u.id
                     )
                   )
                   ORDER BY u.username COLLATE NOCASE LIMIT 500""",
                (uid, class_code, class_code, uid, uid, uid, uid),
            ).fetchall()
    return [_user_public(r) for r in rows]

def can_dm(sender: dict, target_id: int) -> bool:
    uid = int(sender["id"])
    target_id = int(target_id)
    if uid == target_id:
        return False
    with get_db_cursor() as c:
        target = c.execute("SELECT id,is_bot,is_banned,class_code FROM users WHERE id=?", (target_id,)).fetchone()
        if not target or target["is_bot"] or target["is_banned"]:
            return False
        blocked = c.execute(
            """SELECT 1 FROM user_blocks WHERE
               (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?) LIMIT 1""",
            (uid, target_id, target_id, uid),
        ).fetchone()
        if blocked:
            return False
        if sender.get("is_admin"):
            return True

        sender_class = str(sender.get("class_code") or "").strip()
        target_class = str(target["class_code"] or "").strip()
        if sender_class and sender_class == target_class:
            return True

        low, high = sorted((uid, target_id))
        friend = c.execute(
            "SELECT 1 FROM friendships WHERE user_low_id=? AND user_high_id=? AND status='accepted' LIMIT 1",
            (low, high),
        ).fetchone()
        if friend:
            return True

        shared_space = c.execute(
            """SELECT 1 FROM space_members a JOIN space_members b ON b.space_id=a.space_id
               WHERE a.user_id=? AND b.user_id=? LIMIT 1""",
            (uid, target_id),
        ).fetchone()
        if shared_space:
            return True

        shared_server = c.execute(
            """SELECT 1 FROM custom_server_members a JOIN custom_server_members b ON b.server_id=a.server_id
               WHERE a.user_id=? AND b.user_id=? LIMIT 1""",
            (uid, target_id),
        ).fetchone()
    return shared_server is not None

def _reply_preview(c, reply_to_id):
    if not reply_to_id:
        return None
    r = c.execute(
        """SELECT pm.id,pm.content,u.username FROM private_messages pm
           JOIN users u ON u.id=pm.sender_id WHERE pm.id=?""",
        (reply_to_id,),
    ).fetchone()
    if not r:
        return {"id": int(reply_to_id), "username": "Message supprimé", "content": "Indisponible"}
    return {"id": int(r["id"]), "username": r["username"], "content": (r["content"] or "")[:180]}


def _serialize(c, row, viewer_id: int):
    other_id = row["receiver_id"] if int(row["sender_id"]) == int(viewer_id) else row["sender_id"]
    other_name = row["receiver_username"] if int(row["sender_id"]) == int(viewer_id) else row["sender_username"]
    return {
        "id": int(row["id"]),
        "sender_id": int(row["sender_id"]),
        "receiver_id": int(row["receiver_id"]),
        "sender_username": row["sender_username"],
        "receiver_username": row["receiver_username"],
        "other_user_id": int(other_id),
        "other_username": other_name,
        "content": row["content"],
        "created_at": row["created_at"],
        "edited_at": row["edited_at"],
        "read_at": row["read_at"],
        "reply_to_id": row["reply_to_id"],
        "reply": _reply_preview(c, row["reply_to_id"]),
        "mine": int(row["sender_id"]) == int(viewer_id),
    }


DM_SELECT = """SELECT pm.id,pm.sender_id,pm.receiver_id,pm.content,pm.created_at,pm.reply_to_id,
                       pm.edited_at,pm.read_at,pm.deleted_by_sender,pm.deleted_by_receiver,
                       su.username AS sender_username,ru.username AS receiver_username
                FROM private_messages pm
                JOIN users su ON su.id=pm.sender_id JOIN users ru ON ru.id=pm.receiver_id"""


def list_conversations(user_id: int):
    with get_db_cursor() as c:
        rows = c.execute(
            """SELECT pm.* FROM private_messages pm
               JOIN (SELECT CASE WHEN sender_id=? THEN receiver_id ELSE sender_id END AS other_id,
                            MAX(id) AS max_id
                     FROM private_messages
                     WHERE (sender_id=? AND deleted_by_sender=0) OR (receiver_id=? AND deleted_by_receiver=0)
                     GROUP BY other_id) latest ON latest.max_id=pm.id
               ORDER BY pm.id DESC LIMIT 200""",
            (user_id, user_id, user_id),
        ).fetchall()
        result = []
        for row in rows:
            other_id = int(row["receiver_id"] if int(row["sender_id"]) == int(user_id) else row["sender_id"])
            u = c.execute(
                "SELECT id,username,class_code,profile_color,status_message,is_admin,is_moderator FROM users WHERE id=?",
                (other_id,),
            ).fetchone()
            if not u:
                continue
            unread = c.execute(
                "SELECT COUNT(*) AS n FROM private_messages WHERE sender_id=? AND receiver_id=? AND read_at IS NULL AND deleted_by_receiver=0",
                (other_id, user_id),
            ).fetchone()["n"]
            result.append({
                "user": _user_public(u),
                "last_message": (row["content"] or "")[:140],
                "last_at": row["created_at"],
                "unread": int(unread or 0),
            })
    return result


def direct_history(user_id: int, other_id: int, before_id: Optional[int] = None, limit: int = 60):
    limit = max(1, min(int(limit), 100))
    params = [user_id, other_id, other_id, user_id]
    before = ""
    if before_id:
        before = " AND pm.id<?"
        params.append(int(before_id))
    params.append(limit)
    with get_db_cursor() as c:
        rows = c.execute(
            DM_SELECT
            + " WHERE ((pm.sender_id=? AND pm.receiver_id=? AND pm.deleted_by_sender=0)"
              " OR (pm.sender_id=? AND pm.receiver_id=? AND pm.deleted_by_receiver=0))"
            + before + " ORDER BY pm.id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        messages = [_serialize(c, row, user_id) for row in reversed(rows)]
        c.execute(
            "UPDATE private_messages SET read_at=COALESCE(read_at,datetime('now')) WHERE sender_id=? AND receiver_id=? AND read_at IS NULL",
            (other_id, user_id),
        )
    return messages


def send_direct_message(sender: dict, receiver_id: int, content: str, reply_to_id: Optional[int] = None):
    if not can_dm(sender, receiver_id):
        raise PermissionError("Tu ne peux pas envoyer de message privé à ce compte.")
    content = (content or "").strip()[:2000]
    if not content:
        raise ValueError("Le message est vide.")
    with get_db_cursor() as c:
        if reply_to_id:
            valid = c.execute(
                "SELECT 1 FROM private_messages WHERE id=? AND ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?))",
                (reply_to_id, sender["id"], receiver_id, receiver_id, sender["id"]),
            ).fetchone()
            if not valid:
                reply_to_id = None
        c.execute(
            "INSERT INTO private_messages(sender_id,receiver_id,content,reply_to_id) VALUES(?,?,?,?)",
            (sender["id"], receiver_id, content, reply_to_id),
        )
        mid = int(c.lastrowid)
        row = c.execute(DM_SELECT + " WHERE pm.id=?", (mid,)).fetchone()
        return _serialize(c, row, sender["id"])


def edit_direct_message(message_id: int, actor_id: int, content: str):
    content = (content or "").strip()[:2000]
    if not content:
        raise ValueError("Le message est vide.")
    with get_db_cursor() as c:
        row = c.execute("SELECT sender_id FROM private_messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            return None
        if int(row["sender_id"]) != int(actor_id):
            raise PermissionError("Tu ne peux modifier que tes messages.")
        c.execute("UPDATE private_messages SET content=?,edited_at=datetime('now') WHERE id=?", (content, message_id))
        result = c.execute(DM_SELECT + " WHERE pm.id=?", (message_id,)).fetchone()
        return _serialize(c, result, actor_id)


def delete_direct_message(message_id: int, actor_id: int):
    with get_db_cursor() as c:
        row = c.execute("SELECT sender_id,receiver_id FROM private_messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            return False
        if int(actor_id) == int(row["sender_id"]):
            c.execute("UPDATE private_messages SET deleted_by_sender=1 WHERE id=?", (message_id,))
        elif int(actor_id) == int(row["receiver_id"]):
            c.execute("UPDATE private_messages SET deleted_by_receiver=1 WHERE id=?", (message_id,))
        else:
            raise PermissionError("Accès refusé.")
        c.execute("DELETE FROM private_messages WHERE id=? AND deleted_by_sender=1 AND deleted_by_receiver=1", (message_id,))
    return True
