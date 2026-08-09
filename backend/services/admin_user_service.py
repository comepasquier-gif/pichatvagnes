from database import get_db_cursor
from security import hash_password
import re
import secrets
import string
from services.class_service import normalize_class_code, ensure_class_room
from permissions import (
    get_user_role, get_role_label, normalize_moderator_permissions,
    serialize_moderator_permissions, identify_moderator_pack,
    moderator_permissions_for_pack,
)

class UserNotFoundError(Exception): pass
class ProtectedUserError(Exception): pass
class RegistrationRequestNotFoundError(Exception): pass
class RegistrationRequestStateError(Exception): pass
class UsernameConflictError(Exception): pass


def _admin_user(row):
    result = {
        "id": row["id"], "username": row["username"], "class_code": row["class_code"],
        "is_admin": bool(row["is_admin"]), "is_moderator": bool(row["is_moderator"]),
        "moderator_class_code": row["moderator_class_code"], "moderator_permissions": normalize_moderator_permissions(row["moderator_permissions"]), "is_bot": bool(row["is_bot"]),
        "is_banned": bool(row["is_banned"]), "banned_at": row["banned_at"],
        "banned_reason": row["banned_reason"] or "", "created_at": row["created_at"],
        "grade_title": row["grade_title"] or "", "grade_color": row["grade_color"] or "",
    }
    result["role"] = get_user_role(result); result["role_label"] = get_role_label(result)
    result["moderator_pack"] = identify_moderator_pack(result["moderator_permissions"]) if result["is_moderator"] else "custom"
    return result


def list_users_for_admin():
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, username, class_code, is_admin, is_moderator, moderator_class_code, moderator_permissions,
                   is_bot, is_banned, banned_at, banned_reason, created_at, grade_title, grade_color
            FROM users ORDER BY class_code IS NULL, class_code, lower(username)
        """)
        rows = cursor.fetchall()
    return [_admin_user(r) for r in rows]


def list_users_for_moderator(class_code):
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, username, class_code, is_admin, is_moderator, moderator_class_code, moderator_permissions,
                   is_bot, is_banned, banned_at, banned_reason, created_at, grade_title, grade_color
            FROM users WHERE class_code = ? AND is_bot = 0
            ORDER BY lower(username)
        """, (class_code,))
        rows = cursor.fetchall()
    return [_admin_user(r) for r in rows]


def get_user_for_admin(user_id):
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, username, class_code, is_admin, is_moderator, moderator_class_code, moderator_permissions,
                   is_bot, is_banned, banned_at, banned_reason, created_at, grade_title, grade_color FROM users WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()
    if row is None: raise UserNotFoundError()
    return _admin_user(row)


def ban_user(user_id, acting_user_id, reason="", allowed_class=None):
    reason = reason.strip()[:300]
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, class_code, is_admin, is_moderator, is_bot FROM users WHERE id = ?", (user_id,))
        target = cursor.fetchone()
        if target is None: raise UserNotFoundError()
        if target["id"] == acting_user_id: raise ProtectedUserError("Tu ne peux pas bannir ton propre compte.")
        if bool(target["is_admin"]): raise ProtectedUserError("Un administrateur est protégé.")
        if bool(target["is_bot"]): raise ProtectedUserError("Un bot se gère dans la section Bots.")
        if allowed_class and bool(target["is_moderator"]): raise ProtectedUserError("Un modérateur de classe est protégé. Demande à un admin.")
        if allowed_class and target["class_code"] != allowed_class:
            raise ProtectedUserError("Un modérateur ne peut agir que sur sa propre classe.")
        cursor.execute("UPDATE users SET is_banned=1, banned_at=datetime('now'), banned_reason=?, ban_until=NULL WHERE id=?", (reason, user_id))
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return get_user_for_admin(user_id)


