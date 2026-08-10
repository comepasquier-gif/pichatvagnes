from __future__ import annotations
from typing import Optional

import json
from database import get_db_cursor
from permissions import get_user_role, get_role_label


def _safe_json(raw):
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _public_role(user: dict):
    """Rôle affiché publiquement selon le choix du propriétaire du compte."""
    visibility = (user.get("grade_visibility") or "full").lower()
    role = get_user_role(user)
    if visibility == "hidden":
        return role, ""
    if visibility == "subtle":
        if role in {"admin", "moderator"}:
            return role, "STAFF"
        return role, "MEMBRE"
    return role, get_role_label(user)


def _reaction_summary(message_id: int):
    with get_db_cursor() as c:
        c.execute(
            "SELECT emoji, COUNT(*) AS count FROM message_reactions WHERE message_id=? GROUP BY emoji ORDER BY count DESC, emoji LIMIT 12",
            (message_id,),
        )
        return [{"emoji": r["emoji"], "count": int(r["count"])} for r in c.fetchall()]


def _reply_preview(reply_to_id: Optional[int]):
    if not reply_to_id:
        return None
    with get_db_cursor() as c:
        row = c.execute(
            """SELECT m.id,m.content,m.message_type,u.username
               FROM messages m JOIN users u ON u.id=m.user_id WHERE m.id=?""",
            (reply_to_id,),
        ).fetchone()
    if not row:
        return {"id": int(reply_to_id), "username": "Message supprimé", "content": "Message indisponible", "message_type": "text"}
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "content": (row["content"] or "")[:220],
        "message_type": row["message_type"] or "text",
    }


