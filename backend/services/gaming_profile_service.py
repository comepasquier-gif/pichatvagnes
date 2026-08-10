import re
from typing import Dict, List, Optional

from database import get_db_cursor


DEFAULT_GAME_CATALOG = [
    {"key": "valorant", "name": "Valorant", "icon": "🎯", "username_hint": "Pseudo#TAG", "platform_hint": "PC"},
    {"key": "brawl-stars", "name": "Brawl Stars", "icon": "⭐", "username_hint": "Pseudo ou tag joueur", "platform_hint": "Mobile"},
    {"key": "roblox", "name": "Roblox", "icon": "⬛", "username_hint": "Pseudo Roblox", "platform_hint": "PC / Mobile / Console"},
    {"key": "fortnite", "name": "Fortnite", "icon": "🪂", "username_hint": "Pseudo Epic Games", "platform_hint": "PC / Console / Mobile"},
]

KNOWN_GAMES = {item["key"]: item for item in DEFAULT_GAME_CATALOG}
AUTO_BADGE_CODES = {"member", "admin", "moderator", "gamer", "multi-gamer", "profile-complete"}


def _slug(value: str, fallback: str = "jeu") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or fallback)[:40]


def get_game_catalog() -> List[Dict[str, str]]:
    return [dict(item) for item in DEFAULT_GAME_CATALOG]


def list_games(user_id: int, include_private: bool = False) -> List[Dict]:
    sql = """
        SELECT id,game_key,game_name,username,platform,is_public,sort_order,created_at,updated_at
        FROM user_game_profiles WHERE user_id=?
    """
    params = [user_id]
    if not include_private:
        sql += " AND is_public=1"
    sql += " ORDER BY sort_order,id"
    with get_db_cursor() as cursor:
        rows = cursor.execute(sql, tuple(params)).fetchall()
    return [
        {
            **dict(row),
            "is_public": bool(row["is_public"]),
            "icon": KNOWN_GAMES.get(row["game_key"], {}).get("icon", "🎮"),
        }
        for row in rows
    ]


def replace_games(user_id: int, games: List[Dict]) -> List[Dict]:
    cleaned = []
    seen = set()
    for index, game in enumerate(games[:12]):
        game_name = (game.get("game_name") or "").strip()[:48]
        username = (game.get("username") or "").strip()[:80]
        platform = (game.get("platform") or "").strip()[:32]
        if not game_name or not username:
            continue
        raw_key = (game.get("game_key") or "").strip().lower()
        game_key = raw_key if raw_key in KNOWN_GAMES else "custom-" + _slug(game_name)
        base_key = game_key
        suffix = 2
        while game_key in seen:
            game_key = "%s-%d" % (base_key[:35], suffix)
            suffix += 1
        seen.add(game_key)
        cleaned.append(
            {
                "game_key": game_key,
                "game_name": KNOWN_GAMES.get(game_key, {}).get("name", game_name),
                "username": username,
                "platform": platform,
                "is_public": 1 if game.get("is_public", True) else 0,
                "sort_order": index,
            }
        )
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM user_game_profiles WHERE user_id=?", (user_id,))
        for item in cleaned:
            cursor.execute(
                """
                INSERT INTO user_game_profiles
                    (user_id,game_key,game_name,username,platform,is_public,sort_order,updated_at)
                VALUES (?,?,?,?,?,?,?,datetime('now'))
                """,
                (
                    user_id,
                    item["game_key"],
                    item["game_name"],
                    item["username"],
                    item["platform"],
                    item["is_public"],
                    item["sort_order"],
                ),
            )
    sync_automatic_badges(user_id)
    return list_games(user_id, include_private=True)


def get_user_badges(user_id: int, active_only: bool = True) -> List[Dict]:
    sql = """
        SELECT b.id,b.code,b.name,b.description,b.icon,b.color,b.category,b.is_system,b.is_active,
               ub.reason,ub.awarded_at,ub.showcased,ub.display_order,
               a.username AS awarded_by_username
        FROM user_badges ub
        JOIN badge_definitions b ON b.id=ub.badge_id
        LEFT JOIN users a ON a.id=ub.awarded_by
        WHERE ub.user_id=?
    """
    if active_only:
        sql += " AND b.is_active=1"
    sql += " ORDER BY ub.showcased DESC,ub.display_order,b.id"
    with get_db_cursor() as cursor:
        rows = cursor.execute(sql, (user_id,)).fetchall()
    return [
        {
            **dict(row),
            "is_system": bool(row["is_system"]),
            "is_active": bool(row["is_active"]),
            "showcased": bool(row["showcased"]),
        }
        for row in rows
    ]


