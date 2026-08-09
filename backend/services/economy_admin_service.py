from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

from database import get_db_cursor
from services.pycoin_service import PyCoinError, get_economy_settings


MAX_ADMIN_AMOUNT = 1_000_000
MAX_BALANCE = 2_000_000_000


class EconomyAdminError(Exception):
    pass


def _clean_reason(value: str) -> str:
    reason = (value or "Ajustement administrateur").strip()
    return reason[:240] or "Ajustement administrateur"


def _get_target(cursor, user_id: int):
    row = cursor.execute(
        "SELECT id,username,class_code,coins,is_bot,is_admin,is_moderator FROM users WHERE id=?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        raise EconomyAdminError("Compte introuvable.")
    if bool(row["is_bot"]):
        raise EconomyAdminError("Les bots ne possèdent pas de portefeuille administrable.")
    return row


def _insert_transaction(cursor, user_id: int, amount: int, balance: int, kind: str, details: str, related_user_id=None):
    cursor.execute(
        """INSERT INTO pycoin_transactions
           (user_id,amount,balance_after,kind,details,related_user_id)
           VALUES (?,?,?,?,?,?)""",
        (int(user_id), int(amount), int(balance), kind[:40], details[:240], related_user_id),
    )


def adjust_user_balance(user_id: int, operation: str, amount: int, reason: str, actor_id: int) -> dict:
    operation = (operation or "").strip().lower()
    amount = int(amount)
    if operation not in {"credit", "debit", "set"}:
        raise EconomyAdminError("Opération invalide : credit, debit ou set.")
    if amount < 0 or amount > MAX_ADMIN_AMOUNT:
        raise EconomyAdminError(f"Le montant doit être compris entre 0 et {MAX_ADMIN_AMOUNT:,}.".replace(",", " "))
    if operation in {"credit", "debit"} and amount == 0:
        raise EconomyAdminError("Le montant doit être supérieur à zéro.")
    reason = _clean_reason(reason)

    with get_db_cursor() as cursor:
        target = _get_target(cursor, user_id)
        old_balance = int(target["coins"] or 0)
        if operation == "credit":
            new_balance = old_balance + amount
            delta = amount
        elif operation == "debit":
            new_balance = old_balance - amount
            delta = -amount
        else:
            new_balance = amount
            delta = new_balance - old_balance
        if new_balance < 0:
            raise EconomyAdminError(f"Solde insuffisant : {old_balance} PyCoins disponibles.")
        if new_balance > MAX_BALANCE:
            raise EconomyAdminError("Le solde maximum autorisé est dépassé.")
        cursor.execute("UPDATE users SET coins=? WHERE id=?", (new_balance, int(user_id)))
        _insert_transaction(
            cursor, int(user_id), delta, new_balance,
            f"admin_{operation}", reason, int(actor_id),
        )
    return {
        "user_id": int(user_id),
        "username": target["username"],
        "old_balance": old_balance,
        "balance": new_balance,
        "delta": delta,
        "operation": operation,
        "reason": reason,
    }


def bulk_adjust(scope: str, amount: int, operation: str, reason: str, actor_id: int, class_code: str = "") -> dict:
    scope = (scope or "").strip().lower()
    operation = (operation or "credit").strip().lower()
    if scope not in {"class", "all"}:
        raise EconomyAdminError("Portée invalide : class ou all.")
    if operation not in {"credit", "debit"}:
        raise EconomyAdminError("La distribution groupée accepte credit ou debit.")
    amount = int(amount)
    if amount < 1 or amount > 100_000:
        raise EconomyAdminError("Le montant groupé doit être compris entre 1 et 100 000.")
    code = re.sub(r"\s+", "", (class_code or "").upper())[:16]
    if scope == "class" and not code:
        raise EconomyAdminError("Indique la classe concernée.")
    reason = _clean_reason(reason)

    with get_db_cursor() as cursor:
        if scope == "class":
            rows = cursor.execute(
                "SELECT id,username,coins FROM users WHERE is_bot=0 AND class_code=? COLLATE NOCASE ORDER BY username",
                (code,),
            ).fetchall()
        else:
            rows = cursor.execute(
                "SELECT id,username,coins FROM users WHERE is_bot=0 ORDER BY username"
            ).fetchall()
        if not rows:
            raise EconomyAdminError("Aucun compte ne correspond à cette distribution.")
        changed = 0
        skipped = 0
        total_delta = 0
        for row in rows:
            old = int(row["coins"] or 0)
            delta = amount if operation == "credit" else -amount
            new = old + delta
            if new < 0 or new > MAX_BALANCE:
                skipped += 1
                continue
            cursor.execute("UPDATE users SET coins=? WHERE id=?", (new, int(row["id"])))
            _insert_transaction(
                cursor, int(row["id"]), delta, new,
                f"admin_bulk_{operation}", reason, int(actor_id),
            )
            changed += 1
            total_delta += delta
    return {
        "scope": scope,
        "class_code": code or None,
        "operation": operation,
        "amount_each": amount,
        "changed": changed,
        "skipped": skipped,
        "total_delta": total_delta,
        "reason": reason,
    }


def get_dashboard(query: str = "", transaction_limit: int = 100) -> dict:
    query = (query or "").strip()
    transaction_limit = max(10, min(int(transaction_limit), 500))
    with get_db_cursor() as cursor:
        stats = cursor.execute(
            """SELECT COUNT(*) AS user_count,
                      COALESCE(SUM(coins),0) AS total_coins,
                      COALESCE(AVG(coins),0) AS average_coins,
                      COALESCE(MAX(coins),0) AS max_coins
               FROM users WHERE is_bot=0"""
        ).fetchone()
        richest = cursor.execute(
            """SELECT id,username,class_code,coins,is_admin,is_moderator
               FROM users WHERE is_bot=0 ORDER BY coins DESC,username LIMIT 10"""
        ).fetchall()
        if query:
            like = f"%{query}%"
            users = cursor.execute(
                """SELECT id,username,class_code,coins,is_admin,is_moderator,is_banned
                   FROM users WHERE is_bot=0 AND (username LIKE ? OR class_code LIKE ?)
                   ORDER BY coins DESC,username LIMIT 200""",
                (like, like),
            ).fetchall()
        else:
            users = cursor.execute(
                """SELECT id,username,class_code,coins,is_admin,is_moderator,is_banned
                   FROM users WHERE is_bot=0 ORDER BY coins DESC,username LIMIT 200"""
            ).fetchall()
        transactions = cursor.execute(
            """SELECT t.id,t.amount,t.balance_after,t.kind,t.details,t.created_at,
                      u.username,u.class_code,ru.username AS related_username
               FROM pycoin_transactions t
               JOIN users u ON u.id=t.user_id
               LEFT JOIN users ru ON ru.id=t.related_user_id
               ORDER BY t.id DESC LIMIT ?""",
            (transaction_limit,),
        ).fetchall()
        today = cursor.execute(
            """SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) AS credited,
                      ABS(COALESCE(SUM(CASE WHEN amount<0 THEN amount ELSE 0 END),0)) AS spent,
                      COUNT(*) AS operations
               FROM pycoin_transactions WHERE created_at >= datetime('now','-1 day')"""
        ).fetchone()
        promos = cursor.execute(
            """SELECT p.id,p.code,p.amount,p.max_uses,p.uses,p.active,p.expires_at,p.note,p.created_at,
                      u.username AS creator
               FROM pycoin_promo_codes p LEFT JOIN users u ON u.id=p.created_by
               ORDER BY p.id DESC LIMIT 100"""
        ).fetchall()
    return {
        "stats": {
            "users": int(stats["user_count"] or 0),
            "total_coins": int(stats["total_coins"] or 0),
            "average_coins": round(float(stats["average_coins"] or 0), 1),
            "max_coins": int(stats["max_coins"] or 0),
            "credited_24h": int(today["credited"] or 0),
            "spent_24h": int(today["spent"] or 0),
            "operations_24h": int(today["operations"] or 0),
        },
        "settings": get_economy_settings(),
        "richest": [dict(row) for row in richest],
        "users": [dict(row) for row in users],
        "transactions": [dict(row) for row in transactions],
        "promo_codes": [dict(row) for row in promos],
    }


def create_promo_code(code: str, amount: int, max_uses: int, expires_at: str, note: str, actor_id: int) -> dict:
    code = re.sub(r"[^A-Z0-9_-]", "", (code or "").upper())[:24]
    if len(code) < 3:
        raise EconomyAdminError("Le code promo doit contenir au moins 3 caractères.")
    amount = int(amount)
    max_uses = int(max_uses)
    if amount < 1 or amount > 100_000:
        raise EconomyAdminError("La récompense doit être comprise entre 1 et 100 000 PyCoins.")
    if max_uses < 1 or max_uses > 100_000:
        raise EconomyAdminError("Le nombre d'utilisations doit être compris entre 1 et 100 000.")
    expires = (expires_at or "").strip() or None
    if expires:
        try:
            datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            raise EconomyAdminError("Date d'expiration invalide.")
    with get_db_cursor() as cursor:
        try:
            cursor.execute(
                """INSERT INTO pycoin_promo_codes
                   (code,amount,max_uses,expires_at,note,created_by)
                   VALUES (?,?,?,?,?,?)""",
                (code, amount, max_uses, expires, (note or "")[:200], int(actor_id)),
            )
        except Exception as error:
            if "UNIQUE" in str(error).upper():
                raise EconomyAdminError("Ce code promo existe déjà.")
            raise
        promo_id = int(cursor.lastrowid)
        row = cursor.execute("SELECT * FROM pycoin_promo_codes WHERE id=?", (promo_id,)).fetchone()
    return dict(row)


def toggle_promo_code(promo_id: int, active: bool) -> dict:
    with get_db_cursor() as cursor:
        cursor.execute("UPDATE pycoin_promo_codes SET active=? WHERE id=?", (1 if active else 0, int(promo_id)))
        if cursor.rowcount == 0:
            raise EconomyAdminError("Code promo introuvable.")
        row = cursor.execute("SELECT * FROM pycoin_promo_codes WHERE id=?", (int(promo_id),)).fetchone()
    return dict(row)


def export_transactions_csv(limit: int = 5000) -> str:
    limit = max(1, min(int(limit), 50_000))
    with get_db_cursor() as cursor:
        rows = cursor.execute(
            """SELECT t.id,u.username,u.class_code,t.amount,t.balance_after,t.kind,t.details,
                      ru.username AS related_username,t.created_at
               FROM pycoin_transactions t JOIN users u ON u.id=t.user_id
               LEFT JOIN users ru ON ru.id=t.related_user_id
               ORDER BY t.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["id", "pseudo", "classe", "montant", "solde_apres", "type", "detail", "compte_lie", "date"])
    for row in rows:
        writer.writerow([row["id"], row["username"], row["class_code"] or "", row["amount"], row["balance_after"], row["kind"], row["details"] or "", row["related_username"] or "", row["created_at"]])
    return output.getvalue()
