from __future__ import annotations

import random
from datetime import datetime, timezone
from database import get_db_cursor

CLASS_STATS = {
    "aventurier": {"hp": 100, "attack": 12, "defense": 6, "agility": 8, "icon": "🧭", "description": "Équilibré et polyvalent."},
    "mage": {"hp": 82, "attack": 18, "defense": 4, "agility": 9, "icon": "🪄", "description": "Fortes attaques, moins résistant."},
    "gardien": {"hp": 125, "attack": 9, "defense": 11, "agility": 5, "icon": "🛡️", "description": "Très solide et protecteur."},
    "éclaireur": {"hp": 92, "attack": 13, "defense": 5, "agility": 14, "icon": "🏹", "description": "Rapide, agile et imprévisible."},
}


def _normalize_class(value: str):
    value = (value or "aventurier").strip().lower()
    if value == "eclaireur":
        value = "éclaireur"
    return value if value in CLASS_STATS else "aventurier"


def ensure_profile(user_id: int):
    with get_db_cursor() as c:
        row = c.execute(
            """SELECT id,rpg_class,rpg_level,rpg_xp,rpg_energy,rpg_hp,rpg_attack,rpg_defense,rpg_agility,
                      coins,username,profile_color FROM users WHERE id=?""",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        cls = _normalize_class(row["rpg_class"])
        if not row["rpg_class"]:
            base = CLASS_STATS[cls]
            c.execute(
                "UPDATE users SET rpg_class=?,rpg_hp=?,rpg_attack=?,rpg_defense=?,rpg_agility=? WHERE id=?",
                (cls, base["hp"], base["attack"], base["defense"], base["agility"], user_id),
            )
            row = c.execute(
                """SELECT id,rpg_class,rpg_level,rpg_xp,rpg_energy,rpg_hp,rpg_attack,rpg_defense,rpg_agility,
                          coins,username,profile_color FROM users WHERE id=?""",
                (user_id,),
            ).fetchone()
    return dict(row)


def equipped_bonuses(user_id: int):
    with get_db_cursor() as c:
        rows = c.execute(
            """SELECT i.stat_key,SUM(i.stat_value) AS value FROM rpg_inventory inv
               JOIN rpg_items i ON i.id=inv.item_id
               WHERE inv.user_id=? AND inv.equipped=1 GROUP BY i.stat_key""",
            (user_id,),
        ).fetchall()
    return {r["stat_key"]: int(r["value"] or 0) for r in rows if r["stat_key"]}


def profile(user_id: int):
    row = ensure_profile(user_id)
    if not row:
        return None
    bonuses = equipped_bonuses(user_id)
    xp = int(row.get("rpg_xp") or 0)
    level = max(int(row.get("rpg_level") or 1), 1 + xp // 120)
    if level != int(row.get("rpg_level") or 1):
        with get_db_cursor() as c:
            c.execute("UPDATE users SET rpg_level=? WHERE id=?", (level, user_id))
    cls = _normalize_class(row.get("rpg_class"))
    return {
        "user_id": user_id,
        "username": row["username"],
        "class": cls,
        "class_icon": CLASS_STATS[cls]["icon"],
        "class_description": CLASS_STATS[cls]["description"],
        "level": level,
        "xp": xp,
        "next_level_xp": level * 120,
        "energy": int(row.get("rpg_energy") or 0),
        "hp": int(row.get("rpg_hp") or 100) + bonuses.get("hp", 0),
        "attack": int(row.get("rpg_attack") or 12) + bonuses.get("attack", 0),
        "defense": int(row.get("rpg_defense") or 6) + bonuses.get("defense", 0),
        "agility": int(row.get("rpg_agility") or 8) + bonuses.get("agility", 0),
        "coins": int(row.get("coins") or 0),
        "profile_color": row.get("profile_color") or "#5865f2",
        "bonuses": bonuses,
    }


def choose_class(user_id: int, value: str):
    cls = _normalize_class(value)
    base = CLASS_STATS[cls]
    with get_db_cursor() as c:
        c.execute(
            """UPDATE users SET rpg_class=?,rpg_hp=?,rpg_attack=?,rpg_defense=?,rpg_agility=? WHERE id=?""",
            (cls, base["hp"], base["attack"], base["defense"], base["agility"], user_id),
        )
    return profile(user_id)


def shop():
    with get_db_cursor() as c:
        rows = c.execute(
            "SELECT code,name,description,item_type,rarity,stat_key,stat_value,price,icon FROM rpg_items WHERE active=1 ORDER BY price,id"
        ).fetchall()
    return [dict(r) for r in rows]


def inventory(user_id: int):
    with get_db_cursor() as c:
        rows = c.execute(
            """SELECT i.code,i.name,i.description,i.item_type,i.rarity,i.stat_key,i.stat_value,i.price,i.icon,
                      inv.quantity,inv.equipped
               FROM rpg_inventory inv JOIN rpg_items i ON i.id=inv.item_id
               WHERE inv.user_id=? AND inv.quantity>0 ORDER BY inv.equipped DESC,i.rarity,i.name""",
            (user_id,),
        ).fetchall()
    return [dict(r) | {"equipped": bool(r["equipped"])} for r in rows]


def buy_item(user_id: int, code: str):
    with get_db_cursor() as c:
        item = c.execute("SELECT * FROM rpg_items WHERE code=? AND active=1", (code,)).fetchone()
        user = c.execute("SELECT coins FROM users WHERE id=?", (user_id,)).fetchone()
        if not item:
            raise ValueError("Objet introuvable.")
        if not user or int(user["coins"] or 0) < int(item["price"]):
            raise ValueError("Pas assez de PyCoins.")
        c.execute("UPDATE users SET coins=coins-? WHERE id=?", (item["price"], user_id))
        c.execute(
            """INSERT INTO rpg_inventory(user_id,item_id,quantity) VALUES(?,?,1)
               ON CONFLICT(user_id,item_id) DO UPDATE SET quantity=quantity+1""",
            (user_id, item["id"]),
        )
        c.execute(
            "INSERT INTO pycoin_transactions(user_id,amount,transaction_type,description) VALUES(?,?,'rpg_purchase',?)",
            (user_id, -int(item["price"]), f"Achat RPG : {item['name']}"),
        )
    return {"purchased": item["code"], "profile": profile(user_id), "inventory": inventory(user_id)}


def equip_item(user_id: int, code: str):
    with get_db_cursor() as c:
        row = c.execute(
            """SELECT i.id,i.item_type,i.stat_key,inv.quantity,inv.equipped FROM rpg_inventory inv
               JOIN rpg_items i ON i.id=inv.item_id WHERE inv.user_id=? AND i.code=?""",
            (user_id, code),
        ).fetchone()
        if not row or int(row["quantity"] or 0) <= 0:
            raise ValueError("Objet absent de l'inventaire.")
        if row["item_type"] != "equipment":
            raise ValueError("Cet objet ne peut pas être équipé.")
        next_value = 0 if row["equipped"] else 1
        if next_value:
            c.execute(
                """UPDATE rpg_inventory SET equipped=0 WHERE user_id=? AND item_id IN
                   (SELECT id FROM rpg_items WHERE stat_key=?)""",
                (user_id, row["stat_key"]),
            )
        c.execute("UPDATE rpg_inventory SET equipped=? WHERE user_id=? AND item_id=?", (next_value, user_id, row["id"]))
    return {"equipped": bool(next_value), "profile": profile(user_id), "inventory": inventory(user_id)}


def use_item(user_id: int, code: str):
    with get_db_cursor() as c:
        row = c.execute(
            """SELECT i.id,i.item_type,i.stat_key,i.stat_value,inv.quantity FROM rpg_inventory inv
               JOIN rpg_items i ON i.id=inv.item_id WHERE inv.user_id=? AND i.code=?""",
            (user_id, code),
        ).fetchone()
        if not row or int(row["quantity"] or 0) <= 0:
            raise ValueError("Objet absent de l'inventaire.")
        if row["item_type"] != "consumable":
            raise ValueError("Cet objet doit être équipé, pas consommé.")
        if row["stat_key"] == "hp":
            c.execute("UPDATE users SET rpg_hp=MIN(200,rpg_hp+?) WHERE id=?", (row["stat_value"], user_id))
        elif row["stat_key"] == "energy":
            c.execute("UPDATE users SET rpg_energy=MIN(100,rpg_energy+?) WHERE id=?", (row["stat_value"], user_id))
        c.execute("UPDATE rpg_inventory SET quantity=quantity-1 WHERE user_id=? AND item_id=?", (user_id, row["id"]))
    return {"used": code, "profile": profile(user_id), "inventory": inventory(user_id)}


def progress_quest(user_id: int, objective: str, amount: int = 1):
    with get_db_cursor() as c:
        quests = c.execute("SELECT id,target FROM rpg_quests WHERE active=1 AND objective=?", (objective,)).fetchall()
        for quest in quests:
            c.execute(
                """INSERT INTO rpg_quest_progress(user_id,quest_id,progress) VALUES(?,?,?)
                   ON CONFLICT(user_id,quest_id) DO UPDATE SET progress=MIN(?,progress+?)""",
                (user_id, quest["id"], min(amount, int(quest["target"])), int(quest["target"]), amount),
            )
            c.execute(
                """UPDATE rpg_quest_progress SET completed_at=COALESCE(completed_at,datetime('now'))
                   WHERE user_id=? AND quest_id=? AND progress>=?""",
                (user_id, quest["id"], quest["target"]),
            )


def quests(user_id: int):
    with get_db_cursor() as c:
        rows = c.execute(
            """SELECT q.id,q.title,q.description,q.objective,q.target,q.reward_xp,q.reward_coins,q.icon,
                      COALESCE(p.progress,0) AS progress,p.completed_at,p.claimed_at
               FROM rpg_quests q LEFT JOIN rpg_quest_progress p ON p.quest_id=q.id AND p.user_id=?
               WHERE q.active=1 ORDER BY q.id""",
            (user_id,),
        ).fetchall()
    return [dict(r) | {"completed": bool(r["completed_at"]), "claimed": bool(r["claimed_at"])} for r in rows]


def claim_quest(user_id: int, quest_id: int):
    with get_db_cursor() as c:
        row = c.execute(
            """SELECT q.reward_xp,q.reward_coins,q.target,p.progress,p.completed_at,p.claimed_at
               FROM rpg_quests q JOIN rpg_quest_progress p ON p.quest_id=q.id
               WHERE q.id=? AND p.user_id=?""",
            (quest_id, user_id),
        ).fetchone()
        if not row or int(row["progress"] or 0) < int(row["target"]):
            raise ValueError("Quête non terminée.")
        if row["claimed_at"]:
            raise ValueError("Récompense déjà récupérée.")
        c.execute("UPDATE rpg_quest_progress SET claimed_at=datetime('now') WHERE user_id=? AND quest_id=?", (user_id, quest_id))
        c.execute("UPDATE users SET rpg_xp=rpg_xp+?,coins=coins+? WHERE id=?", (row["reward_xp"], row["reward_coins"], user_id))
    return {"claimed": True, "profile": profile(user_id)}


def daily_reward(user_id: int):
    today = datetime.now(timezone.utc).date().isoformat()
    with get_db_cursor() as c:
        row = c.execute("SELECT rpg_last_daily FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise ValueError("Compte introuvable.")
        if (row["rpg_last_daily"] or "").startswith(today):
            raise ValueError("Bonus RPG déjà récupéré aujourd'hui.")
        reward = random.randint(18, 35)
        c.execute("UPDATE users SET rpg_last_daily=?,coins=coins+?,rpg_energy=100 WHERE id=?", (today, reward, user_id))
    return {"reward_coins": reward, "profile": profile(user_id)}


def active_boss():
    with get_db_cursor() as c:
        row = c.execute("SELECT * FROM rpg_world_bosses WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        top = c.execute(
            """SELECT u.username,SUM(a.damage) AS damage FROM rpg_boss_attacks a JOIN users u ON u.id=a.user_id
               WHERE a.boss_id=? GROUP BY a.user_id ORDER BY damage DESC LIMIT 10""",
            (row["id"],),
        ).fetchall()
    result = dict(row)
    result["leaderboard"] = [dict(r) for r in top]
    return result


def attack_boss(user_id: int, style: str = "normal"):
    p = profile(user_id)
    if not p:
        raise ValueError("Profil introuvable.")
    costs = {"normal": 10, "power": 20, "careful": 8}
    cost = costs.get(style, 10)
    if p["energy"] < cost:
        raise ValueError("Pas assez d'énergie RPG.")
    with get_db_cursor() as c:
        boss = c.execute("SELECT * FROM rpg_world_bosses WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        if not boss:
            raise ValueError("Aucun boss actif.")
        base = p["attack"] + random.randint(1, max(2, p["agility"] // 2))
        if style == "power":
            base = int(base * 1.55)
        elif style == "careful":
            base = int(base * 0.85) + p["defense"] // 2
        damage = max(1, base)
        next_hp = max(0, int(boss["current_hp"]) - damage)
        c.execute("UPDATE users SET rpg_energy=rpg_energy-? WHERE id=?", (cost, user_id))
        c.execute("UPDATE rpg_world_bosses SET current_hp=? WHERE id=?", (next_hp, boss["id"]))
        c.execute("INSERT INTO rpg_boss_attacks(boss_id,user_id,damage) VALUES(?,?,?)", (boss["id"], user_id, damage))
        defeated = next_hp <= 0
        if defeated:
            c.execute("UPDATE rpg_world_bosses SET status='defeated',defeated_at=datetime('now') WHERE id=?", (boss["id"],))
            contributors = c.execute("SELECT DISTINCT user_id FROM rpg_boss_attacks WHERE boss_id=?", (boss["id"],)).fetchall()
            share_coins = max(10, int(boss["reward_coins"]) // max(1, len(contributors)))
            share_xp = max(20, int(boss["reward_xp"]) // max(1, len(contributors)))
            for contributor in contributors:
                c.execute("UPDATE users SET coins=coins+?,rpg_xp=rpg_xp+? WHERE id=?", (share_coins, share_xp, contributor["user_id"]))
    return {"damage": damage, "defeated": defeated, "boss": active_boss(), "profile": profile(user_id)}


def leaderboard(limit=50):
    with get_db_cursor() as c:
        rows = c.execute(
            """SELECT id,username,rpg_class,rpg_level,rpg_xp,game_wins,profile_color
               FROM users WHERE is_bot=0 AND is_banned=0
               ORDER BY rpg_level DESC,rpg_xp DESC,game_wins DESC LIMIT ?""",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    return [dict(r) for r in rows]