def unban_user(user_id, allowed_class=None):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, class_code, is_bot FROM users WHERE id=?", (user_id,))
        target = cursor.fetchone()
        if target is None: raise UserNotFoundError()
        if bool(target["is_bot"]): raise ProtectedUserError("Ce compte est un bot.")
        if allowed_class and target["class_code"] != allowed_class:
            raise ProtectedUserError("Un modérateur ne peut agir que sur sa propre classe.")
        cursor.execute("UPDATE users SET is_banned=0, banned_at=NULL, banned_reason='', ban_until=NULL WHERE id=?", (user_id,))
    return get_user_for_admin(user_id)


def update_user_class(user_id, class_code):
    code = normalize_class_code(class_code)
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, is_bot FROM users WHERE id=?", (user_id,))
        target = cursor.fetchone()
        if target is None: raise UserNotFoundError()
        if bool(target["is_bot"]): raise ProtectedUserError("Un bot n'a pas de classe.")
        cursor.execute("UPDATE users SET class_code=? WHERE id=?", (code, user_id))
        cursor.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    ensure_class_room(code)
    return get_user_for_admin(user_id)


def set_moderator(user_id, enabled, class_code=None, permissions=None, moderator_pack=None):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, is_admin, is_bot, class_code FROM users WHERE id=?", (user_id,))
        target = cursor.fetchone()
        if target is None: raise UserNotFoundError()
        if bool(target["is_admin"]) or bool(target["is_bot"]):
            raise ProtectedUserError("Ce compte ne peut pas devenir modérateur de classe.")
        code = normalize_class_code(class_code or target["class_code"]) if enabled else None
        if enabled and moderator_pack:
            try:
                permissions = moderator_permissions_for_pack(moderator_pack)
            except ValueError as exc:
                raise ProtectedUserError(str(exc))
        perms = serialize_moderator_permissions(permissions) if enabled else ""
        cursor.execute("UPDATE users SET is_moderator=?, moderator_class_code=?, moderator_permissions=? WHERE id=?", (1 if enabled else 0, code, perms, user_id))
        cursor.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    if enabled: ensure_class_room(code)
    return get_user_for_admin(user_id)



def update_moderator_permissions(user_id, permissions):
    with get_db_cursor() as cursor:
        row=cursor.execute("SELECT id,is_moderator,is_admin,is_bot FROM users WHERE id=?",(user_id,)).fetchone()
        if row is None: raise UserNotFoundError()
        if not bool(row["is_moderator"]) or bool(row["is_admin"]) or bool(row["is_bot"]):
            raise ProtectedUserError("Ce compte n'est pas un modérateur configurable.")
        cursor.execute("UPDATE users SET moderator_permissions=? WHERE id=?",(serialize_moderator_permissions(permissions),user_id))
        cursor.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
    return get_user_for_admin(user_id)


def apply_moderator_pack(user_id, pack, class_code=None):
    try:
        permissions = moderator_permissions_for_pack(pack)
    except ValueError as exc:
        raise ProtectedUserError(str(exc))
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT id,is_moderator,is_admin,is_bot,class_code,moderator_class_code FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise UserNotFoundError()
        if bool(row["is_admin"]) or bool(row["is_bot"]):
            raise ProtectedUserError("Ce compte ne peut pas recevoir un pack modo.")
        code = normalize_class_code(class_code or row["moderator_class_code"] or row["class_code"])
        cursor.execute(
            "UPDATE users SET is_admin=0,is_moderator=1,moderator_class_code=?,class_code=?,moderator_permissions=? WHERE id=?",
            (code, code, serialize_moderator_permissions(permissions), user_id),
        )
        cursor.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    ensure_class_room(code)
    return get_user_for_admin(user_id)

def list_registration_requests(status="pending"):
    allowed = {"pending", "approved", "rejected", "all"}
    if status not in allowed: status = "pending"
    with get_db_cursor() as cursor:
        sql = "SELECT id, username, class_code, status, created_at, reviewed_at FROM registration_requests"
        params = ()
        if status != "all": sql += " WHERE status = ?"; params = (status,)
        sql += " ORDER BY created_at DESC"
        cursor.execute(sql, params); rows = cursor.fetchall()
    return [dict(row) for row in rows]


