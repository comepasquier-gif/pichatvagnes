from __future__ import annotations
from typing import Optional

import sqlite3

from database import get_db_cursor, IntegrityError
from services.class_service import normalize_class_code


class RoomAlreadyExistsError(Exception):
    pass


class RoomNotFoundError(Exception):
    pass


ROOM_COLUMNS = "id,name,class_code,created_at,slow_mode_seconds,room_kind,owner_user_id,description,icon,invite_code"


def _row_to_room(row, viewer_id=None):
    keys = row.keys()
    owner_id = row["owner_user_id"] if "owner_user_id" in keys else None
    is_owner = viewer_id is not None and owner_id is not None and int(owner_id) == int(viewer_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "class_code": row["class_code"],
        "created_at": row["created_at"],
        "slow_mode_seconds": int(row["slow_mode_seconds"] or 0) if "slow_mode_seconds" in keys else 0,
        "room_kind": (row["room_kind"] if "room_kind" in keys else "standard") or "standard",
        "owner_user_id": owner_id,
        "description": (row["description"] if "description" in keys else "") or "",
        "icon": (row["icon"] if "icon" in keys else "💬") or "💬",
        "invite_code": ((row["invite_code"] if "invite_code" in keys else None) if is_owner else None),
        "is_owner": is_owner,
        "space_id": row["space_id"] if "space_id" in keys else None,
        "space_name": row["space_name"] if "space_name" in keys else None,
        "space_icon": row["space_icon"] if "space_icon" in keys else None,
        "category": row["category"] if "category" in keys else None,
        "position": int(row["position"] or 0) if "position" in keys else 0,
    }


def _standard_rooms(cursor, user: dict):
    if user.get("is_admin"):
        return cursor.execute(
            f"SELECT {ROOM_COLUMNS} FROM rooms WHERE COALESCE(room_kind,'standard')!='custom' ORDER BY class_code IS NOT NULL,class_code,created_at"
        ).fetchall()
    if user.get("is_moderator") and user.get("moderator_class_code"):
        return cursor.execute(
            f"""SELECT {ROOM_COLUMNS} FROM rooms
                WHERE COALESCE(room_kind,'standard')!='custom'
                  AND (class_code IS NULL OR class_code=?)
                ORDER BY class_code IS NULL DESC,created_at""",
            (user["moderator_class_code"],),
        ).fetchall()
    if user.get("class_code"):
        return cursor.execute(
            f"""SELECT {ROOM_COLUMNS} FROM rooms
                WHERE COALESCE(room_kind,'standard')!='custom'
                  AND (class_code IS NULL OR class_code=?)
                ORDER BY class_code IS NULL DESC,created_at""",
            (user["class_code"],),
        ).fetchall()
    return cursor.execute(
        f"SELECT {ROOM_COLUMNS} FROM rooms WHERE COALESCE(room_kind,'standard')!='custom' AND class_code IS NULL ORDER BY created_at"
    ).fetchall()


def list_rooms(user: dict) -> list:
    """PiChat 2.0 : salons de l'espace actif + serveurs personnels."""
    from services.space_service import get_active_space_id
    active_space = get_active_space_id(user["id"])
    with get_db_cursor() as cursor:
        rows = cursor.execute(
            f"""SELECT {','.join('r.'+c for c in ROOM_COLUMNS.split(','))},
                       sr.space_id,s.name AS space_name,s.icon AS space_icon,sr.category,sr.position
                FROM space_rooms sr JOIN rooms r ON r.id=sr.room_id JOIN spaces s ON s.id=sr.space_id
                WHERE sr.space_id=? ORDER BY sr.category,sr.position,r.id""",
            (active_space,),
        ).fetchall()
        # La sécurité de classe reste appliquée dans un établissement.
        standard=[]
        for row in rows:
            room_class=row["class_code"]
            if user.get("is_admin") or room_class is None or room_class==user.get("class_code") or (user.get("is_moderator") and room_class==user.get("moderator_class_code")):
                standard.append(row)
        if user.get("is_admin"):
            custom = cursor.execute(f"SELECT {ROOM_COLUMNS} FROM rooms WHERE room_kind='custom' ORDER BY created_at DESC").fetchall()
        else:
            custom = cursor.execute(
                f"""SELECT {','.join('r.' + col for col in ROOM_COLUMNS.split(','))}
                    FROM rooms r JOIN custom_server_members m ON m.server_id=r.id
                    WHERE r.room_kind='custom' AND m.user_id=? ORDER BY r.created_at DESC""",
                (user["id"],),
            ).fetchall()
    return [_row_to_room(row,user.get("id")) for row in standard] + [_row_to_room(row,user.get("id")) for row in custom]


def create_room(name: str, class_code: Optional[str] = None) -> dict:
    code = normalize_class_code(class_code, required=False)
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO rooms (name,class_code,room_kind) VALUES (?,?,'standard')",
                (name.strip(), code),
            )
            room_id = cursor.lastrowid
            central = cursor.execute("SELECT id FROM spaces WHERE slug='pichat-central'").fetchone()
            if central is not None:
                cursor.execute("INSERT OR IGNORE INTO space_rooms(space_id,room_id,category,position) VALUES(?,?,'SALONS',?)", (central["id"], room_id, room_id))
            row = cursor.execute(f"SELECT {ROOM_COLUMNS} FROM rooms WHERE id=?", (room_id,)).fetchone()
    except IntegrityError:
        raise RoomAlreadyExistsError(f"Un salon nommé '{name}' existe déjà.")
    return _row_to_room(row)


