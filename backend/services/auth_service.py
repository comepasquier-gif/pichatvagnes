import sqlite3
from typing import Optional

from database import get_db_cursor, IntegrityError
from security import hash_password, verify_password, generate_session_token
from services.class_service import normalize_class_code, InvalidClassCodeError, ensure_class_room
from permissions import get_user_role, get_role_label, normalize_moderator_permissions
from services.moderation_service import clear_expired_restrictions
from services.support_access_service import get_support_session


class UsernameAlreadyTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class BannedUserError(Exception):
    pass


class RegistrationPendingError(Exception):
    pass


def register_user_direct(username: str, password: str, class_code: str) -> dict:
    """Crée immédiatement un compte public puis son serveur de classe."""
    username = username.strip()
    code = normalize_class_code(class_code)
    password_hash = hash_password(password)

    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            raise UsernameAlreadyTakenError(f"Le pseudo '{username}' est déjà utilisé.")

        # Une ancienne demande éventuelle ne doit pas bloquer l'inscription ouverte.
        cursor.execute("DELETE FROM registration_requests WHERE username = ?", (username,))
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash, class_code) VALUES (?, ?, ?)",
                (username, password_hash, code),
            )
        except IntegrityError:
            raise UsernameAlreadyTakenError(f"Le pseudo '{username}' est déjà utilisé.")

    ensure_class_room(code)
    return authenticate_user(username, password)


