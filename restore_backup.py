#!/usr/bin/env python3
"""Restaure une sauvegarde créée par backup.py.

Par sécurité :
1. le ZIP est validé avant toute modification ;
2. une sauvegarde automatique de l'état actuel est créée avant restauration ;
3. seuls database/pichat.db et uploads/ sont restaurés.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from backup import BACKUPS_DIR, DATABASE_PATH, PROJECT_ROOT, UPLOADS_DIR, FRIENDLY_URL_CONFIG, create_backup


def _validate_member_name(name: str) -> None:
    """Empêche les chemins absolus et les '../' (zip-slip)."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Chemin dangereux dans le ZIP : {name}")


def _read_manifest(archive: zipfile.ZipFile) -> dict:
    try:
        raw = archive.read("backup_manifest.json")
    except KeyError as exc:
        raise ValueError("Ce ZIP n'est pas une sauvegarde PiChat valide (manifeste absent).") from exc

    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("format") != "pichat-backup" or manifest.get("format_version") != 1:
        raise ValueError("Format de sauvegarde PiChat inconnu ou incompatible.")
    return manifest


def restore_backup(backup_zip: Path, assume_yes: bool = False) -> None:
    backup_zip = backup_zip.expanduser().resolve()
    if not backup_zip.is_file():
        raise FileNotFoundError(f"Sauvegarde introuvable : {backup_zip}")

    with zipfile.ZipFile(backup_zip, "r") as archive:
        for member in archive.infolist():
            _validate_member_name(member.filename)
        manifest = _read_manifest(archive)

        db_expected = bool(manifest.get("database_included"))
        names = set(archive.namelist())
        if db_expected and "database/pichat.db" not in names:
            raise ValueError("Sauvegarde incomplète : database/pichat.db est absent.")

        print("=== PiChat — restauration ===")
        print(f"Sauvegarde : {backup_zip.name}")
        print(f"Créée le : {manifest.get('created_at', 'date inconnue')}")
        counts = manifest.get("table_counts") or {}
        print(
            "Contenu annoncé : "
            f"{counts.get('users', 0)} compte(s), "
            f"{counts.get('bots', 0)} bot(s), "
            f"{counts.get('rooms', 0)} salon(s), "
            f"{counts.get('messages', 0) + counts.get('private_messages', 0)} message(s), "
            f"{manifest.get('upload_file_count', 0)} fichier(s) uploadé(s)."
        )
        print("ATTENTION : la base et les uploads actuels vont être remplacés.")
        print("Arrête PiChat avec Ctrl+C avant de continuer.")

        if not assume_yes:
            answer = input("Restaurer cette sauvegarde ? Tape OUI pour confirmer : ").strip()
            if answer != "OUI":
                print("Restauration annulée.")
                return

        # Sauvegarde de secours de l'état actuel avant tout écrasement.
        safety_backup = create_backup(quiet=True)
        print(f"Sauvegarde de sécurité créée : {safety_backup}")

        with tempfile.TemporaryDirectory(prefix="pichat_restore_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)

            if db_expected:
                db_bytes = archive.read("database/pichat.db")
                tmp_db = tmp_dir / "pichat.db"
                tmp_db.write_bytes(db_bytes)

                DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
                # Nettoyer les fichiers WAL/SHM d'une ancienne exécution avant
                # de remplacer la base restaurée. Le serveur doit être arrêté.
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(DATABASE_PATH) + suffix)
                    if sidecar.exists():
                        sidecar.unlink()

                # Remplacement atomique autant que possible sur le même disque.
                staged_db = DATABASE_PATH.with_suffix(".db.restore_tmp")
                shutil.copy2(tmp_db, staged_db)
                staged_db.replace(DATABASE_PATH)

            # Restaurer aussi le nom d'URL conviviale s'il existe dans le backup.
            if "config/friendly_url.json" in names:
                FRIENDLY_URL_CONFIG.write_bytes(archive.read("config/friendly_url.json"))

            # Restaurer les uploads exactement comme dans le backup.
            staged_uploads = tmp_dir / "uploads"
            staged_uploads.mkdir(parents=True, exist_ok=True)
            for member in archive.infolist():
                if not member.filename.startswith("uploads/") or member.is_dir():
                    continue
                rel = PurePosixPath(member.filename).relative_to("uploads")
                target = staged_uploads.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

            if UPLOADS_DIR.exists():
                shutil.rmtree(UPLOADS_DIR)
            shutil.copytree(staged_uploads, UPLOADS_DIR)

    print("OK : restauration terminée.")
    print("Tu peux maintenant relancer PiChat.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaurer les données PiChat depuis un ZIP de sauvegarde.")
    parser.add_argument("backup", type=Path, help="Chemin vers PiChat_backup_....zip")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmer automatiquement la restauration (à utiliser avec prudence)",
    )
    args = parser.parse_args()

    try:
        restore_backup(args.backup, assume_yes=args.yes)
    except Exception as exc:
        print(f"ERREUR : restauration impossible : {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
