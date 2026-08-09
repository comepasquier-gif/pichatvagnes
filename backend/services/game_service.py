from __future__ import annotations
import json, random, re, secrets
from database import get_db_cursor
from security import hash_password
from services.message_service import save_message, update_message_card
from services.room_service import user_can_access_room

GAME_BOT = "PiGame"


def ensure_game_bot():
    with get_db_cursor() as c:
        c.execute("SELECT id FROM users WHERE username=?", (GAME_BOT,))
        row = c.fetchone()
        if row:
            return row["id"]
        c.execute(
            "INSERT INTO users (username,password_hash,is_bot,status_message,grade_title,grade_color,grade_visibility,profile_color) VALUES (?,?,1,?,?,?,?,?)",
            (GAME_BOT, hash_password(secrets.token_urlsafe(32)), "Mini-jeux PiChat", "GAME", "#f0b232", "full", "#f0b232"),
        )
        return c.lastrowid


def feature_settings():
    with get_db_cursor() as c:
        row = c.execute("SELECT games_enabled,tutor_enabled,reactions_enabled,reports_enabled,member_panel FROM feature_settings WHERE id=1").fetchone()
    if not row:
        return {"games_enabled": True, "tutor_enabled": True, "reactions_enabled": True, "reports_enabled": True, "member_panel": True}
    return {k: bool(row[k]) for k in row.keys()}


def _username(user_id):
    with get_db_cursor() as c:
        row = c.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    return row["username"] if row else "?"


