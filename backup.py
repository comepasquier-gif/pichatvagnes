#!/usr/bin/env python3
"""Crée une sauvegarde portable des données PiChat.

La sauvegarde contient :
- la base SQLite complète (comptes, admins, bots, salons, messages, sessions, etc.)
- le dossier uploads/ (avatars et futurs fichiers envoyés)
- un manifeste JSON décrivant la sauvegarde

Le venv n'est volontairement pas inclus : il dépend du système et doit
être recréé avec ``python3 -m venv venv`` sur une nouvelle machine.
"""

from __future__ import annotations

import os

import argparse
import json
import sqlite3
import tempfile
import zipfile
from typing import Optional
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.getenv("PICHAT_DATA_ROOT", str(PROJECT_ROOT))).expanduser()
DATABASE_PATH = DATA_ROOT / "database" / "pichat.db"
UPLOADS_DIR = DATA_ROOT / "uploads"
BACKUPS_DIR = DATA_ROOT / "backups"
FRIENDLY_URL_CONFIG = PROJECT_ROOT / "friendly_url.json"


def _table_counts(db_path: Path) -> dict[str, int]:
    """Retourne le nombre de lignes des tables connues, si elles existent."""
    counts: dict[str, int] = {}
    if not db_path.exists():
        return counts

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        for table in sorted(tables):
            # Le nom vient uniquement de sqlite_master, pas d'une saisie utilisateur.
            counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    return counts


def create_backup(output_path: Optional[Path] = None, quiet: bool = False) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_path is None:
        output_path = BACKUPS_DIR / f"PiChat_backup_{timestamp}.zip"
    else:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        raise FileExistsError(f"Le fichier existe déjà : {output_path}")

    with tempfile.TemporaryDirectory(prefix="pichat_backup_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        snapshot_db = tmp_dir / "pichat.db"
        database_included = DATABASE_PATH.exists()

        # L'API backup de SQLite produit un snapshot cohérent même si PiChat est lancé.
        if database_included:
            with sqlite3.connect(DATABASE_PATH) as source, sqlite3.connect(snapshot_db) as destination:
                source.backup(destination)

        table_counts = _table_counts(snapshot_db) if database_included else {}
        upload_files = [
            p for p in UPLOADS_DIR.rglob("*")
            if p.is_file() and p.name != ".gitkeep"
        ] if UPLOADS_DIR.exists() else []

        manifest = {
            "format": "pichat-backup",
            "format_version": 1,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "database_included": database_included,
            "database_file": "database/pichat.db" if database_included else None,
            "uploads_prefix": "uploads/",
            "upload_file_count": len(upload_files),
            "table_counts": table_counts,
            "friendly_url_config_included": FRIENDLY_URL_CONFIG.exists(),
        }

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "backup_manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )

            if database_included:
                archive.write(snapshot_db, "database/pichat.db")

            if FRIENDLY_URL_CONFIG.exists():
                archive.write(FRIENDLY_URL_CONFIG, "config/friendly_url.json")

            # Inclure .gitkeep permet aussi de recréer un dossier uploads vide.
            if UPLOADS_DIR.exists():
                for path in sorted(UPLOADS_DIR.rglob("*")):
                    if path.is_file():
                        archive.write(path, Path("uploads") / path.relative_to(UPLOADS_DIR))
            else:
                archive.writestr("uploads/.gitkeep", "")

    if not quiet:
        print("=== PiChat — sauvegarde ===")
        print(f"OK : sauvegarde créée : {output_path}")
        if database_included:
            users = table_counts.get("users", 0)
            messages = table_counts.get("messages", 0)
            private_messages = table_counts.get("private_messages", 0)
            bots = table_counts.get("bots", 0)
            rooms = table_counts.get("rooms", 0)
            print(
                "Contenu : "
                f"{users} compte(s), {bots} bot(s), {rooms} salon(s), "
                f"{messages + private_messages} message(s), {len(upload_files)} fichier(s) uploadé(s)."
            )
        else:
            print("Attention : aucune base pichat.db n'existait encore ; seuls les uploads ont été sauvegardés.")
        print("Tu peux copier ce ZIP sur un autre Windows ou Mac pour le restaurer.")

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Sauvegarder toutes les données PiChat dans un ZIP.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Chemin du ZIP à créer (par défaut : backups/PiChat_backup_DATE_HEURE.zip)",
    )
    args = parser.parse_args()

    try:
        create_backup(args.output)
    except Exception as exc:
        print(f"ERREUR : sauvegarde impossible : {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
