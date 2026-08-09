from __future__ import annotations
from typing import Optional

"""AutoModo : modération automatique, explicable et réversible.

Le bot ne prononce jamais de ban définitif. Il peut :
- flouter / bloquer un message selon les règles configurées ;
- envoyer un avertissement ;
- appliquer un mute temporaire ;
- appliquer un ban temporaire en cas de récidives nombreuses ;
- consigner chaque décision pour révision par un humain.
"""

from datetime import datetime, timedelta, timezone
import re
import secrets
import unicodedata

from database import get_db_cursor
from security import hash_password
from services.message_service import save_message


DEFAULT_SETTINGS = {
    "enabled": True,
    "announce_actions": True,
    "exempt_staff": True,
    "profanity_mode": "blur",  # allow | blur | block
    "link_mode": "warn",       # allow | warn | block
    "max_links": 2,
    "max_mentions": 5,
    "warn_points": 1,
    "mute_points": 4,
    "mute_minutes": 10,
    "temp_ban_points": 8,
    "temp_ban_minutes": 60,
    "point_window_minutes": 1440,
}


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sql_dt(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def get_automod_settings() -> dict:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT * FROM automod_settings WHERE id=1").fetchone()
    if row is None:
        return dict(DEFAULT_SETTINGS)
    result = dict(row)
    for key in ("enabled", "announce_actions", "exempt_staff"):
        result[key] = bool(result.get(key))
    return result


def set_automod_settings(values: dict) -> dict:
    data = dict(DEFAULT_SETTINGS)
    data.update(values or {})
    if data["profanity_mode"] not in {"allow", "blur", "block"}:
        raise ValueError("Mode gros mots invalide.")
    if data["link_mode"] not in {"allow", "warn", "block"}:
        raise ValueError("Mode liens invalide.")
    with get_db_cursor() as cursor:
        cursor.execute(
            """UPDATE automod_settings SET enabled=?,announce_actions=?,exempt_staff=?,
               profanity_mode=?,link_mode=?,max_links=?,max_mentions=?,warn_points=?,
               mute_points=?,mute_minutes=?,temp_ban_points=?,temp_ban_minutes=?,
               point_window_minutes=?,updated_at=datetime('now') WHERE id=1""",
            (
                int(bool(data["enabled"])), int(bool(data["announce_actions"])),
                int(bool(data["exempt_staff"])), data["profanity_mode"], data["link_mode"],
                int(data["max_links"]), int(data["max_mentions"]), int(data["warn_points"]),
                int(data["mute_points"]), int(data["mute_minutes"]),
                int(data["temp_ban_points"]), int(data["temp_ban_minutes"]),
                int(data["point_window_minutes"]),
            ),
        )
    return get_automod_settings()


def _normalize(text: str) -> tuple[str, str]:
    raw = unicodedata.normalize("NFKD", text or "")
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch)).lower()
    raw = raw.translate(str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"}))
    spaced = re.sub(r"\s+", " ", raw)
    compact = re.sub(r"[^a-z0-9]", "", raw)
    return spaced, compact


def _profanity_hits(content: str) -> list[str]:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT profanity_enabled,profanity_words FROM moderation_settings WHERE id=1").fetchone()
    if not row or not bool(row["profanity_enabled"]):
        return []
    words = [w.strip().lower() for w in (row["profanity_words"] or "").split(",") if w.strip()]
    spaced, compact = _normalize(content)
    hits = []
    for word in words:
        normalized, compact_word = _normalize(word)
        if not normalized:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])", spaced):
            hits.append(word)
        elif len(compact_word) >= 4 and compact_word in compact:
            hits.append(word)
    return sorted(set(hits))


def ensure_automod_bot() -> dict:
    """Crée le compte système AutoModo s'il n'existe pas encore."""
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT id,username FROM users WHERE username='AutoModo' AND is_bot=1"
        ).fetchone()
        if row:
            return dict(row)

        # En cas de conflit avec un vrai utilisateur, utilise un nom de secours.
        existing = cursor.execute("SELECT id FROM users WHERE username='AutoModo'").fetchone()
        name = "AutoModoBot" if existing else "AutoModo"
        row = cursor.execute("SELECT id,username FROM users WHERE username=? AND is_bot=1", (name,)).fetchone()
        if row:
            return dict(row)
        disabled_hash = hash_password(secrets.token_urlsafe(32))
        cursor.execute(
            """INSERT INTO users(username,password_hash,is_bot,status_message,grade_title,grade_color)
               VALUES(?,?,1,'Modération automatique','AUTOMODO','#ed4245')""",
            (name, disabled_hash),
        )
        return {"id": cursor.lastrowid, "username": name}