def delete_room(room_id: int) -> None:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT id FROM rooms WHERE id=?", (room_id,)).fetchone()
        if row is None:
            raise RoomNotFoundError()
        cursor.execute("DELETE FROM rooms WHERE id=?", (room_id,))


def room_exists(room_id: int) -> bool:
    with get_db_cursor() as cursor:
        return cursor.execute("SELECT id FROM rooms WHERE id=?", (room_id,)).fetchone() is not None


def user_can_access_room(user: dict, room_id: int) -> bool:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            """SELECT r.class_code,r.room_kind,sr.space_id
                 FROM rooms r LEFT JOIN space_rooms sr ON sr.room_id=r.id WHERE r.id=?""",
            (room_id,),
        ).fetchone()
        if row is None:
            return False
        if user.get("is_admin"):
            return True
        if row["space_id"] is not None:
            membership = cursor.execute("SELECT 1 FROM space_members WHERE space_id=? AND user_id=?", (row["space_id"], user["id"])).fetchone()
            if membership is None:
                return False
        if (row["room_kind"] or "standard") == "custom":
            membership = cursor.execute(
                "SELECT 1 FROM custom_server_members WHERE server_id=? AND user_id=?",
                (room_id, user["id"]),
            ).fetchone()
            return membership is not None
    room_class = row["class_code"]
    if user.get("is_moderator"):
        if room_class is None:
            return True
        return bool(user.get("moderator_class_code")) and user.get("moderator_class_code") == room_class
    if room_class is None:
        return True
    return bool(user.get("class_code")) and room_class == user.get("class_code")


def get_default_room_id_for_user(user: dict) -> Optional[int]:
    """Préfère le salon de classe puis le général de l'espace actif."""
    from services.space_service import get_active_space_id
    active_space = get_active_space_id(user["id"])
    with get_db_cursor() as cursor:
        preferred_class = user.get("moderator_class_code") if user.get("is_moderator") else user.get("class_code")
        if preferred_class:
            row = cursor.execute(
                """SELECT r.id FROM space_rooms sr JOIN rooms r ON r.id=sr.room_id
                   WHERE sr.space_id=? AND r.class_code=? ORDER BY sr.position,r.id LIMIT 1""",
                (active_space, preferred_class),
            ).fetchone()
            if row:
                return row["id"]
        row = cursor.execute(
            """SELECT r.id FROM space_rooms sr JOIN rooms r ON r.id=sr.room_id
               WHERE sr.space_id=? AND r.class_code IS NULL ORDER BY sr.position,r.id LIMIT 1""",
            (active_space,),
        ).fetchone()
    return row["id"] if row else None


def list_room_recipient_user_ids(room_id: int) -> list[int]:
    with get_db_cursor() as cursor:
        room = cursor.execute(
            """SELECT r.class_code,r.room_kind,sr.space_id
               FROM rooms r LEFT JOIN space_rooms sr ON sr.room_id=r.id WHERE r.id=?""",
            (room_id,),
        ).fetchone()
        if room is None:
            return []
        if (room["room_kind"] or "standard") == "custom":
            rows = cursor.execute(
                """SELECT DISTINCT u.id FROM users u
                   LEFT JOIN custom_server_members m ON m.user_id=u.id AND m.server_id=?
                   WHERE COALESCE(u.is_banned,0)=0 AND COALESCE(u.is_bot,0)=0
                     AND (COALESCE(u.is_admin,0)=1 OR m.user_id IS NOT NULL)""",
                (room_id,),
            ).fetchall()
        elif room["space_id"] is not None:
            if room["class_code"] is None:
                rows = cursor.execute(
                    """SELECT DISTINCT u.id FROM users u JOIN space_members sm ON sm.user_id=u.id
                       WHERE sm.space_id=? AND COALESCE(u.is_banned,0)=0 AND COALESCE(u.is_bot,0)=0""",
                    (room["space_id"],),
                ).fetchall()
            else:
                rows = cursor.execute(
                    """SELECT DISTINCT u.id FROM users u JOIN space_members sm ON sm.user_id=u.id
                       WHERE sm.space_id=? AND COALESCE(u.is_banned,0)=0 AND COALESCE(u.is_bot,0)=0
                         AND (COALESCE(u.is_admin,0)=1 OR u.class_code=? OR
                              (COALESCE(u.is_moderator,0)=1 AND u.moderator_class_code=?))""",
                    (room["space_id"], room["class_code"], room["class_code"]),
                ).fetchall()
        elif room["class_code"] is None:
            rows = cursor.execute("SELECT id FROM users WHERE COALESCE(is_banned,0)=0 AND COALESCE(is_bot,0)=0").fetchall()
        else:
            rows = cursor.execute(
                """SELECT id FROM users WHERE COALESCE(is_banned,0)=0 AND COALESCE(is_bot,0)=0
                   AND (COALESCE(is_admin,0)=1 OR class_code=? OR
                        (COALESCE(is_moderator,0)=1 AND moderator_class_code=?))""",
                (room["class_code"], room["class_code"]),
            ).fetchall()
    return [int(row["id"]) for row in rows]

