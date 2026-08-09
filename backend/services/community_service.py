from __future__ import annotations
from database import get_db_cursor
from permissions import get_user_role, get_role_label
from services.room_service import user_can_access_room


def update_profile(user_id, status_message, profile_bio, profile_color, grade_visibility):
    with get_db_cursor() as c:
        c.execute(
            "UPDATE users SET status_message=?,profile_bio=?,profile_color=?,grade_visibility=? WHERE id=?",
            ((status_message or "").strip()[:120], (profile_bio or "").strip()[:280], profile_color, grade_visibility, user_id),
        )
        row = c.execute("SELECT id,username,status_message,profile_bio,profile_color,grade_visibility,xp,coins,game_wins,game_losses,class_code,is_admin,is_moderator,moderator_class_code,grade_title,grade_color FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def public_profile(user_id):
    with get_db_cursor() as c:
        row=c.execute("SELECT id,username,status_message,profile_bio,profile_color,grade_visibility,xp,coins,game_wins,game_losses,class_code,is_admin,is_moderator,moderator_class_code,grade_title,grade_color,is_bot FROM users WHERE id=?",(user_id,)).fetchone()
    if not row: return None
    u=dict(row); role=get_user_role(u); vis=u.get("grade_visibility") or "full"
    if vis=="hidden": label=""
    elif vis=="subtle": label="STAFF" if role in {"admin","moderator"} else "MEMBRE"
    else: label=get_role_label(u)
    xp=int(u.get("xp") or 0)
    result={"id":u["id"],"username":u["username"],"status_message":u.get("status_message") or "","bio":u.get("profile_bio") or "","color":u.get("profile_color") or "#5865f2","class_code":u.get("class_code"),"role":role,"role_label":label,"is_bot":bool(u.get("is_bot")),"xp":xp,"level":1+xp//100,"coins":int(u.get("coins") or 0),"wins":int(u.get("game_wins") or 0),"losses":int(u.get("game_losses") or 0)}
    if not result["is_bot"]:
        try:
            from services.gaming_profile_service import list_games, get_user_badges, sync_automatic_badges
            sync_automatic_badges(user_id)
            result["games"] = list_games(user_id, include_private=False)
            result["badges"] = get_user_badges(user_id)
        except Exception:
            result["games"] = []
            result["badges"] = []
    else:
        result["games"] = []
        result["badges"] = []
    return result


def room_members(room_id, viewer, online_ids=None, special_presences=None):
    if not user_can_access_room(viewer, room_id): return []
    with get_db_cursor() as c:
        room=c.execute("SELECT class_code,room_kind FROM rooms WHERE id=?",(room_id,)).fetchone()
        if not room: return []
        if (room["room_kind"] or "standard") == "custom":
            rows=c.execute("""SELECT DISTINCT u.id FROM users u
                LEFT JOIN custom_server_members m ON m.user_id=u.id AND m.server_id=?
                WHERE u.is_banned=0 AND u.is_bot=0 AND (u.is_admin=1 OR m.user_id IS NOT NULL)
                ORDER BY u.is_admin DESC,u.is_moderator DESC,u.username COLLATE NOCASE""",(room_id,)).fetchall()
        elif room["class_code"]:
            rows=c.execute("""SELECT id FROM users WHERE is_banned=0 AND is_bot=0
                AND (is_admin=1 OR class_code=? OR moderator_class_code=?)
                ORDER BY is_admin DESC,is_moderator DESC,username COLLATE NOCASE""",(room["class_code"],room["class_code"])).fetchall()
        else:
            rows=c.execute("SELECT id FROM users WHERE is_banned=0 AND is_bot=0 ORDER BY is_admin DESC,is_moderator DESC,username COLLATE NOCASE").fetchall()
    online_ids=online_ids or set()
    special_presences=special_presences or {}
    result=[]
    for r in rows:
        p=public_profile(r["id"])
        if p:
            p["online"]=r["id"] in online_ids or r["id"] in special_presences
            if r["id"] in special_presences:
                p["presence_status"]=special_presences[r["id"]].get("status")
                p["presence_kind"]=special_presences[r["id"]].get("kind")
            result.append(p)
    return result


def get_feature_settings():
    keys = (
        "games_enabled", "tutor_enabled", "reactions_enabled", "reports_enabled", "member_panel",
        "pycoins_enabled", "custom_servers_enabled", "code_lab_enabled", "support_access_enabled",
        "direct_messages_enabled", "message_edit_enabled", "pins_enabled", "search_enabled",
        "tutor_plus_enabled", "rpg_enabled", "gaming_profiles_enabled", "internet_mode_enabled", "arcade_enabled", "game_studio_enabled",
    )
    with get_db_cursor() as c:
        row=c.execute("SELECT " + ",".join(keys) + " FROM feature_settings WHERE id=1").fetchone()
    return {k:bool(row[k]) for k in keys} if row else {k:True for k in keys}


def set_feature_settings(values):
    keys = (
        "games_enabled", "tutor_enabled", "reactions_enabled", "reports_enabled", "member_panel",
        "pycoins_enabled", "custom_servers_enabled", "code_lab_enabled", "support_access_enabled",
        "direct_messages_enabled", "message_edit_enabled", "pins_enabled", "search_enabled",
        "tutor_plus_enabled", "rpg_enabled", "gaming_profiles_enabled", "internet_mode_enabled", "arcade_enabled", "game_studio_enabled",
    )
    with get_db_cursor() as c:
        c.execute(
            "UPDATE feature_settings SET " + ",".join(k + "=?" for k in keys) + ",updated_at=datetime('now') WHERE id=1",
            tuple(1 if values.get(k, True) else 0 for k in keys),
        )
    return get_feature_settings()