def approve_registration_request(request_id, admin_id):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM registration_requests WHERE id=?", (request_id,)); req = cursor.fetchone()
        if req is None: raise RegistrationRequestNotFoundError()
        if req["status"] != "pending" or not req["password_hash"]: raise RegistrationRequestStateError()
        cursor.execute("SELECT id FROM users WHERE username=?", (req["username"],))
        if cursor.fetchone() is not None: raise UsernameConflictError()
        cursor.execute("INSERT INTO users (username, password_hash, class_code) VALUES (?, ?, ?)", (req["username"], req["password_hash"], req["class_code"]))
        user_id = cursor.lastrowid
        cursor.execute("""UPDATE registration_requests SET status='approved', password_hash=NULL,
                   reviewed_by=?, reviewed_at=datetime('now') WHERE id=?""", (admin_id, request_id))
    ensure_class_room(req["class_code"])
    return get_user_for_admin(user_id)


def reject_registration_request(request_id, admin_id, note=""):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT status FROM registration_requests WHERE id=?", (request_id,)); req = cursor.fetchone()
        if req is None: raise RegistrationRequestNotFoundError()
        if req["status"] != "pending": raise RegistrationRequestStateError()
        cursor.execute("""UPDATE registration_requests SET status='rejected', password_hash=NULL,
                   admin_note=?, reviewed_by=?, reviewed_at=datetime('now') WHERE id=?""", (note.strip()[:300], admin_id, request_id))


def set_user_role(user_id, role, class_code=None, acting_user_id=None, permissions=None, moderator_pack=None):
    role=(role or "").strip().lower()
    if role not in {"player","moderator","admin"}:
        raise ProtectedUserError("Grade invalide : utilise player, moderator ou admin.")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id,is_admin,is_bot,class_code FROM users WHERE id=?",(user_id,))
        target=cursor.fetchone()
        if target is None: raise UserNotFoundError()
        if bool(target["is_bot"]): raise ProtectedUserError("Un bot ne peut pas recevoir ce grade.")
        if acting_user_id is not None and target["id"]==acting_user_id and role!="admin":
            raise ProtectedUserError("Tu ne peux pas retirer ton propre grade administrateur.")
        if role=="admin":
            cursor.execute("UPDATE users SET is_admin=1,is_moderator=0,moderator_class_code=NULL,moderator_permissions='' WHERE id=?",(user_id,))
        elif role=="moderator":
            code=normalize_class_code(class_code or target["class_code"])
            if moderator_pack:
                try:
                    permissions=moderator_permissions_for_pack(moderator_pack)
                except ValueError as exc:
                    raise ProtectedUserError(str(exc))
            perms=serialize_moderator_permissions(permissions)
            cursor.execute("UPDATE users SET is_admin=0,is_moderator=1,moderator_class_code=?,moderator_permissions=?,class_code=? WHERE id=?",(code,perms,code,user_id))
        else:
            cursor.execute("UPDATE users SET is_admin=0,is_moderator=0,moderator_class_code=NULL,moderator_permissions='' WHERE id=?",(user_id,))
        cursor.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
    if role=="moderator": ensure_class_room(code)
    return get_user_for_admin(user_id)


def log_admin_action(actor_id, action, target="", details=""):
    with get_db_cursor() as cursor:
        cursor.execute("INSERT INTO admin_audit_logs (actor_id,action,target,details) VALUES (?,?,?,?)",
                       (actor_id, str(action)[:80], str(target)[:120], str(details)[:500]))


def list_audit_logs(limit=100):
    limit=max(1,min(int(limit),500))
    with get_db_cursor() as cursor:
        rows=cursor.execute("""SELECT l.id,l.action,l.target,l.details,l.created_at,u.username AS actor
            FROM admin_audit_logs l LEFT JOIN users u ON u.id=l.actor_id
            ORDER BY l.id DESC LIMIT ?""",(limit,)).fetchall()
    return [dict(r) for r in rows]


