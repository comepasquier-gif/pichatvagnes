#!/usr/bin/env python3
"""Créer ou promouvoir rapidement un administrateur PiChat depuis le Terminal.

Modes disponibles
=================

Mode interactif (le mot de passe reste masqué) :
    python create_admin.py

Mode rapide demandé :
    python create_admin.py user toto password totototo

Mode court :
    python create_admin.py toto totototo

Mode avec options :
    python create_admin.py --user toto --password totototo

ATTENTION : un mot de passe écrit directement dans une commande peut rester
visible dans l'historique du Terminal. Pour un mot de passe sensible, utilise
le mode interactif ou donne seulement le pseudo :
    python create_admin.py user toto
"""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import get_db_cursor, init_database  # noqa: E402
from security import hash_password  # noqa: E402


USERNAME_KEYS = {"user", "username", "utilisateur", "pseudo"}
PASSWORD_KEYS = {"password", "pass", "mdp", "motdepasse", "mot-de-passe"}


def validate_username(username: str) -> str:
    username = username.strip()
    if len(username) < 3:
        raise ValueError("Le nom d'utilisateur doit contenir au moins 3 caractères.")
    if len(username) > 50:
        raise ValueError("Le nom d'utilisateur est trop long (50 caractères maximum).")
    if any(ch.isspace() for ch in username):
        raise ValueError("Le nom d'utilisateur ne doit pas contenir d'espace.")
    return username


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    if len(password) > 128:
        raise ValueError("Le mot de passe est trop long (128 caractères maximum).")
    return password


def ask_username() -> str:
    while True:
        try:
            return validate_username(input("Nom du nouvel administrateur : "))
        except ValueError as exc:
            print(exc)


def ask_password() -> str:
    while True:
        password = getpass.getpass("Mot de passe : ")
        try:
            validate_password(password)
        except ValueError as exc:
            print(exc)
            continue
        confirmation = getpass.getpass("Confirme le mot de passe : ")
        if password != confirmation:
            print("Les deux mots de passe ne correspondent pas.")
            continue
        return password


def parse_quick_tokens(tokens: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Comprend les syntaxes `user X password Y` et `X Y`."""
    if not tokens:
        return None, None

    # Syntaxe courte : create_admin.py toto totototo
    if len(tokens) == 1 and tokens[0].lower() not in USERNAME_KEYS | PASSWORD_KEYS:
        return tokens[0], None
    if len(tokens) == 2 and tokens[0].lower() not in USERNAME_KEYS | PASSWORD_KEYS:
        return tokens[0], tokens[1]

    username: Optional[str] = None
    password: Optional[str] = None
    index = 0
    while index < len(tokens):
        key = tokens[index].lower()
        if key in USERNAME_KEYS:
            if index + 1 >= len(tokens):
                raise ValueError("Il manque le pseudo après 'user'.")
            username = tokens[index + 1]
            index += 2
            continue
        if key in PASSWORD_KEYS:
            if index + 1 >= len(tokens):
                raise ValueError("Il manque le mot de passe après 'password'.")
            password = tokens[index + 1]
            index += 2
            continue
        raise ValueError(
            f"Argument inconnu : {tokens[index]!r}. "
            "Utilise : user PSEUDO password MOT_DE_PASSE"
        )
    return username, password


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Créer ou promouvoir un administrateur PiChat.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python create_admin.py\n"
            "  python create_admin.py user toto password totototo\n"
            "  python create_admin.py toto totototo\n"
            "  python create_admin.py --user toto --password totototo\n"
        ),
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Ne demande un compte que si aucun administrateur n'existe déjà.",
    )
    parser.add_argument("--user", "--username", dest="username", help="Pseudo de l'admin.")
    parser.add_argument("--password", dest="password", help="Mot de passe de l'admin.")
    parser.add_argument(
        "quick",
        nargs="*",
        help="Syntaxe rapide : user PSEUDO password MOT_DE_PASSE, ou PSEUDO MOT_DE_PASSE.",
    )
    args = parser.parse_args()

    print("=== PiChat — ajout rapide d'un administrateur ===")
    init_database()

    if args.ensure:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM users WHERE is_admin = 1 AND is_bot = 0")
            count = int(cursor.fetchone()["n"])
        if count > 0:
            print(f"OK : {count} administrateur(s) existe(nt) déjà. Aucun changement.")
            return 0
        print("Aucun administrateur détecté : créons le premier compte admin.")

    try:
        quick_username, quick_password = parse_quick_tokens(args.quick)
        username = validate_username(args.username or quick_username) if (args.username or quick_username) else ask_username()
        raw_password = args.password if args.password is not None else quick_password
        password = validate_password(raw_password) if raw_password is not None else None
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 2

    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id, is_admin, is_bot FROM users WHERE username = ?",
            (username,),
        )
        existing = cursor.fetchone()

        if existing is not None:
            if existing["is_bot"]:
                print(f"Erreur : '{username}' est un bot et ne peut pas devenir administrateur.")
                return 1

            if password is not None:
                cursor.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, is_admin = 1,
                        is_moderator = 0, moderator_class_code = NULL
                    WHERE id = ?
                    """,
                    (hash_password(password), existing["id"]),
                )
                cursor.execute("DELETE FROM sessions WHERE user_id = ?", (existing["id"],))
                action = "mis à jour et promu administrateur" if not existing["is_admin"] else "mis à jour"
                print(f"OK : le compte '{username}' a été {action}.")
                print("Ses anciennes sessions ont été fermées.")
                return 0

            if existing["is_admin"]:
                print(f"'{username}' est déjà administrateur. Son mot de passe n'a pas été modifié.")
                return 0

            cursor.execute(
                """
                UPDATE users
                SET is_admin = 1, is_moderator = 0, moderator_class_code = NULL
                WHERE id = ?
                """,
                (existing["id"],),
            )
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (existing["id"],))
            print(f"OK : l'utilisateur existant '{username}' est maintenant administrateur.")
            print("Son mot de passe actuel a été conservé.")
            return 0

    if password is None:
        password = ask_password()

    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
                (username, hash_password(password)),
            )
    except sqlite3.IntegrityError:
        print("Erreur : ce nom d'utilisateur existe déjà.")
        return 1

    print(f"OK : administrateur '{username}' créé avec succès.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
