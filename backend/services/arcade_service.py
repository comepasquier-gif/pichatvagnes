import hashlib
import json
import random
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import get_db_cursor


ARCADE_CATALOG = [
    {
        "key": "reflex",
        "name": "Réflexe éclair",
        "icon": "⚡",
        "description": "Clique dès que le bouton devient vert.",
        "score_hint": "Plus ton temps est bas, plus tu marques de points.",
    },
    {
        "key": "memory",
        "name": "Mémoire express",
        "icon": "🧠",
        "description": "Retrouve les six paires avec le moins de coups possible.",
        "score_hint": "Peu de coups et un temps court donnent un meilleur score.",
    },
    {
        "key": "clicker",
        "name": "Click Rush",
        "icon": "👆",
        "description": "Fais le plus de clics possible en dix secondes.",
        "score_hint": "Un clic vaut un point.",
    },
    {
        "key": "number",
        "name": "Nombre mystère",
        "icon": "🔢",
        "description": "Trouve un nombre entre 1 et 100 avec les indices plus haut / plus bas.",
        "score_hint": "Moins tu fais de tentatives, meilleur est le score.",
    },
    {
        "key": "quiz",
        "name": "Quiz express",
        "icon": "🧩",
        "description": "Réponds à cinq questions rapides de culture générale.",
        "score_hint": "100 points par bonne réponse, avec un bonus de rapidité.",
    },
    {
        "key": "tictactoe",
        "name": "Morpion vs PiBot",
        "icon": "⭕",
        "description": "Aligne trois symboles avant PiBot.",
        "score_hint": "Victoire : 300 points · nul : 120 · défaite : 30.",
    },
]

CATALOG_BY_KEY = {item["key"]: item for item in ARCADE_CATALOG}

QUIZ_BANK = [
    {"q": "Quelle planète est surnommée la planète rouge ?", "options": ["Mars", "Vénus", "Jupiter", "Mercure"], "answer": 0},
    {"q": "Combien y a-t-il de côtés dans un hexagone ?", "options": ["5", "6", "7", "8"], "answer": 1},
    {"q": "Quel est le plus grand océan du monde ?", "options": ["Atlantique", "Indien", "Pacifique", "Arctique"], "answer": 2},
    {"q": "Dans quel langage PiChat est-il principalement développé côté serveur ?", "options": ["Python", "Java", "Swift", "C++"], "answer": 0},
    {"q": "Quel animal est le plus rapide sur terre ?", "options": ["Lion", "Guépard", "Antilope", "Cheval"], "answer": 1},
    {"q": "Quelle est la capitale de l'Italie ?", "options": ["Milan", "Venise", "Rome", "Naples"], "answer": 2},
    {"q": "Combien font 9 × 8 ?", "options": ["64", "70", "72", "81"], "answer": 2},
    {"q": "Quel gaz les plantes absorbent-elles principalement ?", "options": ["Oxygène", "Dioxyde de carbone", "Azote", "Hydrogène"], "answer": 1},
    {"q": "Quel pays a la forme d'une botte ?", "options": ["Espagne", "Italie", "Grèce", "Portugal"], "answer": 1},
    {"q": "Quelle couleur obtient-on en mélangeant bleu et jaune ?", "options": ["Violet", "Orange", "Vert", "Rouge"], "answer": 2},
    {"q": "Combien de minutes y a-t-il dans deux heures ?", "options": ["90", "100", "120", "140"], "answer": 2},
    {"q": "Quel instrument possède généralement 88 touches ?", "options": ["Guitare", "Piano", "Violon", "Batterie"], "answer": 1},
    {"q": "Quel est le symbole chimique de l'eau ?", "options": ["CO2", "O2", "H2O", "NaCl"], "answer": 2},
    {"q": "Quel continent compte le plus de pays ?", "options": ["Europe", "Asie", "Afrique", "Amérique"], "answer": 2},
    {"q": "Quelle saison vient après le printemps ?", "options": ["Automne", "Hiver", "Été", "Mousson"], "answer": 2},
]

MEMORY_SYMBOLS = ["🍓", "🚀", "🐼", "🎮", "🌈", "⚽", "🍕", "🎧", "🦊", "⭐", "🧪", "🛹"]

