from __future__ import annotations

import json
import re
import secrets
import string
from datetime import datetime
from typing import Any, Dict, List, Optional

from database import get_db_cursor
from config import DATABASE_BACKEND
from permissions import moderator_permissions_for_pack, serialize_moderator_permissions
from security import hash_password
from services.class_service import ensure_class_room


class TestLabError(Exception):
    pass


DEFAULT_CLASSES = ["6A", "6B", "5A", "5B", "4A"]
DEFAULT_PASSWORD = "PiChatTest2026!"
PROFILE_COLORS = ["#5865f2", "#57f287", "#f0b232", "#eb459e", "#37b5ff"]
SAMPLE_MESSAGES = [
    "Bonjour, ceci est un message de démonstration.",
    "Je teste les réponses, les réactions et la recherche.",
    "Quelqu’un veut faire une partie dans l’Arcade ?",
    "Mon profil gaming est maintenant rempli.",
    "Le système de PyCoins fonctionne bien.",
    "Message de test pour le panneau de modération.",
    "Je prépare un mini-jeu dans PiGame Studio.",
    "Test du bouton d’envoi réussi ✅",
]


def _clean_prefix(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "", (value or "test").strip().lower())[:12]
    return clean or "test"


def _new_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _batch_code(prefix: str) -> str:
    return "%s-%s-%s" % (prefix, datetime.utcnow().strftime("%Y%m%d%H%M%S"), secrets.token_hex(2))


def _room_ids(cursor: Any) -> Dict[str, int]:
    result: Dict[str, int] = {}
    rows = cursor.execute("SELECT id,name,class_code FROM rooms").fetchall()
    for row in rows:
        if row["class_code"]:
            result[str(row["class_code"]).upper()] = int(row["id"])
        if row["name"] == "général":
            result["general"] = int(row["id"])
    return result


def _central_space_id(cursor: Any) -> Optional[int]:
    row = cursor.execute("SELECT id FROM spaces WHERE slug='pichat-central'").fetchone()
    return int(row["id"]) if row else None


