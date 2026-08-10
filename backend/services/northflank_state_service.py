"""Persistence bridge for Northflank Sandbox.

PiChat itself keeps using SQLite (zero-risk migration for the existing code).
On Northflank, the service filesystem can be replaced by a deployment.  A free
managed PostgreSQL addon therefore stores a compressed snapshot of the SQLite
DB and user uploads.  The snapshot is restored before database migrations and
updated periodically while PiChat runs.

This is intentionally a single-instance bridge for small/hobby deployments.
Do not run multiple PiChat web replicas against the same snapshot.
"""
from __future__ import annotations

import asyncio
import io
import os
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Optional

from config import DATABASE_DIR, DATABASE_PATH, UPLOADS_DIR, NORTHFLANK_MODE

try:
    import psycopg2
except Exception:  # dependency is optional outside Northflank
    psycopg2 = None

STATE_KEY = "pichat-main"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SNAPSHOT_INTERVAL = max(30, int(os.getenv("PICHAT_STATE_SNAPSHOT_SECONDS", "60") or "60"))
MAX_SNAPSHOT_MB = max(10, int(os.getenv("PICHAT_STATE_MAX_MB", "200") or "200"))


def enabled() -> bool:
    return bool(NORTHFLANK_MODE and DATABASE_URL and psycopg2 is not None)


def _connect():
    if not enabled():
        return None
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode=os.getenv("PGSSLMODE", "prefer"))


def ensure_state_table() -> None:
    if not enabled():
        return
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pichat_state_snapshot (
                        state_key TEXT PRIMARY KEY,
                        payload BYTEA NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        app_version TEXT
                    )
                    """
                )
    finally:
        conn.close()


def _safe_tar_members(tar: tarfile.TarFile):
    for member in tar.getmembers():
        name = member.name.replace("\\", "/")
        if name.startswith("/") or "../" in name or name == "..":
            raise ValueError("Archive de sauvegarde non sûre")
        yield member


def restore_latest_snapshot() -> bool:
    """Restore DB/uploads before init_database(). Returns True if restored."""
    if not enabled():
        return False
    ensure_state_table()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM pichat_state_snapshot WHERE state_key=%s", (STATE_KEY,))
            row = cur.fetchone()
        if not row:
            return False
        payload = bytes(row[0])
    finally:
        conn.close()

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # Extract only database/ and uploads/ into DATA_ROOT.
    data_root = DATABASE_DIR.parent
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        members = list(_safe_tar_members(tar))
        allowed = [m for m in members if m.name == "database" or m.name.startswith("database/") or m.name == "uploads" or m.name.startswith("uploads/")]
        tar.extractall(path=data_root, members=allowed)
    return DATABASE_PATH.exists()


def build_snapshot() -> bytes:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    data_root = DATABASE_DIR.parent
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if DATABASE_PATH.exists():
            tar.add(DATABASE_PATH, arcname="database/pichat.db", recursive=False)
        if UPLOADS_DIR.exists():
            for p in UPLOADS_DIR.rglob("*"):
                if p.is_file():
                    tar.add(p, arcname=str(Path("uploads") / p.relative_to(UPLOADS_DIR)), recursive=False)
    payload = buf.getvalue()
    if len(payload) > MAX_SNAPSHOT_MB * 1024 * 1024:
        raise RuntimeError("Snapshot PiChat trop volumineux pour le coffre Northflank")
    return payload


def save_snapshot(app_version: str = "") -> bool:
    if not enabled() or not DATABASE_PATH.exists():
        return False
    ensure_state_table()
    payload = build_snapshot()
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pichat_state_snapshot(state_key,payload,created_at,app_version)
                    VALUES (%s,%s,NOW(),%s)
                    ON CONFLICT (state_key) DO UPDATE
                    SET payload=EXCLUDED.payload, created_at=NOW(), app_version=EXCLUDED.app_version
                    """,
                    (STATE_KEY, psycopg2.Binary(payload), app_version),
                )
        return True
    finally:
        conn.close()


async def snapshot_worker(app_version: str = "") -> None:
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL)
        try:
            await asyncio.to_thread(save_snapshot, app_version)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("[Northflank] snapshot impossible:", exc)
