from __future__ import annotations

from datetime import datetime, timezone

from database import get_db_cursor


class PyCoinError(Exception):
    pass


DEFAULT_ECONOMY_SETTINGS = {
    "daily_reward": 25,
    "transfer_max": 500,
    "transfers_enabled": True,
    "server_creation_cost": 100,
    "server_customization_cost": 10,
    "code_cost": 5,
    "max_owned_servers": 3,
}


def get_economy_settings() -> dict:
    with get_db_cursor() as cursor:
        row = cursor.execute("SELECT * FROM economy_settings WHERE id=1").fetchone()
    if row is None:
        return dict(DEFAULT_ECONOMY_SETTINGS)
    return {
        "daily_reward": int(row["daily_reward"]),
        "transfer_max": int(row["transfer_max"]),
        "transfers_enabled": bool(row["transfers_enabled"]),
        "server_creation_cost": int(row["server_creation_cost"]),
        "server_customization_cost": int(row["server_customization_cost"]),
        "code_cost": int(row["code_cost"]),
        "max_owned_servers": int(row["max_owned_servers"]),
    }


def update_economy_settings(data: dict) -> dict:
    current = get_economy_settings()
    values = dict(current)
    limits = {
        "daily_reward": (0, 100_000),
        "transfer_max": (1, 100_000),
        "server_creation_cost": (0, 1_000_000),
        "server_customization_cost": (0, 1_000_000),
        "code_cost": (0, 100_000),
        "max_owned_servers": (1, 20),
    }
    for key, (minimum, maximum) in limits.items():
        if key in data and data[key] is not None:
            value = int(data[key])
            if value < minimum or value > maximum:
                raise PyCoinError(f"Valeur invalide pour {key} : {minimum} à {maximum}.")
            values[key] = value
    if "transfers_enabled" in data and data["transfers_enabled"] is not None:
        values["transfers_enabled"] = bool(data["transfers_enabled"])
    with get_db_cursor() as cursor:
        cursor.execute(
            """UPDATE economy_settings SET daily_reward=?,transfer_max=?,transfers_enabled=?,
                      server_creation_cost=?,server_customization_cost=?,code_cost=?,max_owned_servers=?,
                      updated_at=datetime('now') WHERE id=1""",
            (
                values["daily_reward"], values["transfer_max"], 1 if values["transfers_enabled"] else 0,
                values["server_creation_cost"], values["server_customization_cost"],
                values["code_cost"], values["max_owned_servers"],
            ),
        )
    return get_economy_settings()