def submit_registration_request(username: str, password: str, class_code: str) -> int:
    """Enregistre une demande. Aucun compte actif n'est créé ici."""
    username = username.strip()
    code = normalize_class_code(class_code)
    password_hash = hash_password(password)

    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            raise UsernameAlreadyTakenError(f"Le pseudo '{username}' est déjà utilisé.")

        cursor.execute(
            "SELECT id, status FROM registration_requests WHERE username = ?",
            (username,),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if existing["status"] == "pending":
                raise RegistrationPendingError("Une demande est déjà en attente pour ce pseudo.")
            cursor.execute(
                """
                UPDATE registration_requests
                SET password_hash = ?, class_code = ?, status = 'pending',
                    admin_note = '', reviewed_by = NULL, reviewed_at = NULL,
                    created_at = datetime('now')
                WHERE id = ?
                """,
                (password_hash, code, existing["id"]),
            )
            return existing["id"]

        try:
            cursor.execute(
                """
                INSERT INTO registration_requests (username, password_hash, class_code, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (username, password_hash, code),
            )
            return cursor.lastrowid
        except IntegrityError:
            raise UsernameAlreadyTakenError(f"Le pseudo '{username}' est déjà utilisé.")


def authenticate_user(username: str, password: str) -> dict:
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, username, password_hash, avatar_path, status_message,
                   is_admin, is_moderator, moderator_class_code, moderator_permissions, is_bot, class_code, is_banned, banned_reason, grade_title, grade_color, grade_visibility, profile_bio, profile_color, xp, coins, game_wins, game_losses, rpg_class, rpg_level, rpg_xp, rpg_energy, rpg_hp, rpg_attack, rpg_defense, rpg_agility, active_space_id
            FROM users WHERE username = ?
            """,
            (username,),
        )
        user_row = cursor.fetchone()

    if user_row is not None:
        clear_expired_restrictions(user_row["id"])
        with get_db_cursor() as cursor:
            cursor.execute("""SELECT id, username, password_hash, avatar_path, status_message,
                   is_admin, is_moderator, moderator_class_code, moderator_permissions, is_bot, class_code, is_banned, banned_reason, grade_title, grade_color, grade_visibility, profile_bio, profile_color, xp, coins, game_wins, game_losses, rpg_class, rpg_level, rpg_xp, rpg_energy, rpg_hp, rpg_attack, rpg_defense, rpg_agility, active_space_id
                   FROM users WHERE id=?""", (user_row["id"],))
            user_row=cursor.fetchone()

    if user_row is None or bool(user_row["is_bot"]):
        raise InvalidCredentialsError("Pseudo ou mot de passe incorrect.")
    if bool(user_row["is_banned"]):
        raise BannedUserError((user_row["banned_reason"] or "").strip())
    if not verify_password(password, user_row["password_hash"]):
        raise InvalidCredentialsError("Pseudo ou mot de passe incorrect.")

    result = {
        "id": user_row["id"], "username": user_row["username"], "avatar_path": user_row["avatar_path"],
        "status_message": user_row["status_message"], "is_admin": bool(user_row["is_admin"]),
        "is_moderator": bool(user_row["is_moderator"]), "class_code": user_row["class_code"],
        "moderator_class_code": user_row["moderator_class_code"], "moderator_permissions": normalize_moderator_permissions(user_row["moderator_permissions"]), "grade_title": user_row["grade_title"] or "", "grade_color": user_row["grade_color"] or "",
        "grade_visibility": user_row["grade_visibility"] or "full", "profile_bio": user_row["profile_bio"] or "",
        "profile_color": user_row["profile_color"] or "#5865f2", "xp": int(user_row["xp"] or 0), "coins": int(user_row["coins"] or 0),
        "game_wins": int(user_row["game_wins"] or 0), "game_losses": int(user_row["game_losses"] or 0),
        "rpg_class": user_row["rpg_class"] or "aventurier", "rpg_level": int(user_row["rpg_level"] or 1),
        "rpg_xp": int(user_row["rpg_xp"] or 0), "rpg_energy": int(user_row["rpg_energy"] or 0),
        "rpg_hp": int(user_row["rpg_hp"] or 100), "rpg_attack": int(user_row["rpg_attack"] or 12),
        "rpg_defense": int(user_row["rpg_defense"] or 6), "rpg_agility": int(user_row["rpg_agility"] or 8),
        "active_space_id": user_row["active_space_id"],
    }
    result["role"] = get_user_role(result); result["role_label"] = get_role_label(result)
    return result


def create_session(user_id: int, user_agent: str = "", ip_address: str = "") -> str:
    from services.space_service import ensure_default_space_for_user
    ensure_default_space_for_user(user_id)
    token = generate_session_token()
    with get_db_cursor() as cursor:
        cursor.execute(
            "INSERT INTO sessions (token,user_id,last_seen_at,user_agent,ip_address) VALUES (?,?,datetime('now'),?,?)",
            (token, user_id, (user_agent or "")[:300], (ip_address or "")[:80]),
        )
    return token


def get_user_from_session(token: str) -> Optional[dict]:
    with get_db_cursor() as cursor:
        session_row=cursor.execute("SELECT user_id FROM sessions WHERE token=?",(token,)).fetchone()
        if session_row is not None:
            cursor.execute("UPDATE sessions SET last_seen_at=datetime('now') WHERE token=? AND (last_seen_at IS NULL OR last_seen_at < datetime('now','-1 minute'))", (token,))
    if session_row is not None:
        clear_expired_restrictions(session_row["user_id"])
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT users.id, users.username, users.avatar_path,
                   users.status_message, users.is_admin, users.is_moderator,
                   users.moderator_class_code, users.moderator_permissions, users.class_code, users.is_banned, users.grade_title, users.grade_color, users.grade_visibility, users.profile_bio, users.profile_color, users.xp, users.coins, users.game_wins, users.game_losses, users.rpg_class, users.rpg_level, users.rpg_xp, users.rpg_energy, users.rpg_hp, users.rpg_attack, users.rpg_defense, users.rpg_agility, users.active_space_id
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        )
        row = cursor.fetchone()

    if row is None or bool(row["is_banned"]):
        return None
    result = {
        "id": row["id"], "username": row["username"], "avatar_path": row["avatar_path"],
        "status_message": row["status_message"], "is_admin": bool(row["is_admin"]),
        "is_moderator": bool(row["is_moderator"]), "class_code": row["class_code"],
        "moderator_class_code": row["moderator_class_code"], "moderator_permissions": normalize_moderator_permissions(row["moderator_permissions"]), "grade_title": row["grade_title"] or "", "grade_color": row["grade_color"] or "",
        "grade_visibility": row["grade_visibility"] or "full", "profile_bio": row["profile_bio"] or "",
        "profile_color": row["profile_color"] or "#5865f2", "xp": int(row["xp"] or 0), "coins": int(row["coins"] or 0),
        "game_wins": int(row["game_wins"] or 0), "game_losses": int(row["game_losses"] or 0),
        "rpg_class": row["rpg_class"] or "aventurier", "rpg_level": int(row["rpg_level"] or 1),
        "rpg_xp": int(row["rpg_xp"] or 0), "rpg_energy": int(row["rpg_energy"] or 0),
        "rpg_hp": int(row["rpg_hp"] or 100), "rpg_attack": int(row["rpg_attack"] or 12),
        "rpg_defense": int(row["rpg_defense"] or 6), "rpg_agility": int(row["rpg_agility"] or 8),
        "active_space_id": row["active_space_id"],
    }
    result["role"] = get_user_role(result); result["role_label"] = get_role_label(result)
    support = get_support_session(token)
    if support:
        result["support_mode"] = True
        result["support_admin_id"] = int(support["admin_id"])
        result["support_admin_username"] = support["admin_username"]
        result["support_expires_at"] = support["expires_at"]
    else:
        # get_support_session supprime automatiquement une session assistance expirée.
        # On revérifie donc le token avant de traiter le compte comme une session normale.
        with get_db_cursor() as cursor:
            still_valid = cursor.execute("SELECT 1 FROM sessions WHERE token=?", (token,)).fetchone()
        if still_valid is None:
            return None
        result["support_mode"] = False
        result["support_admin_id"] = None
        result["support_admin_username"] = None
        result["support_expires_at"] = None
    return result