def sync_automatic_badges(user_id: int) -> None:
    """Synchronise les badges automatiques sans réécrire la base si rien n'a changé."""
    reasons = {
        "member": "Membre de PiChat",
        "admin": "Administrateur PiChat",
        "moderator": "Modérateur PiChat",
        "gamer": "Au moins un pseudo de jeu renseigné",
        "multi-gamer": "Quatre jeux ou plus renseignés",
        "profile-complete": "Profil PiChat complété",
    }
    with get_db_cursor() as cursor:
        user = cursor.execute(
            """
            SELECT id,is_admin,is_moderator,status_message,profile_bio
            FROM users WHERE id=? AND is_bot=0
            """,
            (user_id,),
        ).fetchone()
        if not user:
            return
        game_count = cursor.execute(
            "SELECT COUNT(*) FROM user_game_profiles WHERE user_id=? AND trim(username)!=''",
            (user_id,),
        ).fetchone()[0]
        desired = {"member"}
        if user["is_admin"]:
            desired.add("admin")
        elif user["is_moderator"]:
            desired.add("moderator")
        if game_count >= 1:
            desired.add("gamer")
        if game_count >= 4:
            desired.add("multi-gamer")
        if (user["status_message"] or "").strip() and (user["profile_bio"] or "").strip() and game_count >= 1:
            desired.add("profile-complete")

        rows = cursor.execute(
            """
            SELECT b.id,b.code
            FROM user_badges ub
            JOIN badge_definitions b ON b.id=ub.badge_id
            WHERE ub.user_id=? AND ub.awarded_by IS NULL AND b.code IN (?,?,?,?,?,?)
            """,
            (user_id, "member", "admin", "moderator", "gamer", "multi-gamer", "profile-complete"),
        ).fetchall()
        current = {row["code"]: row["id"] for row in rows}
        to_remove = set(current) - desired
        to_add = desired - set(current)
        for code in to_remove:
            cursor.execute(
                "DELETE FROM user_badges WHERE user_id=? AND badge_id=? AND awarded_by IS NULL",
                (user_id, current[code]),
            )
        for code in to_add:
            badge = cursor.execute(
                "SELECT id FROM badge_definitions WHERE code=? AND is_active=1", (code,)
            ).fetchone()
            if badge:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO user_badges
                        (user_id,badge_id,awarded_by,reason,showcased,display_order)
                    VALUES (?,?,NULL,?,1,0)
                    """,
                    (user_id, badge["id"], reasons[code]),
                )


def list_badge_catalog(include_inactive: bool = True) -> List[Dict]:
    sql = """
        SELECT b.id,b.code,b.name,b.description,b.icon,b.color,b.category,b.is_system,b.is_active,b.created_at,
               COUNT(ub.user_id) AS awarded_count
        FROM badge_definitions b
        LEFT JOIN user_badges ub ON ub.badge_id=b.id
    """
    if not include_inactive:
        sql += " WHERE b.is_active=1"
    sql += " GROUP BY b.id ORDER BY b.is_system DESC,b.category,b.name"
    with get_db_cursor() as cursor:
        rows = cursor.execute(sql).fetchall()
    return [
        {
            **dict(row),
            "is_system": bool(row["is_system"]),
            "is_active": bool(row["is_active"]),
            "awarded_count": int(row["awarded_count"] or 0),
        }
        for row in rows
    ]


def create_badge(data: Dict) -> Dict:
    name = (data.get("name") or "").strip()[:40]
    code = _slug(data.get("code") or name, "badge")
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO badge_definitions
                (code,name,description,icon,color,category,is_system,is_active)
            VALUES (?,?,?,?,?,?,0,1)
            """,
            (
                code,
                name,
                (data.get("description") or "").strip()[:180],
                (data.get("icon") or "🏅").strip()[:12],
                data.get("color") or "#f0b232",
                _slug(data.get("category") or "custom", "custom")[:24],
            ),
        )
        badge_id = cursor.lastrowid
        row = cursor.execute("SELECT * FROM badge_definitions WHERE id=?", (badge_id,)).fetchone()
    result = dict(row)
    result["is_system"] = bool(result["is_system"])
    result["is_active"] = bool(result["is_active"])
    result["awarded_count"] = 0
    return result


