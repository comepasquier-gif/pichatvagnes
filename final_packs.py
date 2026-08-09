#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from database import init_database
from services.final_packs_service import auto_backup_status, get_final_pack_settings, run_auto_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Packs finaux PiChat 2.2")
    parser.add_argument("action", choices=["status", "backup"])
    args = parser.parse_args()
    init_database()
    if args.action == "backup":
        result = run_auto_backup(force=True)
        print("Backup créé :", result["name"] if result else "aucun")
        return 0
    print(json.dumps({"settings": get_final_pack_settings(), "backups": auto_backup_status()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