def create_batch(
    admin_id: int,
    account_count: int = 20,
    prefix: str = "test",
    password: Optional[str] = None,
    sample_data: bool = True,
    include_staff: bool = True,
) -> Dict[str, Any]:
    count = max(1, min(int(account_count or 20), 100))
    clean_prefix = _clean_prefix(prefix)
    common_password = (password or "").strip() or DEFAULT_PASSWORD
    if len(common_password) < 8:
        raise TestLabError("Le mot de passe de test doit contenir au moins 8 caractères.")

    for class_code in DEFAULT_CLASSES:
        ensure_class_room(class_code)

    code = _batch_code(clean_prefix)
    short = secrets.token_hex(2)
    password_hash = hash_password(common_password)
    credentials: List[Dict[str, str]] = []

    with get_db_cursor() as cursor:
        central_id = _central_space_id(cursor)
        room_ids = _room_ids(cursor)
        cursor.execute(
            """INSERT INTO test_lab_batches
               (batch_code,created_by,account_count,prefix,sample_data,include_staff,status)
               VALUES (?,?,?,?,?,?,'active')""",
            (code, admin_id, count, clean_prefix, 1 if sample_data else 0, 1 if include_staff else 0),
        )
        batch_id = int(cursor.lastrowid)

        users: List[Dict[str, Any]] = []
        for index in range(1, count + 1):
            class_code = DEFAULT_CLASSES[(index - 1) % len(DEFAULT_CLASSES)]
            username = "%s_%s_%02d" % (clean_prefix, short, index)
            username = username[:32]
            role = "player"
            is_moderator = 0
            moderator_class = None
            permissions = ""
            if include_staff and index <= 3:
                pack = ("small", "standard", "super")[index - 1]
                role = "%s_moderator" % pack
                is_moderator = 1
                moderator_class = class_code
                permissions = serialize_moderator_permissions(moderator_permissions_for_pack(pack))

            coins = 100 + index * 25
            xp = index * 40
            cursor.execute(
                """INSERT INTO users
                   (username,password_hash,status_message,is_admin,is_bot,class_code,is_banned,
                    is_moderator,moderator_class_code,moderator_permissions,grade_title,grade_color,
                    grade_visibility,profile_bio,profile_color,xp,coins,active_space_id,is_test_account)
                   VALUES (?,?,?,0,0,?,0,?,?,?,?,?,'full',?,?,?,?,?,1)""",
                (
                    username,
                    password_hash,
                    "Compte de test PiChat",
                    class_code,
                    is_moderator,
                    moderator_class,
                    permissions,
                    ("MODO TEST" if is_moderator else "JOUEUR TEST"),
                    PROFILE_COLORS[(index - 1) % len(PROFILE_COLORS)],
                    "Compte généré par le Laboratoire de test PiChat.",
                    PROFILE_COLORS[(index - 1) % len(PROFILE_COLORS)],
                    xp,
                    coins,
                    central_id,
                ),
            )
            user_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO test_lab_accounts(batch_id,user_id,username,class_code,role) VALUES (?,?,?,?,?)",
                (batch_id, user_id, username, class_code, role),
            )
            if central_id is not None:
                cursor.execute(
                    "INSERT OR IGNORE INTO space_members(space_id,user_id,role) VALUES (?,?,?)",
                    (central_id, user_id, "moderator" if is_moderator else "member"),
                )
            cursor.execute(
                "INSERT INTO pycoin_transactions(user_id,amount,balance_after,kind,details) VALUES (?,?,?,?,?)",
                (user_id, coins, coins, "test_lab", "Solde de démonstration"),
            )
            users.append({"id": user_id, "username": username, "class_code": class_code, "role": role, "coins": coins})
            credentials.append({"username": username, "password": common_password, "class_code": class_code, "role": role})

        # Trois demandes d'inscription permettent de tester l'onglet Demandes.
        request_count = min(3, max(1, count // 6))
        for offset in range(1, request_count + 1):
            username = "%s_req_%s_%02d" % (clean_prefix, short, offset)
            cursor.execute(
                """INSERT INTO registration_requests(username,password_hash,class_code,status,admin_note)
                   VALUES (?,?,?,'pending','Demande générée par le Laboratoire de test')""",
                (username[:32], password_hash, DEFAULT_CLASSES[offset % len(DEFAULT_CLASSES)]),
            )
            cursor.execute(
                "INSERT INTO test_lab_requests(batch_id,request_id) VALUES (?,?)",
                (batch_id, int(cursor.lastrowid)),
            )

        if sample_data and users:
            general_room = room_ids.get("general") or next(iter(room_ids.values()))
            message_ids: List[int] = []
            for index, user in enumerate(users):
                room_id = room_ids.get(user["class_code"], general_room)
                for turn in range(2):
                    content = SAMPLE_MESSAGES[(index + turn) % len(SAMPLE_MESSAGES)]
                    cursor.execute(
                        "INSERT INTO messages(room_id,user_id,content) VALUES (?,?,?)",
                        (room_id, user["id"], content),
                    )
                    message_ids.append(int(cursor.lastrowid))

                games = [
                    ("valorant", "Valorant", "TestValo%02d" % (index + 1), "PC"),
                    ("brawl-stars", "Brawl Stars", "TestBS%02d" % (index + 1), "Mobile"),
                ]
                if index % 2 == 0:
                    games.append(("roblox", "Roblox", "TestRoblox%02d" % (index + 1), "PC/Mobile"))
                if index % 3 == 0:
                    games.append(("fortnite", "Fortnite", "TestFN%02d" % (index + 1), "Console"))
                for sort_order, game in enumerate(games):
                    cursor.execute(
                        """INSERT OR IGNORE INTO user_game_profiles
                           (user_id,game_key,game_name,username,platform,is_public,sort_order)
                           VALUES (?,?,?,?,?,1,?)""",
                        (user["id"], game[0], game[1], game[2], game[3], sort_order),
                    )

                score = 1000 + index * 137
                cursor.execute(
                    """INSERT INTO arcade_scores
                       (user_id,game_key,score,result_label,details_json,coins_awarded,xp_awarded)
                       VALUES (?,?,?,?,?,5,10)""",
                    (user["id"], "click-rush", score, "%s points" % score, json.dumps({"test_lab": True})),
                )
                cursor.execute(
                    """INSERT INTO arcade_user_stats
                       (user_id,game_key,best_score,best_label,plays,wins,updated_at)
                       VALUES (?,?,?,?,1,0,datetime('now'))
                       ON CONFLICT(user_id,game_key) DO UPDATE SET
                         best_score=excluded.best_score,best_label=excluded.best_label,
                         plays=excluded.plays,wins=excluded.wins,updated_at=excluded.updated_at""",
                    (user["id"], "click-rush", score, "%s points" % score),
                )

            # Échanges privés entre les premiers comptes.
            for index in range(min(6, len(users) - 1)):
                cursor.execute(
                    "INSERT INTO private_messages(sender_id,receiver_id,content) VALUES (?,?,?)",
                    (users[index]["id"], users[index + 1]["id"], "Message privé de démonstration."),
                )

            # Packs finaux 2.2 : amis, demandes, sessions et messages programmés.
            for index in range(0, min(8, len(users) - 1), 2):
                first, second = users[index]["id"], users[index + 1]["id"]
                low, high = sorted((first, second))
                cursor.execute(
                    """INSERT OR IGNORE INTO friendships
                       (user_low_id,user_high_id,requested_by,status,responded_at)
                       VALUES (?,?,?,'accepted',datetime('now'))""",
                    (low, high, first),
                )
            if len(users) >= 3:
                low, high = sorted((users[0]["id"], users[2]["id"]))
                cursor.execute(
                    """INSERT OR IGNORE INTO friendships
                       (user_low_id,user_high_id,requested_by,status) VALUES (?,?,?,'pending')""",
                    (low, high, users[0]["id"]),
                )
            for index, user in enumerate(users[:3]):
                cursor.execute(
                    """INSERT INTO sessions(token,user_id,last_seen_at,user_agent,ip_address)
                       VALUES (?,?,datetime('now'),?,?)""",
                    ("test-session-%s-%s" % (batch_id, index), user["id"], "Navigateur de test", "127.0.0.%s" % (index + 10)),
                )
                cursor.execute(
                    """INSERT INTO scheduled_messages
                       (user_id,room_id,content,send_at,status)
                       VALUES (?,?,?,datetime('now','+1 day'),'pending')""",
                    (user["id"], room_ids.get(user["class_code"], general_room), "Message programmé de démonstration."),
                )

            # Signalements et incidents AutoModo visibles dans les panneaux staff.
            for index, message_id in enumerate(message_ids[: min(5, len(message_ids))]):
                reporter = users[(index + 2) % len(users)]
                cursor.execute(
                    "INSERT OR IGNORE INTO message_reports(message_id,reporter_id,reason,status) VALUES (?,?,?,'open')",
                    (message_id, reporter["id"], "Signalement de test"),
                )
            for index, user in enumerate(users[3:6]):
                cursor.execute(
                    """INSERT INTO automod_incidents
                       (user_id,room_id,rule,points,action,content_preview,detail,status)
                       VALUES (?,?,?,?,'warning','Message de test','Incident généré pour vérifier AutoModo','open')""",
                    (user["id"], room_ids.get(user["class_code"], general_room), "test_lab_spam", index + 1),
                )
                cursor.execute(
                    """INSERT INTO moderation_actions
                       (actor_id,target_id,action,reason,duration_minutes,room_id)
                       VALUES (?,?,?,'Action de démonstration',10,?)""",
                    (admin_id, user["id"], "warning", room_ids.get(user["class_code"], general_room)),
                )

            # Un jeu PiGame sûr en brouillon pour tester l'envoi en validation.
            owner = users[-1]
            slug = "test-lab-%s" % secrets.token_hex(3)
            cursor.execute(
                """INSERT INTO generated_games
                   (owner_id,title,slug,description,icon,source_prompt,generation_mode,
                    html_code,css_code,js_code,status,safety_report)
                   VALUES (?,?,?,?,?,?, 'test_lab',?,?,?,?,?)""",
                (
                    owner["id"],
                    "Jeu test du bouton",
                    slug,
                    "Petit jeu créé automatiquement pour tester PiGame Studio.",
                    "🧪",
                    "Création automatique du Laboratoire de test",
                    "<main><h1>Jeu test</h1><p id='score'>Score : 0</p><button id='plus'>+1</button><button id='reset'>Rejouer</button></main>",
                    "main{text-align:center;padding:24px}button{margin:8px;padding:12px 18px}",
                    "let n=0;const s=document.getElementById('score');document.getElementById('plus').addEventListener('click',()=>{n+=1;s.textContent='Score : '+n});document.getElementById('reset').addEventListener('click',()=>{n=0;s.textContent='Score : 0'});",
                    "draft",
                    json.dumps({"safe": True, "source": "test_lab"}),
                ),
            )

            # Badges de base pour rendre les profils immédiatement visibles.
            badge_rows = cursor.execute("SELECT id,code FROM badge_definitions WHERE code IN ('member','gamer','multi-gamer','arcade-player')").fetchall()
            badges = {row["code"]: int(row["id"]) for row in badge_rows}
            for index, user in enumerate(users):
                for badge_code in ["member", "gamer"] + (["multi-gamer"] if index % 3 == 0 else []) + (["arcade-player"] if index % 2 == 0 else []):
                    badge_id = badges.get(badge_code)
                    if badge_id:
                        cursor.execute(
                            """INSERT OR IGNORE INTO user_badges
                               (user_id,badge_id,awarded_by,reason,showcased,display_order)
                               VALUES (?,?,?,'Données de test',1,0)""",
                            (user["id"], badge_id, admin_id),
                        )

    return {
        "batch_id": batch_id,
        "batch_code": code,
        "account_count": count,
        "request_count": request_count,
        "password": common_password,
        "credentials": credentials,
        "sample_data": bool(sample_data),
        "include_staff": bool(include_staff),
    }


def list_batches() -> List[Dict[str, Any]]:
    with get_db_cursor() as cursor:
        rows = cursor.execute(
            """SELECT b.*,COUNT(a.user_id) AS active_accounts
               FROM test_lab_batches b
               LEFT JOIN test_lab_accounts a ON a.batch_id=b.id
               GROUP BY b.id ORDER BY b.id DESC LIMIT 50"""
        ).fetchall()
    return [dict(row) for row in rows]


def delete_batch(batch_id: int) -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        batch = cursor.execute("SELECT * FROM test_lab_batches WHERE id=?", (batch_id,)).fetchone()
        if not batch:
            raise TestLabError("Lot de test introuvable.")
        user_rows = cursor.execute("SELECT user_id,username FROM test_lab_accounts WHERE batch_id=?", (batch_id,)).fetchall()
        request_rows = cursor.execute("SELECT request_id FROM test_lab_requests WHERE batch_id=?", (batch_id,)).fetchall()
        for row in request_rows:
            cursor.execute("DELETE FROM registration_requests WHERE id=?", (row["request_id"],))
        removed = 0
        for row in user_rows:
            # Double sécurité : seuls les comptes enregistrés dans le lot sont supprimés.
            linked = cursor.execute(
                "SELECT 1 FROM test_lab_accounts WHERE batch_id=? AND user_id=? AND username=?",
                (batch_id, row["user_id"], row["username"]),
            ).fetchone()
            if linked:
                cursor.execute("DELETE FROM users WHERE id=?", (row["user_id"],))
                removed += 1
        cursor.execute(
            "UPDATE test_lab_batches SET status='deleted',deleted_at=datetime('now') WHERE id=?",
            (batch_id,),
        )
    return {"batch_id": int(batch_id), "removed_accounts": removed, "removed_requests": len(request_rows)}


def simulate_connections(count: int = 12, batch_id: Optional[int] = None) -> Dict[str, Any]:
    """Crée des sessions factices uniquement pour des comptes de test.

    Cela charge les écrans de présence/sessions sans ouvrir de faux sockets réseau ni
    toucher à de vrais comptes. Les sessions disparaissent avec le lot grâce au CASCADE.
    """
    wanted=max(2,min(int(count or 12),100))
    with get_db_cursor() as cursor:
        if batch_id is None:
            batch=cursor.execute("SELECT id FROM test_lab_batches WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
            if not batch: raise TestLabError('Crée d’abord un lot de test.')
            batch_id=int(batch['id'])
        rows=cursor.execute(
            """SELECT a.user_id,a.username FROM test_lab_accounts a
               JOIN test_lab_batches b ON b.id=a.batch_id
               JOIN users u ON u.id=a.user_id
               WHERE a.batch_id=? AND b.status='active' AND u.is_test_account=1
               ORDER BY a.username""",(batch_id,),
        ).fetchall()
        if not rows: raise TestLabError('Aucun compte de test actif dans ce lot.')
        # Retire uniquement les anciennes sessions simulées de ce lot.
        cursor.execute("DELETE FROM sessions WHERE token LIKE ?",(f'test-sim-{batch_id}-%',))
        for index in range(wanted):
            user=rows[index % len(rows)]
            token=f'test-sim-{batch_id}-{index}-{secrets.token_hex(6)}'
            cursor.execute(
                """INSERT INTO sessions(token,user_id,last_seen_at,user_agent,ip_address)
                   VALUES (?,?,datetime('now'),?,?)""",
                (token,int(user['user_id']),f'PiChat Labo connexion {index+1}',f'198.51.100.{(index%200)+10}'),
            )
    return {'ok':True,'batch_id':int(batch_id),'simulated_connections':wanted,'test_users':len(rows)}


def delete_all_active_batches() -> Dict[str, Any]:
    batches = list_batches()
    removed_accounts = 0
    removed_batches = 0
    for batch in batches:
        if batch.get("status") == "active":
            result = delete_batch(int(batch["id"]))
            removed_accounts += int(result["removed_accounts"])
            removed_batches += 1
    return {"removed_batches": removed_batches, "removed_accounts": removed_accounts}


def diagnostics() -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        counts = {}
        for table in [
            "users", "rooms", "messages", "private_messages", "message_reports",
            "automod_incidents", "arcade_scores", "generated_games", "test_lab_batches",
            "scheduled_messages", "friendships", "sessions", "user_blocks", "auto_backup_runs",
        ]:
            try:
                counts[table] = int(cursor.execute("SELECT COUNT(*) AS n FROM %s" % table).fetchone()["n"])
            except Exception:
                counts[table] = None
        active_batches = int(cursor.execute("SELECT COUNT(*) AS n FROM test_lab_batches WHERE status='active'").fetchone()["n"])
        test_accounts = int(cursor.execute("SELECT COUNT(*) AS n FROM test_lab_accounts").fetchone()["n"])
    return {
        "database": "ok",
        "counts": counts,
        "active_batches": active_batches,
        "test_accounts": test_accounts,
        "checks": [
            {"key": "database", "label": "Base "+("PostgreSQL" if DATABASE_BACKEND=="postgresql" else "SQLite"), "ok": True},
            {"key": "rooms", "label": "Salons disponibles", "ok": bool(counts.get("rooms"))},
            {"key": "users", "label": "Comptes disponibles", "ok": bool(counts.get("users"))},
            {"key": "game_studio", "label": "PiGame Studio", "ok": counts.get("generated_games") is not None},
            {"key": "arcade", "label": "Arcade", "ok": counts.get("arcade_scores") is not None},
            {"key": "final_packs", "label": "Packs finaux 2.2", "ok": counts.get("scheduled_messages") is not None and counts.get("friendships") is not None},
        ],
    }