def get_profile(user_id):
    with get_db_cursor() as c:
        row = c.execute("SELECT id,username,xp,coins,game_wins,game_losses,profile_color FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    xp = int(row["xp"] or 0)
    return {"id": row["id"], "username": row["username"], "xp": xp, "level": 1 + xp // 100, "coins": int(row["coins"] or 0), "wins": int(row["game_wins"] or 0), "losses": int(row["game_losses"] or 0), "profile_color": row["profile_color"] or "#5865f2"}


def award_message_xp(user_id, amount=2):
    with get_db_cursor() as c:
        c.execute("UPDATE users SET xp=xp+? WHERE id=? AND is_bot=0", (max(0, min(amount, 5)), user_id))


def _find_user_for_room(room_id, username):
    with get_db_cursor() as c:
        row = c.execute("SELECT id,username,is_admin,is_moderator,moderator_class_code,class_code,is_bot,is_banned FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()
    if not row or row["is_bot"] or row["is_banned"]:
        return None
    user = dict(row)
    return user if user_can_access_room(user, room_id) else None


def _game_message(room_id, text, kind, metadata):
    return save_message(room_id, ensure_game_bot(), text, message_type=kind, metadata=metadata)


def handle_game_command(room_id, sender, content):
    """Retourne None si ce n'est pas une commande jeu, sinon un message carte."""
    raw = content.strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split()
    cmd = parts[0].lower()
    if cmd not in {"/duel", "/roll", "/dice", "/coin", "/rps", "/stats", "/8ball", "/choose", "/poll", "/games"}:
        return None
    if not feature_settings()["games_enabled"]:
        return _game_message(room_id, "Les mini-jeux sont désactivés par l'administration.", "game_notice", {"icon": "🎮"})

    if cmd == "/games":
        return _game_message(room_id, "Commandes : /duel @pseudo · /roll 20 · /coin · /rps pierre · /8ball question · /choose A | B · /poll Question | A | B · /stats", "game_help", {})

    if cmd in {"/roll", "/dice"}:
        sides = 6
        if len(parts) > 1:
            try: sides = max(2, min(1000, int(parts[1])))
            except Exception: pass
        value = random.randint(1, sides)
        return _game_message(room_id, f"{sender['username']} lance un D{sides} : {value}", "dice", {"sides": sides, "value": value, "player": sender["username"]})

    if cmd == "/coin":
        value = random.choice(["Pile", "Face"])
        return _game_message(room_id, f"{sender['username']} lance la pièce : {value}", "coin", {"value": value, "player": sender["username"]})

    if cmd == "/rps":
        choices = {"pierre":"🪨", "feuille":"📄", "ciseaux":"✂️", "rock":"🪨", "paper":"📄", "scissors":"✂️"}
        chosen = parts[1].lower() if len(parts)>1 else ""
        normalized = {"rock":"pierre","paper":"feuille","scissors":"ciseaux"}.get(chosen, chosen)
        if normalized not in {"pierre","feuille","ciseaux"}:
            return _game_message(room_id, "Utilise /rps pierre, /rps feuille ou /rps ciseaux.", "game_notice", {"icon":"✋"})
        bot = random.choice(["pierre","feuille","ciseaux"])
        if normalized == bot: result = "Égalité"
        elif (normalized,bot) in {("pierre","ciseaux"),("feuille","pierre"),("ciseaux","feuille")}: result = "Gagné !"
        else: result = "Perdu !"
        return _game_message(room_id, f"{sender['username']} {choices[normalized]} vs PiGame {choices[bot]} — {result}", "rps", {"player_choice":normalized,"bot_choice":bot,"result":result})

    if cmd == "/8ball":
        answers = ["Oui.", "Très probable.", "Ça se tente.", "Demande plus tard.", "Pas sûr du tout.", "Non.", "Le hamster refuse de répondre."]
        q = raw[len(parts[0]):].strip() or "Question mystère"
        return _game_message(room_id, random.choice(answers), "eightball", {"question":q,"asker":sender["username"]})

    if cmd == "/choose":
        body = raw[len(parts[0]):].strip()
        opts = [x.strip() for x in body.split("|") if x.strip()][:10]
        if len(opts) < 2:
            return _game_message(room_id, "Exemple : /choose pizza | tacos | pâtes", "game_notice", {"icon":"🎯"})
        choice = random.choice(opts)
        return _game_message(room_id, f"PiGame choisit : {choice}", "choice", {"options":opts,"choice":choice})

    if cmd == "/poll":
        body = raw[len(parts[0]):].strip()
        bits = [x.strip() for x in body.split("|") if x.strip()]
        if len(bits) < 3:
            return _game_message(room_id, "Exemple : /poll On mange quoi ? | Pizza | Tacos", "game_notice", {"icon":"📊"})
        question, options = bits[0], bits[1:7]
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣"][:len(options)]
        return _game_message(room_id, question, "poll", {"question":question,"options":options,"emojis":emojis,"creator":sender["username"]})

    if cmd == "/stats":
        profile = get_profile(sender["id"])
        return _game_message(room_id, f"Profil jeu de {sender['username']}", "stats", profile or {})

    if cmd == "/duel":
        m = re.search(r"@([A-Za-z0-9_.-]{2,32})", raw)
        if not m:
            return _game_message(room_id, "Utilise /duel @pseudo", "game_notice", {"icon":"⚔️"})
        opponent = _find_user_for_room(room_id, m.group(1))
        if not opponent:
            return _game_message(room_id, "Joueur introuvable dans ce serveur.", "game_notice", {"icon":"⚔️"})
        if opponent["id"] == sender["id"]:
            return _game_message(room_id, "Impossible de te défier toi-même 😅", "game_notice", {"icon":"⚔️"})
        with get_db_cursor() as c:
            c.execute("INSERT INTO duels (room_id,challenger_id,opponent_id,turn_user_id,status,log_json) VALUES (?,?,?,?, 'pending', ?)", (room_id,sender["id"],opponent["id"],sender["id"],json.dumps([f"{sender['username']} défie {opponent['username']} !"],ensure_ascii=False)))
            duel_id = c.lastrowid
        meta = duel_metadata(duel_id)
        msg = _game_message(room_id, f"⚔️ {sender['username']} défie {opponent['username']} !", "duel", meta)
        with get_db_cursor() as c:
            c.execute("UPDATE duels SET message_id=? WHERE id=?", (msg["id"],duel_id))
        msg["metadata"] = duel_metadata(duel_id)
        return msg


def duel_metadata(duel_id):
    from services.rpg_service import profile as rpg_profile
    with get_db_cursor() as c:
        row = c.execute("SELECT * FROM duels WHERE id=?", (duel_id,)).fetchone()
    if not row:
        return {}
    log = []
    try:
        log = json.loads(row["log_json"] or "[]")
    except Exception:
        pass
    challenger_profile = rpg_profile(row["challenger_id"]) or {}
    opponent_profile = rpg_profile(row["opponent_id"]) or {}
    return {
        "duel_id": row["id"], "status": row["status"],
        "challenger_id": row["challenger_id"], "challenger": _username(row["challenger_id"]),
        "challenger_hp": row["challenger_hp"], "challenger_guard": row["challenger_guard"],
        "challenger_energy": row["challenger_energy"], "challenger_rpg": challenger_profile,
        "opponent_id": row["opponent_id"], "opponent": _username(row["opponent_id"]),
        "opponent_hp": row["opponent_hp"], "opponent_guard": row["opponent_guard"],
        "opponent_energy": row["opponent_energy"], "opponent_rpg": opponent_profile,
        "turn_user_id": row["turn_user_id"], "winner_id": row["winner_id"], "log": log[-8:],
    }


def duel_action(duel_id, actor, action):
    from services.rpg_service import profile as rpg_profile, progress_quest
    action = (action or "").lower()
    with get_db_cursor() as c:
        row = c.execute("SELECT * FROM duels WHERE id=?", (duel_id,)).fetchone()
        if not row:
            raise ValueError("Duel introuvable.")
        d = dict(row)
        players = {d["challenger_id"], d["opponent_id"]}
        if actor["id"] not in players:
            raise PermissionError("Tu ne participes pas à ce duel.")
        logs = []
        try:
            logs = json.loads(d["log_json"] or "[]")
        except Exception:
            pass
        if d["status"] == "pending":
            if action == "accept" and actor["id"] == d["opponent_id"]:
                cp = rpg_profile(d["challenger_id"]) or {"hp": 100}
                op = rpg_profile(d["opponent_id"]) or {"hp": 100}
                d["challenger_hp"] = min(180, max(70, int(cp.get("hp") or 100)))
                d["opponent_hp"] = min(180, max(70, int(op.get("hp") or 100)))
                d["challenger_energy"] = 3
                d["opponent_energy"] = 3
                d["challenger_guard"] = 0
                d["opponent_guard"] = 0
                d["status"] = "active"
                d["turn_user_id"] = d["challenger_id"]
                logs.append(f"{actor['username']} accepte. Combat RPG !")
            elif action == "decline" and actor["id"] == d["opponent_id"]:
                d["status"] = "declined"
                logs.append(f"{actor['username']} refuse le duel.")
            else:
                raise ValueError("Action impossible pour ce duel.")
        elif d["status"] == "active":
            if action == "forfeit":
                winner = d["opponent_id"] if actor["id"] == d["challenger_id"] else d["challenger_id"]
                d["status"] = "finished"
                d["winner_id"] = winner
                logs.append(f"{actor['username']} abandonne.")
            else:
                if actor["id"] != d["turn_user_id"]:
                    raise PermissionError("Ce n'est pas ton tour.")
                actor_is_challenger = actor["id"] == d["challenger_id"]
                target = d["opponent_id"] if actor_is_challenger else d["challenger_id"]
                own_hp = "challenger_hp" if actor_is_challenger else "opponent_hp"
                own_guard = "challenger_guard" if actor_is_challenger else "opponent_guard"
                own_energy = "challenger_energy" if actor_is_challenger else "opponent_energy"
                target_hp = "opponent_hp" if actor_is_challenger else "challenger_hp"
                target_guard = "opponent_guard" if actor_is_challenger else "challenger_guard"
                stats = rpg_profile(actor["id"]) or {"attack": 12, "defense": 6, "agility": 8, "class": "aventurier"}
                damage = 0
                label = ""
                if action == "attack":
                    damage = max(4, int(stats["attack"]) + random.randint(-2, 7))
                    label = "attaque"
                elif action == "risky":
                    damage = max(1, int(stats["attack"] * random.uniform(0.45, 2.15)))
                    label = "attaque risquée"
                elif action == "defend":
                    d[own_guard] = min(30, 5 + int(stats["defense"]))
                    label = f"se met en garde (+{d[own_guard]} protection)"
                elif action == "heal":
                    if d[own_energy] <= 0:
                        raise ValueError("Plus d'énergie spéciale.")
                    d[own_energy] -= 1
                    amount = random.randint(8, 16) + int(stats["defense"] // 2)
                    max_hp = min(180, max(70, int(stats.get("hp") or 100)))
                    d[own_hp] = min(max_hp, d[own_hp] + amount)
                    label = f"récupère {amount} PV"
                elif action == "special":
                    if d[own_energy] <= 0:
                        raise ValueError("Plus d'énergie spéciale.")
                    d[own_energy] -= 1
                    cls = stats.get("class") or "aventurier"
                    if cls == "mage":
                        damage = int(stats["attack"] * 1.7) + random.randint(4, 12)
                        label = "lance une décharge arcanique"
                    elif cls == "gardien":
                        damage = int(stats["attack"] * 1.15) + random.randint(2, 8)
                        d[own_guard] = min(35, d[own_guard] + 10 + int(stats["defense"] // 2))
                        label = "utilise un coup de bouclier"
                    elif cls == "éclaireur":
                        damage = int(stats["attack"] * 1.25) + random.randint(4, 10)
                        if random.random() < 0.35:
                            damage += int(stats["attack"] * 0.65)
                            label = "enchaîne une double flèche"
                        else:
                            label = "tire une flèche précise"
                    else:
                        damage = int(stats["attack"] * 1.4) + random.randint(3, 9)
                        label = "utilise une technique héroïque"
                else:
                    raise ValueError("Action inconnue.")
                if damage:
                    absorbed = min(int(d[target_guard] or 0), damage)
                    d[target_guard] = 0
                    damage = max(0, damage - absorbed)
                    d[target_hp] = max(0, int(d[target_hp]) - damage)
                    label += f" (-{damage} PV"
                    if absorbed:
                        label += f", {absorbed} bloqués"
                    label += ")"
                logs.append(f"{actor['username']} {label}.")
                if int(d[target_hp]) <= 0:
                    d["status"] = "finished"
                    d["winner_id"] = actor["id"]
                    logs.append(f"🏆 {_username(actor['id'])} remporte le duel !")
                else:
                    d["turn_user_id"] = target
        c.execute(
            """UPDATE duels SET challenger_hp=?,opponent_hp=?,challenger_guard=?,opponent_guard=?,
                      challenger_energy=?,opponent_energy=?,turn_user_id=?,status=?,winner_id=?,log_json=?,updated_at=datetime('now')
               WHERE id=?""",
            (d["challenger_hp"], d["opponent_hp"], d["challenger_guard"], d["opponent_guard"],
             d["challenger_energy"], d["opponent_energy"], d["turn_user_id"], d["status"],
             d.get("winner_id"), json.dumps(logs, ensure_ascii=False), duel_id),
        )
        quest_users = []
        if d["status"] == "finished" and d.get("winner_id"):
            loser = d["opponent_id"] if d["winner_id"] == d["challenger_id"] else d["challenger_id"]
            c.execute("UPDATE users SET xp=xp+45,rpg_xp=rpg_xp+45,coins=coins+25,game_wins=game_wins+1 WHERE id=?", (d["winner_id"],))
            c.execute("UPDATE users SET xp=xp+12,rpg_xp=rpg_xp+12,game_losses=game_losses+1 WHERE id=?", (loser,))
            quest_users = [d["winner_id"], loser]
        message_id = d["message_id"]
    for quest_user_id in quest_users:
        progress_quest(quest_user_id, "duels", 1)
    meta = duel_metadata(duel_id)
    msg = update_message_card(message_id, metadata=meta) if message_id else None
    return msg, meta