def update_badge(badge_id: int, data: Dict) -> Dict:
    allowed = {"name", "description", "icon", "color", "category", "is_active"}
    values = {key: value for key, value in data.items() if key in allowed and value is not None}
    if not values:
        catalog = [item for item in list_badge_catalog() if item["id"] == badge_id]
        if not catalog:
            raise ValueError("Badge introuvable.")
        return catalog[0]
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT is_system FROM badge_definitions WHERE id=?", (badge_id,)).fetchone()
        if not row:
            raise ValueError("Badge introuvable.")
        if row["is_system"] and "is_active" in values and not values["is_active"]:
            raise ValueError("Un badge système ne peut pas être désactivé.")
        assignments = []
        params = []
        for key, value in values.items():
            if key in {"name", "description", "icon", "category"}:
                value = (value or "").strip()
            if key == "category":
                value = _slug(value, "custom")[:24]
            if key == "is_active":
                value = 1 if value else 0
            assignments.append(key + "=?")
            params.append(value)
        params.append(badge_id)
        cursor.execute("UPDATE badge_definitions SET " + ",".join(assignments) + " WHERE id=?", tuple(params))
    return [item for item in list_badge_catalog() if item["id"] == badge_id][0]


def award_badge(user_id: int, badge_id: int, awarded_by: int, reason: str = "", showcased: bool = True) -> Dict:
    with get_db_cursor() as cursor:
        user = cursor.execute("SELECT id FROM users WHERE id=? AND is_bot=0", (user_id,)).fetchone()
        badge = cursor.execute("SELECT id,is_active FROM badge_definitions WHERE id=?", (badge_id,)).fetchone()
        if not user:
            raise ValueError("Utilisateur introuvable.")
        if not badge or not badge["is_active"]:
            raise ValueError("Badge introuvable ou désactivé.")
        cursor.execute(
            """
            INSERT INTO user_badges (user_id,badge_id,awarded_by,reason,showcased,display_order)
            VALUES (?,?,?,?,?,0)
            ON CONFLICT(user_id,badge_id) DO UPDATE SET
                awarded_by=excluded.awarded_by,
                reason=excluded.reason,
                awarded_at=datetime('now'),
                showcased=excluded.showcased
            """,
            (user_id, badge_id, awarded_by, (reason or "").strip()[:180], 1 if showcased else 0),
        )
    return {"user_id": user_id, "badges": get_user_badges(user_id, active_only=False)}


def revoke_badge(user_id: int, badge_id: int) -> Dict:
    with get_db_cursor() as cursor:
        badge = cursor.execute("SELECT code,is_system FROM badge_definitions WHERE id=?", (badge_id,)).fetchone()
        if not badge:
            raise ValueError("Badge introuvable.")
        if badge["is_system"] or badge["code"] in AUTO_BADGE_CODES:
            raise ValueError("Ce badge est attribué automatiquement par PiChat.")
        cursor.execute("DELETE FROM user_badges WHERE user_id=? AND badge_id=?", (user_id, badge_id))
    return {"user_id": user_id, "badges": get_user_badges(user_id, active_only=False)}


def delete_game_profile(user_id: int, game_profile_id: int) -> List[Dict]:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT id FROM user_game_profiles WHERE id=? AND user_id=?",
            (game_profile_id, user_id),
        ).fetchone()
        if not row:
            raise ValueError("Profil de jeu introuvable.")
        cursor.execute("DELETE FROM user_game_profiles WHERE id=?", (game_profile_id,))
    sync_automatic_badges(user_id)
    return list_games(user_id, include_private=True)