def _current_points(user_id: int, window_minutes: int) -> int:
    threshold = _sql_dt(_utc_now() - timedelta(minutes=max(1, int(window_minutes))))
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT COALESCE(SUM(points),0) AS total FROM automod_incidents WHERE user_id=? AND status!='ignored' AND created_at>=?",
            (user_id, threshold),
        ).fetchone()
    return int(row["total"] or 0)


def _record_incident(user_id: int, room_id: int, rule: str, points: int,
                     action: str, content: str, detail: str = "", message_id=None) -> int:
    with get_db_cursor() as cursor:
        cursor.execute(
            """INSERT INTO automod_incidents
               (user_id,room_id,message_id,rule,points,action,content_preview,detail)
               VALUES(?,?,?,?,?,?,?,?)""",
            (user_id, room_id, message_id, rule[:40], int(points), action[:40],
             (content or "")[:300], (detail or "")[:500]),
        )
        return cursor.lastrowid


def _apply_escalation(user: dict, settings: dict, points_after: int, reason: str) -> str:
    """Retourne warning, mute, temporary_ban ou none."""
    if user.get("is_admin") or user.get("is_moderator") or user.get("is_bot"):
        return "none"
    now = _utc_now()
    if points_after >= int(settings["temp_ban_points"]):
        expires = _sql_dt(now + timedelta(minutes=int(settings["temp_ban_minutes"])))
        with get_db_cursor() as cursor:
            cursor.execute(
                """UPDATE users SET is_banned=1,banned_at=datetime('now'),banned_reason=?,ban_until=?
                   WHERE id=?""",
                ("AutoModo : " + reason[:350], expires, user["id"]),
            )
            cursor.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        return "temporary_ban"
    if points_after >= int(settings["mute_points"]):
        expires = _sql_dt(now + timedelta(minutes=int(settings["mute_minutes"])))
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET muted_until=?,mute_reason=? WHERE id=?",
                (expires, "AutoModo : " + reason[:350], user["id"]),
            )
        return "mute"
    if points_after >= int(settings["warn_points"]):
        with get_db_cursor() as cursor:
            cursor.execute("UPDATE users SET warning_count=warning_count+1 WHERE id=?", (user["id"],))
        return "warning"
    return "none"


def _bot_text(username: str, rule: str, sanction: str, blocked: bool) -> str:
    labels = {
        "profanity": "langage inapproprié",
        "links": "trop de liens",
        "mentions": "mentions excessives",
        "duplicate": "message répété",
        "rate_limit": "débit de messages trop élevé",
        "burst": "rafale de messages",
        "rapid_fire": "rafale instantanée de messages",
        "cooldown": "nouvelle tentative pendant le cooldown",
        "near_duplicate": "copier-coller ou message presque identique",
        "character_flood": "caractères répétés",
        "punctuation_flood": "ponctuation excessive",
        "emoji_flood": "trop d'emojis",
        "word_flood": "mot répété en boucle",
        "uppercase": "message en majuscules",
    }
    cause = labels.get(rule, rule.replace("_", " "))
    if sanction == "temporary_ban":
        return f"🛡️ @{username} a été temporairement exclu par AutoModo après plusieurs infractions ({cause}). Un humain peut revoir la décision."
    if sanction == "mute":
        return f"🛡️ @{username} a été placé en mode muet temporairement par AutoModo ({cause})."
    if blocked:
        return f"🛡️ AutoModo a bloqué un message de @{username} ({cause})."
    return f"🛡️ AutoModo avertit @{username} : {cause}."