def _message(row, include_reactions=True):
    user = {
        "is_admin": bool(row["is_admin"]),
        "is_moderator": bool(row["is_moderator"]),
        "moderator_class_code": row["moderator_class_code"],
        "class_code": row["class_code"],
        "grade_title": row["grade_title"] or "",
        "grade_color": row["grade_color"] or "",
        "grade_visibility": row["grade_visibility"] or "full",
    }
    role, public_label = _public_role(user)
    result = {
        "id": row["id"],
        "room_id": row["room_id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "content": row["content"],
        "created_at": row["created_at"],
        "edited_at": row["edited_at"] if "edited_at" in row.keys() else None,
        "reply_to_id": row["reply_to_id"] if "reply_to_id" in row.keys() else None,
        "is_pinned": bool(row["is_pinned"]) if "is_pinned" in row.keys() else False,
        "pinned_by": row["pinned_by"] if "pinned_by" in row.keys() else None,
        "pinned_at": row["pinned_at"] if "pinned_at" in row.keys() else None,
        "is_bot": bool(row["is_bot"]),
        "role": role,
        "role_label": public_label,
        "grade_color": row["grade_color"] or "",
        "grade_visibility": row["grade_visibility"] or "full",
        "profile_color": row["profile_color"] or "#5865f2",
        "message_type": row["message_type"] or "text",
        "metadata": _safe_json(row["metadata_json"]),
    }
    result["reply"] = _reply_preview(result["reply_to_id"])
    if include_reactions:
        result["reactions"] = _reaction_summary(row["id"])
    return result


MESSAGE_SELECT = """SELECT m.id,m.room_id,m.user_id,m.content,m.created_at,m.message_type,m.metadata_json,
                  m.reply_to_id,m.edited_at,m.is_pinned,m.pinned_by,m.pinned_at,
                  u.username,u.is_bot,u.is_admin,u.is_moderator,u.moderator_class_code,u.class_code,
                  u.grade_title,u.grade_color,u.grade_visibility,u.profile_color
           FROM messages m JOIN users u ON u.id=m.user_id"""


def _select_message(cursor, message_id):
    cursor.execute(MESSAGE_SELECT + " WHERE m.id=?", (message_id,))
    return cursor.fetchone()


def save_message(
    room_id: int,
    user_id: int,
    content: str,
    message_type: str = "text",
    metadata=None,
    reply_to_id: Optional[int] = None,
) -> dict:
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    with get_db_cursor() as c:
        if reply_to_id:
            valid = c.execute("SELECT 1 FROM messages WHERE id=? AND room_id=?", (reply_to_id, room_id)).fetchone()
            if not valid:
                reply_to_id = None
        c.execute(
            "INSERT INTO messages (room_id,user_id,content,message_type,metadata_json,reply_to_id) VALUES (?,?,?,?,?,?)",
            (room_id, user_id, content, message_type[:24], metadata_json[:12000], reply_to_id),
        )
        mid = c.lastrowid
        row = _select_message(c, mid)
    return _message(row)


def update_message_card(message_id: int, content: Optional[str] = None, metadata=None) -> Optional[dict]:
    with get_db_cursor() as c:
        if content is not None and metadata is not None:
            c.execute(
                "UPDATE messages SET content=?, metadata_json=?, edited_at=datetime('now') WHERE id=?",
                (content, json.dumps(metadata, ensure_ascii=False), message_id),
            )
        elif metadata is not None:
            c.execute("UPDATE messages SET metadata_json=? WHERE id=?", (json.dumps(metadata, ensure_ascii=False), message_id))
        elif content is not None:
            c.execute("UPDATE messages SET content=?, edited_at=datetime('now') WHERE id=?", (content, message_id))
        row = _select_message(c, message_id)
    return _message(row) if row else None


def edit_text_message(message_id: int, user_id: int, content: str, is_admin: bool = False) -> Optional[dict]:
    content = (content or "").strip()[:2000]
    if not content:
        raise ValueError("Le message ne peut pas être vide.")
    with get_db_cursor() as c:
        row = c.execute("SELECT user_id,message_type FROM messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            return None
        if int(row["user_id"]) != int(user_id) and not is_admin:
            raise PermissionError("Tu ne peux modifier que tes propres messages.")
        if (row["message_type"] or "text") != "text":
            raise ValueError("Cette carte ne peut pas être modifiée comme un message texte.")
        c.execute("UPDATE messages SET content=?,edited_at=datetime('now') WHERE id=?", (content, message_id))
        result = _select_message(c, message_id)
    return _message(result) if result else None


def get_room_history(room_id: int, limit: int = 80, before_id: Optional[int] = None) -> list:
    limit = max(1, min(int(limit), 100))
    params = [room_id]
    before_clause = ""
    if before_id is not None:
        before_clause = " AND m.id < ?"
        params.append(int(before_id))
    params.append(limit)
    with get_db_cursor() as c:
        c.execute(
            MESSAGE_SELECT + f" WHERE m.room_id=?{before_clause} ORDER BY m.id DESC LIMIT ?",
            tuple(params),
        )
        rows = c.fetchall()
    return [_message(r) for r in reversed(rows)]


def has_older_room_messages(room_id: int, oldest_id: Optional[int]) -> bool:
    if oldest_id is None:
        return False
    with get_db_cursor() as c:
        row = c.execute("SELECT 1 FROM messages WHERE room_id=? AND id<? LIMIT 1", (room_id, int(oldest_id))).fetchone()
    return row is not None


def search_room_messages(room_id: int, query: str, limit: int = 80, author: str = "") -> list:
    query = (query or "").strip()
    if len(query) < 2:
        return []
    limit = max(1, min(int(limit), 200))
    params: list = [room_id, f"%{query}%"]
    author_clause = ""
    if author.strip():
        author_clause = " AND lower(u.username)=lower(?)"
        params.append(author.strip())
    params.append(limit)
    with get_db_cursor() as c:
        rows = c.execute(
            MESSAGE_SELECT
            + f" WHERE m.room_id=? AND m.content LIKE ? ESCAPE '\\'{author_clause} ORDER BY m.id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [_message(row) for row in rows]


def list_pinned_messages(room_id: int, limit: int = 100) -> list:
    with get_db_cursor() as c:
        rows = c.execute(
            MESSAGE_SELECT + " WHERE m.room_id=? AND m.is_pinned=1 ORDER BY m.pinned_at DESC,m.id DESC LIMIT ?",
            (room_id, max(1, min(limit, 200))),
        ).fetchall()
    return [_message(row) for row in rows]


def toggle_pin(message_id: int, actor_id: int) -> Optional[dict]:
    with get_db_cursor() as c:
        row = c.execute("SELECT is_pinned FROM messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            return None
        next_value = 0 if row["is_pinned"] else 1
        c.execute(
            "UPDATE messages SET is_pinned=?,pinned_by=?,pinned_at=CASE WHEN ?=1 THEN datetime('now') ELSE NULL END WHERE id=?",
            (next_value, actor_id if next_value else None, next_value, message_id),
        )
        result = _select_message(c, message_id)
    return _message(result) if result else None


def get_default_room_id() -> int:
    with get_db_cursor() as c:
        c.execute("SELECT id FROM rooms ORDER BY created_at ASC LIMIT 1")
        row = c.fetchone()
    return row["id"] if row else None


def get_message(message_id: int):
    with get_db_cursor() as c:
        row = _select_message(c, message_id)
    return _message(row) if row else None


def get_message_for_moderation(message_id: int):
    with get_db_cursor() as c:
        c.execute(
            """SELECT m.id,m.room_id,u.id AS user_id,u.username,r.class_code,u.is_admin,u.is_moderator,u.is_bot
               FROM messages m JOIN users u ON u.id=m.user_id JOIN rooms r ON r.id=m.room_id WHERE m.id=?""",
            (message_id,),
        )
        row = c.fetchone()
    return dict(row) if row else None


def delete_message(message_id: int) -> bool:
    with get_db_cursor() as c:
        c.execute("DELETE FROM messages WHERE id=?", (message_id,))
        return c.rowcount > 0


def toggle_reaction(message_id: int, user_id: int, emoji: str):
    emoji = (emoji or "").strip()[:12]
    if not emoji:
        return []
    with get_db_cursor() as c:
        c.execute("SELECT id FROM messages WHERE id=?", (message_id,))
        if not c.fetchone():
            return None
        c.execute("SELECT id FROM message_reactions WHERE message_id=? AND user_id=? AND emoji=?", (message_id, user_id, emoji))
        row = c.fetchone()
        added = False
        if row:
            c.execute("DELETE FROM message_reactions WHERE id=?", (row["id"],))
        else:
            c.execute("INSERT INTO message_reactions (message_id,user_id,emoji) VALUES (?,?,?)", (message_id, user_id, emoji))
            added = True
    if added:
        try:
            from services.rpg_service import progress_quest
            progress_quest(user_id, "reactions", 1)
        except Exception:
            pass
    return _reaction_summary(message_id)


def report_message(message_id: int, reporter_id: int, reason: str):
    reason = (reason or "").strip()[:300]
    with get_db_cursor() as c:
        c.execute("SELECT id FROM messages WHERE id=?", (message_id,))
        if not c.fetchone():
            return False
        c.execute(
            "INSERT OR IGNORE INTO message_reports (message_id,reporter_id,reason) VALUES (?,?,?)",
            (message_id, reporter_id, reason),
        )
    return True
