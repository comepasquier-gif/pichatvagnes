#!/usr/bin/env python3
"""Attribue, configure ou retire un rôle de modérateur de classe.

Exemples rapides
================

Attribuer les permissions par défaut :
    python set_moderator.py user toto class 5C

Choisir les permissions :
    python set_moderator.py user toto class 5C permissions warn,mute,reports,delete

Appliquer un pack prêt à l'emploi :
    python set_moderator.py user toto class 5C pack normal

Tout autoriser (toujours limité à sa classe) :
    python set_moderator.py user toto class 5C pack super

Retirer le rôle :
    python set_moderator.py user toto remove

Sans argument, le programme passe en mode interactif.
"""
from __future__ import annotations
from typing import Optional

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import init_database, get_db_cursor  # noqa: E402
from services.class_service import (  # noqa: E402
    normalize_class_code,
    InvalidClassCodeError,
    ensure_class_room,
)
from permissions import (  # noqa: E402
    MODERATOR_PERMISSION_DEFINITIONS,
    DEFAULT_MODERATOR_PERMISSIONS,
    serialize_moderator_permissions, moderator_permissions_for_pack,
    moderator_pack_catalog, normalize_moderator_pack, DEFAULT_MODERATOR_PACK,
)

ALIASES = {
    "reports": "reports_view",
    "signalements": "reports_view",
    "resolve": "reports_resolve",
    "resoudre": "reports_resolve",
    "delete": "messages_delete",
    "supprimer": "messages_delete",
    "warn": "users_warn",
    "avertir": "users_warn",
    "mute": "users_mute",
    "kick": "users_kick",
    "expulser": "users_kick",
    "tempban": "users_tempban",
    "ban": "users_ban",
    "unban": "users_unban",
    "notes": "notes_manage",
    "history": "history_view",
    "historique": "history_view",
    "slowmode": "slowmode_manage",
    "automod": "automod_review",
}


def parse_quick_tokens(tokens: list[str]) -> dict:
    result: dict[str, object] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i].strip()
        key = token.lower()
        if key in {"remove", "retirer", "off"}:
            result["remove"] = True
            i += 1
            continue
        if key in {"user", "username", "pseudo"}:
            if i + 1 >= len(tokens):
                raise ValueError("Il manque le pseudo après 'user'.")
            result["username"] = tokens[i + 1]
            i += 2
            continue
        if key in {"class", "classe"}:
            if i + 1 >= len(tokens):
                raise ValueError("Il manque la classe après 'class'.")
            result["class_code"] = tokens[i + 1]
            i += 2
            continue
        if key in {"pack", "profil", "modele", "modèle"}:
            if i + 1 >= len(tokens):
                raise ValueError("Il manque le nom après 'pack'.")
            result["pack"] = tokens[i + 1]
            i += 2
            continue
        if key in {"permissions", "permission", "perms"}:
            if i + 1 >= len(tokens):
                raise ValueError("Il manque la liste après 'permissions'.")
            result["permissions"] = tokens[i + 1]
            i += 2
            continue
        # Syntaxe courte : pseudo classe [permissions]
        if "username" not in result:
            result["username"] = token
        elif "class_code" not in result:
            result["class_code"] = token
        elif "permissions" not in result and "pack" not in result:
            if normalize_moderator_pack(token):
                result["pack"] = token
            else:
                result["permissions"] = token
        else:
            raise ValueError(f"Argument inconnu : {token}")
        i += 1
    return result


def parse_permissions(raw: Optional[str]) -> list[str]:
    if raw is None or not raw.strip() or raw.strip().lower() in {"default", "defaut", "standard"}:
        return sorted(DEFAULT_MODERATOR_PERMISSIONS)
    lowered = raw.strip().lower()
    if lowered in {"all", "tout", "toutes"}:
        return sorted(MODERATOR_PERMISSION_DEFINITIONS)
    if lowered in {"none", "aucune", "rien"}:
        return []

    selected: list[str] = []
    for part in raw.replace(";", ",").split(","):
        key = part.strip().lower()
        if not key:
            continue
        key = ALIASES.get(key, key)
        if key not in MODERATOR_PERMISSION_DEFINITIONS:
            raise ValueError(
                f"Permission inconnue : {part.strip()}. "
                "Utilise 'list' pour voir les permissions."
            )
        if key not in selected:
            selected.append(key)
    return sorted(selected)


def print_packs() -> None:
    print("\nPacks de modération disponibles :")
    for pack in moderator_pack_catalog():
        print(f"  - {pack['key']:<8} {pack['label']:<13} {pack['permission_count']} permissions")
        print(f"             {pack['description']}")
    print("\nAlias français : petit, normal, super")


