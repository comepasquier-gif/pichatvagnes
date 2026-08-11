#!/usr/bin/env python3
"""Migre une base PiChat SQLite 3.x vers DATABASE_URL PostgreSQL.

Usage :
  DATABASE_URL='postgresql://...' \
  python scripts/migrate_sqlite_to_postgres.py /chemin/pichat.db --replace

Le dossier uploads/ historique est détecté automatiquement quand il se trouve
à côté du dossier database/. Il peut aussi être indiqué avec --uploads-dir.
Les sessions, liens d'assistance, tentatives de connexion et secrets API ne
sont volontairement pas migrés.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

EXCLUDE = {
    "sqlite_sequence", "schema_migrations", "backup_archives", "login_attempts",
    "sessions", "support_access_links", "support_sessions", "api_integrations",
}


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _guess_uploads(sqlite_db: Path) -> Path | None:
    candidates = [sqlite_db.parent / "uploads", sqlite_db.parent.parent / "uploads"]
    for path in candidates:
        if path.is_dir():
            return path
    return None


def _migrate_uploads(uploads_dir: Path | None) -> dict:
    if not uploads_dir or not uploads_dir.is_dir():
        return {"detected": False, "imported": 0, "skipped": 0, "rewritten_messages": 0, "rewritten_avatars": 0}

    from database import get_db_cursor
    from services.storage_service import put_object, StorageError

    url_map: dict[str, str] = {}
    imported = skipped = 0
    for path in sorted(p for p in uploads_dir.rglob("*") if p.is_file() and p.name != ".gitkeep"):
        rel = path.relative_to(uploads_dir).as_posix()
        try:
            data = path.read_bytes()
            stored = put_object(
                data,
                path.name,
                mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                None,
                "legacy",
            )
            # PiChat 3.3 servait principalement /uploads/<nom>. Garde aussi le chemin relatif.
            url_map["/uploads/" + rel] = stored["url"]
            url_map.setdefault("/uploads/" + path.name, stored["url"])
            imported += 1
        except (OSError, StorageError, ValueError) as exc:
            skipped += 1
            print(f"uploads: ignoré {rel}: {exc}")

    rewritten_messages = rewritten_avatars = 0
    if url_map:
        with get_db_cursor() as c:
            try:
                rows = c.execute("SELECT id,metadata_json FROM messages WHERE message_type='file'").fetchall()
            except Exception:
                rows = []
            for row in rows:
                try:
                    meta = json.loads(row["metadata_json"] or "{}")
                except Exception:
                    continue
                old = str(meta.get("url") or "")
                if old in url_map:
                    meta["url"] = url_map[old]
                    c.execute("UPDATE messages SET metadata_json=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), row["id"]))
                    rewritten_messages += 1
            try:
                users = c.execute("SELECT id,avatar_path FROM users WHERE avatar_path IS NOT NULL AND avatar_path<>''").fetchall()
            except Exception:
                users = []
            for row in users:
                old = str(row["avatar_path"] or "")
                if old in url_map:
                    c.execute("UPDATE users SET avatar_path=? WHERE id=?", (url_map[old], row["id"]))
                    rewritten_avatars += 1

    return {
        "detected": True,
        "path": str(uploads_dir),
        "imported": imported,
        "skipped": skipped,
        "rewritten_messages": rewritten_messages,
        "rewritten_avatars": rewritten_avatars,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlite_db", type=Path)
    ap.add_argument("--replace", action="store_true", help="vide les tables de destination avant la copie")
    ap.add_argument("--uploads-dir", type=Path, help="dossier uploads/ de l'ancienne instance")
    args = ap.parse_args()

    if not args.sqlite_db.exists():
        raise SystemExit("Base SQLite introuvable.")
    if not os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        raise SystemExit("DATABASE_URL PostgreSQL requis.")

    from database import init_database, get_db_cursor, is_postgres
    if not is_postgres():
        raise SystemExit("PiChat ne détecte pas PostgreSQL.")
    init_database()

    src = sqlite3.connect(args.sqlite_db)
    src.row_factory = sqlite3.Row
    src_tables = [
        r["name"] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ) if r["name"] not in EXCLUDE
    ]
    with get_db_cursor() as c:
        dst_tables = {
            r["table_name"] for r in c.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ).fetchall()
        }
    common = [t for t in src_tables if t in dst_tables]

    if args.replace and common:
        # TRUNCATE en une seule commande gère correctement les FK PostgreSQL.
        with get_db_cursor() as c:
            c.execute("TRUNCATE TABLE " + ",".join(qident(t) for t in common) + " CASCADE")

    copied = {}
    for table in common:
        src_cols = [r["name"] for r in src.execute(f"PRAGMA table_info({qident(table)})")]
        if not src_cols:
            continue
        with get_db_cursor() as c:
            dst_cols = {
                r["column_name"] for r in c.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
                    (table,),
                ).fetchall()
            }
        cols = [x for x in src_cols if x in dst_cols]
        if not cols:
            continue
        rows = src.execute(f"SELECT {','.join(qident(x) for x in cols)} FROM {qident(table)}").fetchall()
        if not rows:
            copied[table] = 0
            continue
        placeholders = ",".join("?" for _ in cols)
        colsql = ",".join(qident(x) for x in cols)
        n = 0
        with get_db_cursor() as c:
            for row in rows:
                try:
                    c.execute(
                        f"INSERT INTO {qident(table)} ({colsql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                        tuple(row[x] for x in cols),
                    )
                    n += 1
                except Exception as exc:
                    raise RuntimeError(f"Échec table {table}: {exc}") from exc
        copied[table] = n
        print(f"{table}: {n}")

    # Recalage des séquences id PostgreSQL après copie d'identifiants explicites.
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for table in common:
                cur.execute("SELECT pg_get_serial_sequence(%s,%s)", (table, "id"))
                row = cur.fetchone()
                seq = row[0] if row else None
                if seq:
                    cur.execute(f"SELECT COALESCE(MAX(id),0) FROM {qident(table)}")
                    mx = int(cur.fetchone()[0] or 0)
                    cur.execute("SELECT setval(%s,%s,%s)", (seq, max(mx, 1), bool(mx)))
    finally:
        conn.close()
        src.close()

    uploads = args.uploads_dir or _guess_uploads(args.sqlite_db)
    upload_result = _migrate_uploads(uploads)
    print("Uploads :", json.dumps(upload_result, ensure_ascii=False))
    print("Migration terminée. Comptes/messages/PyCoins/profils/amis/salons/jeux/réglages conservés.")
    print("Sessions et secrets ne sont volontairement pas migrés : reconnecte les utilisateurs et reconfigure les API.")


if __name__ == "__main__":
    main()