BADGES = [
    ("arcade-player", "Joueur d'arcade", "A terminé son premier mini-jeu", "🕹️", "#37b5ff", "arcade"),
    ("arcade-regular", "Habitué de l'arcade", "A terminé 25 parties", "🎟️", "#b06cff", "arcade"),
    ("arcade-master", "Maître de l'arcade", "A terminé 100 parties", "👑", "#f0b232", "arcade"),
    ("reflex-ace", "Réflexe éclair", "Réaction inférieure à 250 ms", "⚡", "#fee75c", "arcade"),
    ("memory-master", "Mémoire de maître", "Mémoire terminée en 12 coups ou moins", "🧠", "#57f287", "arcade"),
    ("quiz-star", "Sans-faute", "Cinq bonnes réponses au Quiz express", "🌟", "#f0b232", "arcade"),
    ("click-frenzy", "Doigt turbo", "Au moins 55 clics en dix secondes", "🔥", "#ed4245", "arcade"),
    ("tactical-player", "Tacticien", "A battu PiBot au morpion", "⭕", "#5865f2", "arcade"),
]


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _parse_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def get_arcade_settings() -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT * FROM arcade_settings WHERE id=1").fetchone()
    if not row:
        return {
            "enabled": True,
            "rewards_enabled": True,
            "rewarded_plays_per_day": 5,
            "daily_coin_cap": 30,
            "daily_challenge_coins": 25,
            "daily_challenge_xp": 40,
        }
    return {
        "enabled": bool(row["enabled"]),
        "rewards_enabled": bool(row["rewards_enabled"]),
        "rewarded_plays_per_day": int(row["rewarded_plays_per_day"] or 0),
        "daily_coin_cap": int(row["daily_coin_cap"] or 0),
        "daily_challenge_coins": int(row["daily_challenge_coins"] or 0),
        "daily_challenge_xp": int(row["daily_challenge_xp"] or 0),
    }


def update_arcade_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    current = get_arcade_settings()
    updated = dict(current)
    bool_keys = {"enabled", "rewards_enabled"}
    int_limits = {
        "rewarded_plays_per_day": (0, 50),
        "daily_coin_cap": (0, 1000),
        "daily_challenge_coins": (0, 1000),
        "daily_challenge_xp": (0, 5000),
    }
    for key in bool_keys:
        if key in values and values[key] is not None:
            updated[key] = bool(values[key])
    for key, limits in int_limits.items():
        if key in values and values[key] is not None:
            number = int(values[key])
            if number < limits[0] or number > limits[1]:
                raise ValueError("Valeur invalide pour %s." % key)
            updated[key] = number
    with get_db_cursor() as cursor:
        cursor.execute(
            """UPDATE arcade_settings SET enabled=?,rewards_enabled=?,rewarded_plays_per_day=?,
               daily_coin_cap=?,daily_challenge_coins=?,daily_challenge_xp=?,updated_at=datetime('now') WHERE id=1""",
            (
                1 if updated["enabled"] else 0,
                1 if updated["rewards_enabled"] else 0,
                updated["rewarded_plays_per_day"],
                updated["daily_coin_cap"],
                updated["daily_challenge_coins"],
                updated["daily_challenge_xp"],
            ),
        )
    return get_arcade_settings()


def _daily_challenge() -> Dict[str, Any]:
    today = _utc_today()
    digest = hashlib.sha256((today + "|PiChatArcade").encode("utf-8")).digest()
    game = ARCADE_CATALOG[digest[0] % len(ARCADE_CATALOG)]
    targets = {
        "reflex": 1180,
        "memory": 700,
        "clicker": 38,
        "number": 70,
        "quiz": 400,
        "tictactoe": 300,
    }
    return {
        "date": today,
        "game_key": game["key"],
        "game_name": game["name"],
        "icon": game["icon"],
        "target_score": targets[game["key"]],
    }


