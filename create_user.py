#!/usr/bin/env python3
"""Crée directement un compte PiChat depuis le Terminal.

Modes disponibles :
  python create_user.py
  python create_user.py toto 5C totototo
  python create_user.py user toto class 5C password totototo

Si aucun mot de passe n'est fourni en mode rapide, PiChat en génère un temporaire.
"""
from __future__ import annotations
import getpass
import secrets
import sqlite3
import string
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import get_db_cursor, init_database
from security import hash_password
from services.class_service import normalize_class_code, InvalidClassCodeError, ensure_class_room


def generated_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ask_username():
    while True:
        value = input("Nom du nouvel utilisateur : ").strip()
        if 3 <= len(value) <= 32:
            return value
        print("Le pseudo doit contenir 3 à 32 caractères.")


def ask_class():
    while True:
        try:
            return normalize_class_code(input("Classe (ex. 5C, 6C) : "))
        except InvalidClassCodeError as error:
            print(error)


def ask_password():
    while True:
        password = getpass.getpass("Mot de passe : ")
        if len(password) < 8:
            print("8 caractères minimum.")
            continue
        if password != getpass.getpass("Confirme le mot de passe : "):
            print("Les mots de passe ne correspondent pas.")
            continue
        return password


def parse_quick_args(args):
    if not args:
        return None

    # Syntaxe courte : pseudo classe [motdepasse]
    if args[0].lower() != "user":
        if len(args) < 2:
            raise ValueError("Syntaxe : python create_user.py <pseudo> <classe> [motdepasse]")
        return args[0], args[1], args[2] if len(args) > 2 else None

    # Syntaxe explicite : user toto class 5C password motdepasse
    values = {}
    index = 0
    while index < len(args):
        key = args[index].lower()
        if key not in {"user", "class", "password"} or index + 1 >= len(args):
            raise ValueError("Syntaxe : python create_user.py user <pseudo> class <classe> [password <motdepasse>]")
        values[key] = args[index + 1]
        index += 2
    if not values.get("user") or not values.get("class"):
        raise ValueError("Les champs user et class sont obligatoires.")
    return values["user"], values["class"], values.get("password")


def create_account(username: str, class_code: str, password: str) -> None:
    username = username.strip()
    if not 3 <= len(username) <= 32:
        raise ValueError("Le pseudo doit contenir 3 à 32 caractères.")
    if len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    code = normalize_class_code(class_code)
    with get_db_cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (username,password_hash,class_code,is_admin,is_bot,is_banned) VALUES (?,?,?,0,0,0)",
            (username, hash_password(password), code),
        )
        cursor.execute("DELETE FROM registration_requests WHERE lower(username)=lower(?)", (username,))
    ensure_class_room(code)
    print(f"OK : compte '{username}' créé en classe {code}.")


def main():
    print("=== PiChat — création directe d'un compte ===")
    init_database()
    try:
        parsed = parse_quick_args(sys.argv[1:])
        if parsed is None:
            username, class_code, password = ask_username(), ask_class(), ask_password()
            generated = False
        else:
            username, class_code, password = parsed
            generated = not password
            password = password or generated_password()
        create_account(username, class_code, password)
        if generated:
            print(f"Mot de passe temporaire : {password}")
            print("Copie-le maintenant : il ne sera plus affiché.")
        return 0
    except sqlite3.IntegrityError:
        print(f"Erreur : le pseudo '{parsed[0] if parsed else username}' existe déjà.")
        return 1
    except (ValueError, InvalidClassCodeError) as error:
        print("Erreur :", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
