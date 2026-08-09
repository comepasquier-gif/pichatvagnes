#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from database import init_database
from services.test_lab_service import create_batch, delete_all_active_batches, delete_batch, diagnostics, list_batches


def print_credentials(result):
    print("\nLot créé :", result["batch_code"])
    print("Mot de passe commun :", result["password"])
    print("\nPseudo | Classe | Rôle")
    print("-" * 58)
    for item in result["credentials"]:
        print("%-28s | %-6s | %s" % (item["username"], item["class_code"], item["role"]))
    print("\nImportant : le mot de passe n'est pas stocké en clair. Copie cette liste maintenant.")


def main():
    parser = argparse.ArgumentParser(description="PiChat 2.1.5 — Laboratoire de test")
    sub = parser.add_subparsers(dest="action", required=True)

    create = sub.add_parser("create", help="Créer un lot de comptes de test")
    create.add_argument("--accounts", type=int, default=20)
    create.add_argument("--prefix", default="test")
    create.add_argument("--password", default="PiChatTest2026!")
    create.add_argument("--no-samples", action="store_true")
    create.add_argument("--no-staff", action="store_true")
    create.add_argument("--admin-id", type=int, default=1)

    clean = sub.add_parser("clean", help="Supprimer les données de test")
    clean.add_argument("--batch", type=int)
    sub.add_parser("status", help="Afficher les lots et le diagnostic")

    args = parser.parse_args()
    init_database()

    if args.action == "create":
        result = create_batch(
            admin_id=args.admin_id,
            account_count=args.accounts,
            prefix=args.prefix,
            password=args.password,
            sample_data=not args.no_samples,
            include_staff=not args.no_staff,
        )
        print_credentials(result)
    elif args.action == "clean":
        result = delete_batch(args.batch) if args.batch else delete_all_active_batches()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"batches": list_batches(), "diagnostics": diagnostics()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