def _public_session(session_id: str, game_key: str, state: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "session_id": session_id,
        "game": dict(CATALOG_BY_KEY[game_key]),
        "game_key": game_key,
    }
    if game_key == "number":
        base.update({"minimum": 1, "maximum": 100, "attempts": int(state.get("attempts") or 0)})
    elif game_key == "quiz":
        base["questions"] = [
            {"question": item["q"], "options": list(item["options"])} for item in state.get("questions", [])
        ]
    elif game_key == "memory":
        base["cards"] = list(state.get("cards", []))
        base["pairs"] = 6
    elif game_key == "reflex":
        base["wait_ms"] = int(state.get("wait_ms") or 1800)
    elif game_key == "clicker":
        base["duration_ms"] = 10000
    elif game_key == "tictactoe":
        base.update({"board": list(state.get("board", [""] * 9)), "status": state.get("status", "active")})
    return base


def start_game(user_id: int, game_key: str) -> Dict[str, Any]:
    settings = get_arcade_settings()
    if not settings["enabled"]:
        raise PermissionError("L'Arcade est désactivée par l'administration.")
    if game_key not in CATALOG_BY_KEY:
        raise ValueError("Mini-jeu introuvable.")

    now = time.time()
    state: Dict[str, Any] = {"started_ts": now}
    if game_key == "number":
        state.update({"secret": random.randint(1, 100), "attempts": 0, "guesses": []})
    elif game_key == "quiz":
        state["questions"] = random.sample(QUIZ_BANK, 5)
    elif game_key == "memory":
        symbols = random.sample(MEMORY_SYMBOLS, 6)
        cards = symbols + symbols
        random.shuffle(cards)
        state["cards"] = cards
    elif game_key == "reflex":
        state["wait_ms"] = random.randint(1300, 3600)
    elif game_key == "clicker":
        state["duration_ms"] = 10000
    elif game_key == "tictactoe":
        state.update({"board": [""] * 9, "status": "active"})

    session_id = secrets.token_urlsafe(18)
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM arcade_sessions WHERE expires_at < datetime('now') OR completed_at IS NOT NULL")
        cursor.execute(
            """INSERT INTO arcade_sessions(id,user_id,game_key,state_json,expires_at)
               VALUES (?,?,?,?,datetime('now','+15 minutes'))""",
            (session_id, user_id, game_key, json.dumps(state, ensure_ascii=False)),
        )
    return _public_session(session_id, game_key, state)


def _winner(board: List[str]) -> str:
    lines = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return ""


def _bot_move(board: List[str]) -> None:
    available = [i for i, value in enumerate(board) if not value]
    if not available:
        return
    for symbol in ("O", "X"):
        for cell in available:
            test = list(board)
            test[cell] = symbol
            if _winner(test) == symbol:
                board[cell] = "O"
                return
    if 4 in available:
        board[4] = "O"
        return
    corners = [cell for cell in (0, 2, 6, 8) if cell in available]
    board[random.choice(corners or available)] = "O"


def _insert_transaction(cursor, user_id: int, amount: int, kind: str, details: str) -> int:
    cursor.execute("UPDATE users SET coins=coins+? WHERE id=?", (amount, user_id))
    row = cursor.execute("SELECT coins FROM users WHERE id=?", (user_id,)).fetchone()
    balance = int(row["coins"] or 0)
    cursor.execute(
        """INSERT INTO pycoin_transactions(user_id,amount,balance_after,kind,details)
           VALUES (?,?,?,?,?)""",
        (user_id, amount, balance, kind[:40], details[:240]),
    )
    return balance


def _ensure_arcade_badges(cursor) -> None:
    for badge in BADGES:
        cursor.execute(
            """INSERT OR IGNORE INTO badge_definitions
               (code,name,description,icon,color,category,is_system,is_active)
               VALUES (?,?,?,?,?,?,1,1)""",
            badge,
        )


def _grant_badge(cursor, user_id: int, code: str, reason: str) -> None:
    badge = cursor.execute("SELECT id FROM badge_definitions WHERE code=? AND is_active=1", (code,)).fetchone()
    if badge:
        cursor.execute(
            """INSERT OR IGNORE INTO user_badges
               (user_id,badge_id,awarded_by,reason,showcased,display_order)
               VALUES (?,?,NULL,?,1,0)""",
            (user_id, badge["id"], reason[:180]),
        )