def review_message(user: dict, room_id: int, content: str, *, forced_rule: Optional[str] = None,
                   forced_points: Optional[int] = None, forced_detail: str = "") -> dict:
    """Analyse un message ou enregistre une infraction déjà détectée par le websocket."""
    settings = get_automod_settings()
    if not settings["enabled"]:
        return {"blocked": False, "incident": False, "sanction": "none", "bot_message": None}
    if settings["exempt_staff"] and (user.get("is_admin") or user.get("is_moderator") or user.get("is_bot")):
        return {"blocked": False, "incident": False, "sanction": "none", "bot_message": None}

    rule = forced_rule
    points = int(forced_points or 0)
    blocked = False
    detail = forced_detail

    if forced_rule is None:
        profanity = _profanity_hits(content)
        links = re.findall(r"(?:https?://|www\.)[^\s]+", content or "", flags=re.I)
        mentions = re.findall(r"(?<!\w)@[A-Za-zÀ-ÖØ-öø-ÿ0-9_-]{2,32}", content or "")
        if profanity and settings["profanity_mode"] != "allow":
            rule, points = "profanity", 1
            blocked = settings["profanity_mode"] == "block"
            detail = "Mots détectés : " + ", ".join(profanity[:8])
        elif len(links) > int(settings["max_links"]) and settings["link_mode"] != "allow":
            rule, points = "links", 1
            blocked = settings["link_mode"] == "block"
            detail = f"{len(links)} lien(s) détecté(s), maximum {settings['max_links']}"
        elif len(mentions) > int(settings["max_mentions"]):
            rule, points, blocked = "mentions", 2, True
            detail = f"{len(mentions)} mention(s), maximum {settings['max_mentions']}"

    if not rule:
        return {"blocked": False, "incident": False, "sanction": "none", "bot_message": None}

    action = "blocked" if blocked else "allowed_with_warning"
    incident_id = _record_incident(user["id"], room_id, rule, points, action, content, detail)
    total = _current_points(user["id"], int(settings["point_window_minutes"]))
    sanction = _apply_escalation(user, settings, total, detail or rule)

    # La sanction automatique est également visible dans l'historique général.
    if sanction != "none":
        bot = ensure_automod_bot()
        with get_db_cursor() as cursor:
            cursor.execute(
                """INSERT INTO moderation_actions(actor_id,target_id,action,reason,duration_minutes,room_id)
                   VALUES(?,?,?,?,?,?)""",
                (
                    bot["id"], user["id"], "automod_" + sanction, detail or rule,
                    int(settings["mute_minutes"] if sanction == "mute" else settings["temp_ban_minutes"])
                    if sanction in {"mute", "temporary_ban"} else None,
                    room_id,
                ),
            )

    bot_message = None
    if settings["announce_actions"] and (blocked or sanction in {"mute", "temporary_ban"}):
        bot = ensure_automod_bot()
        bot_message = save_message(
            room_id, bot["id"], _bot_text(user["username"], rule, sanction, blocked),
            message_type="automod", metadata={"incident_id": incident_id, "rule": rule, "sanction": sanction},
        )

    return {
        "blocked": blocked,
        "incident": True,
        "incident_id": incident_id,
        "rule": rule,
        "points": points,
        "total_points": total,
        "sanction": sanction,
        "detail": detail,
        "bot_message": bot_message,
    }


def list_automod_incidents(limit: int = 200, status: str = "open") -> list[dict]:
    limit = max(1, min(int(limit), 500))
    params = []
    where = ""
    if status in {"open", "resolved", "ignored"}:
        where = "WHERE i.status=?"
        params.append(status)
    params.append(limit)
    with get_db_cursor() as cursor:
        rows = cursor.execute(
            f"""SELECT i.id,i.rule,i.points,i.action,i.content_preview,i.detail,i.status,
                       i.created_at,i.reviewed_at,u.id AS user_id,u.username,u.class_code,
                       r.id AS room_id,r.name AS room_name,reviewer.username AS reviewed_by
                FROM automod_incidents i
                JOIN users u ON u.id=i.user_id
                LEFT JOIN rooms r ON r.id=i.room_id
                LEFT JOIN users reviewer ON reviewer.id=i.reviewed_by
                {where} ORDER BY CASE WHEN i.status='open' THEN 0 ELSE 1 END,i.created_at DESC LIMIT ?""",
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


def decide_incident(incident_id: int, reviewer_id: int, status: str, note: str = "") -> bool:
    if status not in {"resolved", "ignored", "open"}:
        raise ValueError("État invalide.")
    with get_db_cursor() as cursor:
        cursor.execute(
            """UPDATE automod_incidents SET status=?,review_note=?,reviewed_by=?,reviewed_at=datetime('now')
               WHERE id=?""",
            (status, (note or "")[:500], reviewer_id, incident_id),
        )
        return cursor.rowcount > 0


def clear_user_automod_points(user_id: int, reviewer_id: int) -> int:
    """Annule tous les points AutoModo et lève uniquement ses propres sanctions."""
    with get_db_cursor() as cursor:
        cursor.execute(
            """UPDATE automod_incidents SET status='ignored',review_note='Points remis à zéro',
               reviewed_by=?,reviewed_at=datetime('now') WHERE user_id=? AND status!='ignored'""",
            (reviewer_id, user_id),
        )
        updated = cursor.rowcount
        cursor.execute(
            """UPDATE users SET muted_until=NULL,mute_reason=''
               WHERE id=? AND mute_reason LIKE 'AutoModo :%'""",
            (user_id,),
        )
        cursor.execute(
            """UPDATE users SET is_banned=0,banned_at=NULL,banned_reason='',ban_until=NULL
               WHERE id=? AND banned_reason LIKE 'AutoModo :%'""",
            (user_id,),
        )
        return updated
