from __future__ import annotations

import importlib
from pathlib import Path

from database import get_db_cursor

VERSIONS = [
    ("340001", "migrations.versions.v340001_online_core"),
    ("340002", "migrations.versions.v340002_game_security"),
    ("340003", "migrations.versions.v340003_setup_hardening"),
]


def _ensure_version_table() -> None:
    with get_db_cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


def applied_versions() -> list[str]:
    _ensure_version_table()
    with get_db_cursor() as c:
        return [str(r["version"]) for r in c.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]


def apply_migrations() -> list[str]:
    _ensure_version_table()
    applied = set(applied_versions())
    done = []
    for version, module_name in VERSIONS:
        if version in applied:
            continue
        module = importlib.import_module(module_name)
        module.upgrade()
        with get_db_cursor() as c:
            c.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        done.append(version)
    return done


if __name__ == "__main__":
    print("Applied:", ", ".join(apply_migrations()) or "none")