def _row_balance(cursor, user_id: int) -> int:
    row = cursor.execute("SELECT coins FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise PyCoinError("Compte introuvable.")
    return int(row["coins"] or 0)


def _record(cursor, user_id: int, amount: int, kind: str, details: str = "", related_user_id=None) -> int:
    balance = _row_balance(cursor, user_id)
    cursor.execute(
        """INSERT INTO pycoin_transactions
           (user_id,amount,balance_after,kind,details,related_user_id)
           VALUES (?,?,?,?,?,?)""",
        (user_id, int(amount), balance, kind[:40], (details or "")[:240], related_user_id),
    )
    return balance


def get_wallet(user_id: int) -> dict:
    with get_db_cursor() as cursor:
        balance = _row_balance(cursor, user_id)
        rows = cursor.execute(
            """SELECT id,amount,balance_after,kind,details,related_user_id,created_at
               FROM pycoin_transactions WHERE user_id=? ORDER BY id DESC LIMIT 50""",
            (user_id,),
        ).fetchall()
        reward = cursor.execute(
            "SELECT last_claim_date FROM daily_pycoin_rewards WHERE user_id=?",
            (user_id,),
        ).fetchone()
    today = datetime.now(timezone.utc).date().isoformat()
    settings = get_economy_settings()
    return {
        "balance": balance,
        "daily_available": reward is None or reward["last_claim_date"] != today,
        "daily_reward": settings["daily_reward"],
        "transfer_max": settings["transfer_max"],
        "transfers_enabled": settings["transfers_enabled"],
        "transactions": [dict(row) for row in rows],
    }


def credit(user_id: int, amount: int, kind: str, details: str = "", related_user_id=None) -> int:
    amount = int(amount)
    if amount <= 0:
        raise PyCoinError("Le crédit doit être positif.")
    with get_db_cursor() as cursor:
        cursor.execute("UPDATE users SET coins=coins+? WHERE id=?", (amount, user_id))
        if cursor.rowcount == 0:
            raise PyCoinError("Compte introuvable.")
        return _record(cursor, user_id, amount, kind, details, related_user_id)


def debit(user_id: int, amount: int, kind: str, details: str = "", related_user_id=None) -> int:
    amount = int(amount)
    if amount <= 0:
        raise PyCoinError("Le débit doit être positif.")
    with get_db_cursor() as cursor:
        balance = _row_balance(cursor, user_id)
        if balance < amount:
            raise PyCoinError(f"PyCoins insuffisants : {balance} disponibles, {amount} nécessaires.")
        cursor.execute("UPDATE users SET coins=coins-? WHERE id=?", (amount, user_id))
        return _record(cursor, user_id, -amount, kind, details, related_user_id)


def claim_daily(user_id: int, reward: int = None) -> dict:
    settings = get_economy_settings()
    reward = settings["daily_reward"] if reward is None else int(reward)
    if reward <= 0:
        raise PyCoinError("Le bonus quotidien est désactivé.")
    today = datetime.now(timezone.utc).date().isoformat()
    with get_db_cursor() as cursor:
        row = cursor.execute(
            "SELECT last_claim_date FROM daily_pycoin_rewards WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row is not None and row["last_claim_date"] == today:
            raise PyCoinError("Le bonus quotidien a déjà été récupéré aujourd'hui.")
        cursor.execute("UPDATE users SET coins=coins+? WHERE id=?", (reward, user_id))
        if cursor.rowcount == 0:
            raise PyCoinError("Compte introuvable.")
        cursor.execute(
            """INSERT INTO daily_pycoin_rewards (user_id,last_claim_date)
               VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET last_claim_date=excluded.last_claim_date""",
            (user_id, today),
        )
        balance = _record(cursor, user_id, reward, "daily_reward", "Bonus quotidien")
    return {"reward": reward, "balance": balance, "daily_available": False}


def transfer(sender_id: int, recipient_username: str, amount: int) -> dict:
    settings = get_economy_settings()
    if not settings["transfers_enabled"]:
        raise PyCoinError("Les transferts de PyCoins sont désactivés.")
    amount = int(amount)
    if amount < 1 or amount > settings["transfer_max"]:
        raise PyCoinError(f"Le transfert doit être compris entre 1 et {settings['transfer_max']} PyCoins.")
    username = (recipient_username or "").strip()
    with get_db_cursor() as cursor:
        recipient = cursor.execute(
            "SELECT id,username,is_bot FROM users WHERE username=? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if recipient is None or bool(recipient["is_bot"]):
            raise PyCoinError("Destinataire introuvable.")
        if int(recipient["id"]) == int(sender_id):
            raise PyCoinError("Tu ne peux pas t'envoyer des PyCoins à toi-même.")
        balance = _row_balance(cursor, sender_id)
        if balance < amount:
            raise PyCoinError("Tu n'as pas assez de PyCoins.")
        cursor.execute("UPDATE users SET coins=coins-? WHERE id=?", (amount, sender_id))
        sender_balance = _record(
            cursor, sender_id, -amount, "transfer_sent",
            f"Transfert à {recipient['username']}", int(recipient["id"]),
        )
        cursor.execute("UPDATE users SET coins=coins+? WHERE id=?", (amount, int(recipient["id"])))
        recipient_balance = _record(
            cursor, int(recipient["id"]), amount, "transfer_received",
            "Transfert reçu", sender_id,
        )
    return {
        "amount": amount,
        "recipient": recipient["username"],
        "balance": sender_balance,
        "recipient_balance": recipient_balance,
    }


def redeem_promo(user_id: int, code: str) -> dict:
    clean = "".join(ch for ch in (code or "").upper().strip() if ch.isalnum() or ch in "_-")[:24]
    if not clean:
        raise PyCoinError("Code promo manquant.")
    with get_db_cursor() as cursor:
        promo = cursor.execute("SELECT * FROM pycoin_promo_codes WHERE code=?", (clean,)).fetchone()
        if promo is None or not bool(promo["active"]):
            raise PyCoinError("Code promo invalide ou désactivé.")
        if int(promo["uses"] or 0) >= int(promo["max_uses"]):
            raise PyCoinError("Ce code promo a atteint sa limite d'utilisation.")
        if promo["expires_at"]:
            row = cursor.execute("SELECT datetime(?) < datetime('now') AS expired", (promo["expires_at"],)).fetchone()
            if bool(row["expired"]):
                raise PyCoinError("Ce code promo a expiré.")
        used = cursor.execute(
            "SELECT 1 FROM pycoin_promo_redemptions WHERE promo_id=? AND user_id=?",
            (int(promo["id"]), int(user_id)),
        ).fetchone()
        if used:
            raise PyCoinError("Tu as déjà utilisé ce code promo.")
        amount = int(promo["amount"])
        cursor.execute("UPDATE users SET coins=coins+? WHERE id=?", (amount, int(user_id)))
        if cursor.rowcount == 0:
            raise PyCoinError("Compte introuvable.")
        balance = _row_balance(cursor, int(user_id))
        cursor.execute(
            "INSERT INTO pycoin_promo_redemptions (promo_id,user_id) VALUES (?,?)",
            (int(promo["id"]), int(user_id)),
        )
        cursor.execute("UPDATE pycoin_promo_codes SET uses=uses+1 WHERE id=?", (int(promo["id"]),))
        cursor.execute(
            """INSERT INTO pycoin_transactions
               (user_id,amount,balance_after,kind,details)
               VALUES (?,?,?,?,?)""",
            (int(user_id), amount, balance, "promo_code", f"Code promo {clean}"),
        )
    return {"code": clean, "reward": amount, "balance": balance}