def print_permissions() -> None:
    print("\nPermissions disponibles :")
    for key, label in MODERATOR_PERMISSION_DEFINITIONS.items():
        default = " [défaut]" if key in DEFAULT_MODERATOR_PERMISSIONS else ""
        print(f"  - {key:<22} {label}{default}")
    print("\nAlias rapides : warn,mute,kick,tempban,ban,unban,reports,resolve,delete,notes,history,slowmode,automod")


def main() -> int:
    parser = argparse.ArgumentParser(description="Configurer un modérateur PiChat.")
    parser.add_argument("quick", nargs="*")
    parser.add_argument("--user", "--username", dest="username")
    parser.add_argument("--class", "--classe", dest="class_code")
    parser.add_argument("--permissions", "--perms", dest="permissions")
    parser.add_argument("--pack", dest="pack")
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--list", action="store_true", help="Afficher les permissions disponibles.")
    parser.add_argument("--packs", action="store_true", help="Afficher les packs disponibles.")
    args = parser.parse_args()

    if args.packs or (args.quick and args.quick[0].lower() in {"packs", "pack-list", "packs-list"}):
        print_packs()
        return 0
    if args.list or (args.quick and args.quick[0].lower() == "list"):
        print_permissions()
        print_packs()
        return 0

    try:
        quick = parse_quick_tokens(args.quick)
    except ValueError as exc:
        print("Erreur :", exc)
        return 2

    print("=== PiChat — permissions du modérateur ===")
    init_database()

    username = (args.username or quick.get("username") or "").strip()
    if not username:
        username = input("Pseudo du compte : ").strip()

    remove = bool(args.remove or quick.get("remove"))
    with get_db_cursor() as cursor:
        user = cursor.execute(
            "SELECT id,username,class_code,is_admin,is_bot,is_moderator,moderator_class_code "
            "FROM users WHERE username=?",
            (username,),
        ).fetchone()
        if user is None:
            print("Erreur : compte introuvable.")
            return 1
        if user["is_admin"] or user["is_bot"]:
            print("Erreur : ce compte est protégé.")
            return 1

        if not args.quick and not args.remove:
            action = input("Action [A=attribuer/configurer / R=retirer] : ").strip().upper()
            remove = action == "R"
            if action not in {"A", "R"}:
                print("Action inconnue.")
                return 1

        if remove:
            cursor.execute(
                "UPDATE users SET is_moderator=0, moderator_class_code=NULL, moderator_permissions='' WHERE id=?",
                (user["id"],),
            )
            cursor.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            print(f"OK : {username} n'est plus modérateur.")
            return 0

    raw_class = str(args.class_code or quick.get("class_code") or "").strip()
    if not raw_class:
        raw_class = input(
            f"Classe à modérer [{user['moderator_class_code'] or user['class_code'] or 'ex. 5C'}] : "
        ).strip() or (user["moderator_class_code"] or user["class_code"] or "")
    try:
        class_code = normalize_class_code(raw_class)
    except InvalidClassCodeError as exc:
        print("Erreur :", exc)
        return 1

    raw_pack = args.pack or quick.get("pack")
    raw_permissions = args.permissions or quick.get("permissions")
    if raw_pack and raw_permissions:
        print("Erreur : choisis soit un pack, soit une liste de permissions personnalisée.")
        return 2
    if raw_pack is None and raw_permissions is None and not args.quick:
        print_packs()
        raw_pack = input(f"Pack [{DEFAULT_MODERATOR_PACK}] : ").strip() or DEFAULT_MODERATOR_PACK
    try:
        if raw_pack:
            pack = normalize_moderator_pack(str(raw_pack))
            if not pack:
                raise ValueError("Pack inconnu. Utilise --packs pour afficher la liste.")
            permissions = moderator_permissions_for_pack(pack)
        else:
            pack = None
            permissions = parse_permissions(str(raw_permissions) if raw_permissions is not None else None)
    except ValueError as exc:
        print("Erreur :", exc)
        return 2

    with get_db_cursor() as cursor:
        cursor.execute(
            "UPDATE users SET is_admin=0,is_moderator=1,moderator_class_code=?,class_code=?,moderator_permissions=? WHERE id=?",
            (class_code, class_code, serialize_moderator_permissions(permissions), user["id"]),
        )
        cursor.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
    ensure_class_room(class_code)

    print(f"OK : {username} est modérateur de {class_code} avec {len(permissions)} permission(s).")
    if pack:
        print(f"Pack appliqué : {pack}")
    print("Le compte doit se reconnecter.")
    for permission in permissions:
        print("  ✓", MODERATOR_PERMISSION_DEFINITIONS[permission])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