def _sync_badges(cursor, user_id: int, game_key: str, details: Dict[str, Any]) -> None:
    _ensure_arcade_badges(cursor)
    total = cursor.execute("SELECT COUNT(*) AS n FROM arcade_scores WHERE user_id=?", (user_id,)).fetchone()["n"]
    if int(total) >= 1:
        _grant_badge(cursor, user_id, "arcade-player", "Première partie terminée")
    if int(total) >= 25:
        _grant_badge(cursor, user_id, "arcade-regular", "25 parties terminées")
    if int(total) >= 100:
        _grant_badge(cursor, user_id, "arcade-master", "100 parties terminées")
    if game_key == "reflex" and int(details.get("reaction_ms") or 9999) < 250:
        _grant_badge(cursor, user_id, "reflex-ace", "Réaction sous les 250 ms")
    if game_key == "memory" and int(details.get("moves") or 999) <= 12:
        _grant_badge(cursor, user_id, "memory-master", "Mémoire terminée en 12 coups ou moins")
    if game_key == "quiz" and int(details.get("correct") or 0) == 5:
        _grant_badge(cursor, user_id, "quiz-star", "Sans-faute au Quiz express")
    if game_key == "clicker" and int(details.get("clicks") or 0) >= 55:
        _grant_badge(cursor, user_id, "click-frenzy", "55 clics ou plus en dix secondes")
    if game_key == "tictactoe" and details.get("outcome") == "win":
        _grant_badge(cursor, user_id, "tactical-player", "Victoire contre PiBot")