def is_user_active(user_id: int) -> bool:
    """Revérifie l'état du compte et lève automatiquement un ban temporaire expiré."""
    clear_expired_restrictions(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("SELECT is_banned FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
    return row is not None and not bool(row["is_banned"])


def delete_session(token: str) -> None:
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))

# ---------------------------------------------------------------------------
# PiChat 3.4 - durable anti brute-force
# ---------------------------------------------------------------------------
def _login_ip_hash(ip_address: str) -> str:
    import hashlib
    from config import PICHAT_SECRET_KEY
    secret = (PICHAT_SECRET_KEY or 'pichat-local').encode('utf-8')
    return hashlib.sha256(secret + b'|' + (ip_address or '').encode('utf-8')).hexdigest()


def check_login_allowed(username: str, ip_address: str) -> None:
    uname = (username or '').strip().lower()[:64]
    ip_hash = _login_ip_hash(ip_address)
    with get_db_cursor() as c:
        row = c.execute(
            """SELECT COUNT(*) AS n FROM login_attempts
               WHERE success=0 AND created_at >= datetime('now','-15 minutes')
                 AND (lower(username)=? OR ip_hash=?)""",
            (uname, ip_hash),
        ).fetchone()
    if int(row['n'] or 0) >= 8:
        raise InvalidCredentialsError('Trop de tentatives. Réessaie dans 15 minutes.')


def record_login_attempt(username: str, ip_address: str, success: bool) -> None:
    uname = (username or '').strip().lower()[:64]
    ip_hash = _login_ip_hash(ip_address)
    with get_db_cursor() as c:
        c.execute("INSERT INTO login_attempts(username,ip_hash,success) VALUES (?,?,?)", (uname, ip_hash, 1 if success else 0))
        # Keep the table bounded without storing raw IP addresses.
        c.execute("DELETE FROM login_attempts WHERE created_at < datetime('now','-1 day')")
