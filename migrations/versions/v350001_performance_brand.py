from __future__ import annotations

from database import get_db_cursor


def _columns(c, table: str) -> set[str]:
    c.execute("PRAGMA table_info(%s)" % table)
    return {str(r["name"]) for r in c.fetchall()}


def upgrade() -> None:
    """PiChat 3.5: réglages persistants de performance et de branding."""
    with get_db_cursor() as c:
        cols = _columns(c, "instance_settings")
        if "performance_mode" not in cols:
            c.execute("ALTER TABLE instance_settings ADD COLUMN performance_mode TEXT NOT NULL DEFAULT 'ultra'")
        if "target_ping_ms" not in cols:
            c.execute("ALTER TABLE instance_settings ADD COLUMN target_ping_ms INTEGER NOT NULL DEFAULT 50")
        if "brand_version" not in cols:
            c.execute("ALTER TABLE instance_settings ADD COLUMN brand_version TEXT NOT NULL DEFAULT '3.5'")
        c.execute("UPDATE instance_settings SET performance_mode='ultra', target_ping_ms=50, brand_version='3.5' WHERE id=1")