def _complete_game(
    cursor,
    user_id: int,
    session_id: str,
    game_key: str,
    score: int,
    result_label: str,
    details: Dict[str, Any],
    won: bool = False,
) -> Dict[str, Any]:
    score = max(0, min(int(score), 100000))
    cursor.execute("UPDATE arcade_sessions SET completed_at=datetime('now') WHERE id=?", (session_id,))

    today = _utc_today()
    settings_row = cursor.execute("SELECT * FROM arcade_settings WHERE id=1").fetchone()
    settings = {
        "enabled": bool(settings_row["enabled"]),
        "rewards_enabled": bool(settings_row["rewards_enabled"]),
        "rewarded_plays_per_day": int(settings_row["rewarded_plays_per_day"] or 0),
        "daily_coin_cap": int(settings_row["daily_coin_cap"] or 0),
        "daily_challenge_coins": int(settings_row["daily_challenge_coins"] or 0),
        "daily_challenge_xp": int(settings_row["daily_challenge_xp"] or 0),
    }

    rewarded_today = cursor.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(coins_awarded),0) AS coins FROM arcade_scores WHERE user_id=? AND date(created_at)=?",
        (user_id, today),
    ).fetchone()
    coins = 0
    xp = 0
    if settings["rewards_enabled"] and int(rewarded_today["n"] or 0) < settings["rewarded_plays_per_day"]:
        suggested = max(1, min(7, 1 + score // 120))
        remaining = max(0, settings["daily_coin_cap"] - int(rewarded_today["coins"] or 0))
        coins = min(suggested, remaining)
        xp = max(2, min(15, 3 + score // 80))

    cursor.execute(
        """INSERT INTO arcade_scores
           (user_id,game_key,score,result_label,details_json,coins_awarded,xp_awarded)
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, game_key, score, result_label[:120], json.dumps(details, ensure_ascii=False), coins, xp),
    )
    cursor.execute(
        """INSERT INTO arcade_user_stats(user_id,game_key,best_score,best_label,plays,wins,updated_at)
           VALUES (?,?,?,?,1,?,datetime('now'))
           ON CONFLICT(user_id,game_key) DO UPDATE SET
             best_score=MAX(arcade_user_stats.best_score,excluded.best_score),
             best_label=CASE WHEN excluded.best_score>arcade_user_stats.best_score THEN excluded.best_label ELSE arcade_user_stats.best_label END,
             plays=arcade_user_stats.plays+1,
             wins=arcade_user_stats.wins+excluded.wins,
             updated_at=datetime('now')""",
        (user_id, game_key, score, result_label[:120], 1 if won else 0),
    )

    balance = None
    if coins > 0:
        balance = _insert_transaction(cursor, user_id, coins, "arcade_reward", "%s · %s" % (CATALOG_BY_KEY[game_key]["name"], result_label))
    if xp > 0:
        cursor.execute("UPDATE users SET xp=xp+? WHERE id=?", (xp, user_id))

    challenge = _daily_challenge()
    challenge_bonus = {"claimed": False, "coins": 0, "xp": 0}
    if settings["rewards_enabled"] and game_key == challenge["game_key"] and score >= int(challenge["target_score"]):
        existing = cursor.execute(
            "SELECT 1 FROM arcade_daily_claims WHERE user_id=? AND challenge_date=?",
            (user_id, challenge["date"]),
        ).fetchone()
        if not existing:
            cursor.execute(
                """INSERT INTO arcade_daily_claims(user_id,challenge_date,game_key,score)
                   VALUES (?,?,?,?)""",
                (user_id, challenge["date"], game_key, score),
            )
            challenge_bonus = {
                "claimed": True,
                "coins": settings["daily_challenge_coins"],
                "xp": settings["daily_challenge_xp"],
            }
            if settings["daily_challenge_coins"] > 0:
                balance = _insert_transaction(
                    cursor,
                    user_id,
                    settings["daily_challenge_coins"],
                    "arcade_daily",
                    "Défi Arcade du %s" % challenge["date"],
                )
            if settings["daily_challenge_xp"] > 0:
                cursor.execute("UPDATE users SET xp=xp+? WHERE id=?", (settings["daily_challenge_xp"], user_id))

    _sync_badges(cursor, user_id, game_key, details)

    return {
        "completed": True,
        "game_key": game_key,
        "score": score,
        "result_label": result_label,
        "details": details,
        "reward": {"coins": coins, "xp": xp, "balance": balance},
        "daily_challenge_bonus": challenge_bonus,
    }


def play_action(user_id: int, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        row = cursor.execute(
            """SELECT id,user_id,game_key,state_json,completed_at,
                      CASE WHEN expires_at < datetime('now') THEN 1 ELSE 0 END AS expired
               FROM arcade_sessions WHERE id=?""",
            (session_id,),
        ).fetchone()
        if not row or int(row["user_id"]) != int(user_id):
            raise ValueError("Partie introuvable.")
        if row["completed_at"]:
            raise ValueError("Cette partie est déjà terminée.")
        if row["expired"]:
            raise ValueError("Cette partie a expiré. Relance le mini-jeu.")

        game_key = row["game_key"]
        state = _parse_json(row["state_json"], {})
        elapsed_ms = max(0, int((time.time() - float(state.get("started_ts") or time.time())) * 1000))

        if game_key == "number":
            guess = payload.get("guess")
            if guess is None:
                raise ValueError("Entre un nombre entre 1 et 100.")
            guess = int(guess)
            if guess < 1 or guess > 100:
                raise ValueError("Le nombre doit être compris entre 1 et 100.")
            state["attempts"] = int(state.get("attempts") or 0) + 1
            state.setdefault("guesses", []).append(guess)
            secret = int(state["secret"])
            if guess != secret:
                cursor.execute("UPDATE arcade_sessions SET state_json=? WHERE id=?", (json.dumps(state), session_id))
                return {
                    "completed": False,
                    "hint": "higher" if guess < secret else "lower",
                    "attempts": state["attempts"],
                }
            score = max(20, 120 - state["attempts"] * 10)
            return _complete_game(
                cursor, user_id, session_id, game_key, score,
                "%d tentative%s" % (state["attempts"], "" if state["attempts"] == 1 else "s"),
                {"attempts": state["attempts"], "number": secret, "elapsed_ms": elapsed_ms},
                won=True,
            )

        if game_key == "quiz":
            answers = payload.get("answers") or []
            questions = state.get("questions") or []
            if len(answers) != len(questions):
                raise ValueError("Réponds à toutes les questions.")
            correct = 0
            for index, item in enumerate(questions):
                try:
                    if int(answers[index]) == int(item["answer"]):
                        correct += 1
                except Exception:
                    pass
            speed_bonus = max(0, 75 - elapsed_ms // 1000)
            score = correct * 100 + speed_bonus
            return _complete_game(
                cursor, user_id, session_id, game_key, score,
                "%d/5 bonnes réponses" % correct,
                {"correct": correct, "total": 5, "elapsed_ms": elapsed_ms},
                won=correct >= 4,
            )

        if game_key == "memory":
            moves = int(payload.get("moves") or 0)
            client_elapsed = int(payload.get("elapsed_ms") or elapsed_ms)
            effective_elapsed = max(elapsed_ms, min(client_elapsed, 300000))
            if moves < 6 or moves > 200:
                raise ValueError("Nombre de coups invalide.")
            if effective_elapsed < 1500:
                raise ValueError("Partie terminée trop rapidement pour être validée.")
            score = max(50, 1700 - moves * 65 - effective_elapsed // 120)
            return _complete_game(
                cursor, user_id, session_id, game_key, score,
                "%d coups · %.1f s" % (moves, effective_elapsed / 1000.0),
                {"moves": moves, "elapsed_ms": effective_elapsed},
                won=True,
            )

        if game_key == "reflex":
            wait_ms = int(state.get("wait_ms") or 1800)
            if elapsed_ms < wait_ms:
                cursor.execute("UPDATE arcade_sessions SET completed_at=datetime('now') WHERE id=?", (session_id,))
                return {"completed": True, "failed": True, "result_label": "Trop tôt !", "score": 0, "details": {"early": True}}
            reaction_ms = elapsed_ms - wait_ms
            if reaction_ms > 5000:
                raise ValueError("Réaction trop tardive. Relance une partie.")
            score = max(10, 1500 - reaction_ms)
            return _complete_game(
                cursor, user_id, session_id, game_key, score,
                "%d ms" % reaction_ms,
                {"reaction_ms": reaction_ms},
                won=reaction_ms < 500,
            )

        if game_key == "clicker":
            clicks = int(payload.get("clicks") or 0)
            if elapsed_ms < 9200:
                raise ValueError("La manche de dix secondes n'est pas terminée.")
            if elapsed_ms > 30000:
                raise ValueError("Cette manche a expiré.")
            if clicks < 0 or clicks > 200:
                raise ValueError("Score de clics invalide.")
            return _complete_game(
                cursor, user_id, session_id, game_key, clicks,
                "%d clics" % clicks,
                {"clicks": clicks, "elapsed_ms": elapsed_ms},
                won=clicks >= 40,
            )

        if game_key == "tictactoe":
            cell = payload.get("cell")
            if cell is None:
                raise ValueError("Choisis une case.")
            cell = int(cell)
            board = list(state.get("board") or [""] * 9)
            if state.get("status") != "active":
                raise ValueError("Cette partie est terminée.")
            if cell < 0 or cell > 8 or board[cell]:
                raise ValueError("Cette case est déjà utilisée.")
            board[cell] = "X"
            result = _winner(board)
            if not result:
                _bot_move(board)
                result = _winner(board)
            state["board"] = board
            if not result:
                cursor.execute("UPDATE arcade_sessions SET state_json=? WHERE id=?", (json.dumps(state), session_id))
                return {"completed": False, "board": board, "status": "active"}
            outcome = "draw"
            score = 120
            label = "Match nul"
            won = False
            if result == "X":
                outcome, score, label, won = "win", 300, "Victoire contre PiBot", True
            elif result == "O":
                outcome, score, label = "loss", 30, "PiBot gagne"
            state["status"] = outcome
            cursor.execute("UPDATE arcade_sessions SET state_json=? WHERE id=?", (json.dumps(state), session_id))
            completed = _complete_game(
                cursor, user_id, session_id, game_key, score, label,
                {"outcome": outcome, "board": board, "elapsed_ms": elapsed_ms},
                won=won,
            )
            completed["board"] = board
            completed["status"] = outcome
            return completed

        raise ValueError("Mini-jeu inconnu.")


def dashboard(user_id: int, leaderboard_game: Optional[str] = None) -> Dict[str, Any]:
    game_key = leaderboard_game if leaderboard_game in CATALOG_BY_KEY else "clicker"
    challenge = _daily_challenge()
    settings = get_arcade_settings()
    with get_db_cursor() as cursor:
        stats_rows = cursor.execute(
            """SELECT game_key,best_score,best_label,plays,wins,updated_at
               FROM arcade_user_stats WHERE user_id=?""",
            (user_id,),
        ).fetchall()
        recent_rows = cursor.execute(
            """SELECT game_key,score,result_label,coins_awarded,xp_awarded,created_at
               FROM arcade_scores WHERE user_id=? ORDER BY id DESC LIMIT 12""",
            (user_id,),
        ).fetchall()
        leaderboard_rows = cursor.execute(
            """SELECT s.user_id,u.username,s.best_score,s.best_label,u.profile_color
               FROM arcade_user_stats s JOIN users u ON u.id=s.user_id
               WHERE s.game_key=? AND u.is_bot=0 AND u.is_banned=0
               ORDER BY s.best_score DESC,s.updated_at ASC LIMIT 20""",
            (game_key,),
        ).fetchall()
        claim = cursor.execute(
            "SELECT score FROM arcade_daily_claims WHERE user_id=? AND challenge_date=?",
            (user_id, challenge["date"]),
        ).fetchone()
        today_best = cursor.execute(
            """SELECT MAX(score) AS score FROM arcade_scores
               WHERE user_id=? AND game_key=? AND date(created_at)=?""",
            (user_id, challenge["game_key"], challenge["date"]),
        ).fetchone()
        total = cursor.execute(
            "SELECT COUNT(*) AS plays,COALESCE(SUM(coins_awarded),0) AS coins FROM arcade_scores WHERE user_id=?",
            (user_id,),
        ).fetchone()
        user = cursor.execute("SELECT coins,xp FROM users WHERE id=?", (user_id,)).fetchone()

    stats_map = {row["game_key"]: dict(row) for row in stats_rows}
    stats = []
    for game in ARCADE_CATALOG:
        row = stats_map.get(game["key"], {})
        stats.append({
            "game_key": game["key"],
            "name": game["name"],
            "icon": game["icon"],
            "best_score": int(row.get("best_score") or 0),
            "best_label": row.get("best_label") or "Aucune partie",
            "plays": int(row.get("plays") or 0),
            "wins": int(row.get("wins") or 0),
        })
    challenge.update({
        "completed": bool(claim),
        "claimed_score": int(claim["score"]) if claim else None,
        "today_best": int(today_best["score"] or 0) if today_best else 0,
        "reward_coins": settings["daily_challenge_coins"],
        "reward_xp": settings["daily_challenge_xp"],
    })
    return {
        "catalog": [dict(item) for item in ARCADE_CATALOG],
        "settings": settings,
        "stats": stats,
        "recent": [dict(row) for row in recent_rows],
        "leaderboard_game": game_key,
        "leaderboard": [dict(row) for row in leaderboard_rows],
        "daily_challenge": challenge,
        "summary": {
            "plays": int(total["plays"] or 0),
            "coins_earned": int(total["coins"] or 0),
            "wallet": int(user["coins"] or 0) if user else 0,
            "xp": int(user["xp"] or 0) if user else 0,
        },
    }


def admin_overview() -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        totals = cursor.execute(
            """SELECT COUNT(*) AS plays,COUNT(DISTINCT user_id) AS players,
                      COALESCE(SUM(coins_awarded),0) AS coins,COALESCE(SUM(xp_awarded),0) AS xp
               FROM arcade_scores"""
        ).fetchone()
        popular = cursor.execute(
            """SELECT game_key,COUNT(*) AS plays FROM arcade_scores
               GROUP BY game_key ORDER BY plays DESC"""
        ).fetchall()
        recent = cursor.execute(
            """SELECT a.game_key,a.score,a.result_label,a.coins_awarded,a.created_at,u.username
               FROM arcade_scores a JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 30"""
        ).fetchall()
    return {
        "settings": get_arcade_settings(),
        "totals": dict(totals),
        "popular": [dict(row) for row in popular],
        "recent": [dict(row) for row in recent],
    }