def kick_user(user_id, acting_user_id=None):
    with get_db_cursor() as cursor:
        row=cursor.execute("SELECT id,username,is_bot FROM users WHERE id=?",(user_id,)).fetchone()
        if row is None: raise UserNotFoundError()
        if acting_user_id is not None and row["id"]==acting_user_id: raise ProtectedUserError("Tu ne peux pas t'expulser toi-même.")
        if bool(row["is_bot"]): raise ProtectedUserError("Un bot ne possède pas de session utilisateur.")
        cursor.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
        count=cursor.rowcount
    return {"username":row["username"],"sessions_removed":count}


def reset_user_password(user_id, acting_user_id=None):
    alphabet="ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
    temporary=''.join(secrets.choice(alphabet) for _ in range(14))
    with get_db_cursor() as cursor:
        row=cursor.execute("SELECT id,username,is_bot FROM users WHERE id=?",(user_id,)).fetchone()
        if row is None: raise UserNotFoundError()
        if acting_user_id is not None and row["id"]==acting_user_id: raise ProtectedUserError("Utilise ton profil pour changer ton propre mot de passe.")
        if bool(row["is_bot"]): raise ProtectedUserError("Un bot n'a pas de mot de passe de connexion.")
        cursor.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(temporary),user_id))
        cursor.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
    return {"username":row["username"],"temporary_password":temporary}


def delete_user_account(user_id, acting_user_id=None):
    with get_db_cursor() as cursor:
        row=cursor.execute("SELECT id,username,is_admin,is_bot FROM users WHERE id=?",(user_id,)).fetchone()
        if row is None: raise UserNotFoundError()
        if acting_user_id is not None and row["id"]==acting_user_id: raise ProtectedUserError("Tu ne peux pas supprimer ton propre compte.")
        if bool(row["is_admin"]): raise ProtectedUserError("Un administrateur est protégé. Retire d'abord son grade admin.")
        if bool(row["is_bot"]): raise ProtectedUserError("Supprime ce compte depuis la section Bots.")
        cursor.execute("DELETE FROM users WHERE id=?",(user_id,))
    return row["username"]


def update_user_badge(user_id, title="", color=""):
    title=(title or "").strip()[:24]
    color=(color or "").strip()
    if color and not re.match(r"^#[0-9A-Fa-f]{6}$", color):
        raise ProtectedUserError("La couleur doit être au format #RRGGBB, par exemple #7c5cff.")
    with get_db_cursor() as cursor:
        row=cursor.execute("SELECT id,is_bot FROM users WHERE id=?",(user_id,)).fetchone()
        if row is None: raise UserNotFoundError()
        if bool(row["is_bot"]): raise ProtectedUserError("Les bots ont leur propre badge.")
        cursor.execute("UPDATE users SET grade_title=?, grade_color=? WHERE id=?",(title,color,user_id))
    return get_user_for_admin(user_id)


def get_profanity_settings():
    with get_db_cursor() as cursor:
        row=cursor.execute("SELECT profanity_enabled,profanity_words FROM moderation_settings WHERE id=1").fetchone()
    words=[w.strip() for w in (row["profanity_words"] or "").split(',') if w.strip()]
    return {"enabled":bool(row["profanity_enabled"]),"words":words,"words_text":','.join(words)}


def set_profanity_settings(enabled, words_text):
    words=[]
    seen=set()
    for raw in (words_text or "").replace(';',',').split(','):
        w=raw.strip()
        key=w.casefold()
        if w and key not in seen:
            seen.add(key); words.append(w[:40])
    with get_db_cursor() as cursor:
        cursor.execute("UPDATE moderation_settings SET profanity_enabled=?,profanity_words=?,updated_at=datetime('now') WHERE id=1",
                       (1 if enabled else 0, ','.join(words)))
    return get_profanity_settings()
