from __future__ import annotations

from database import get_db_cursor, is_postgres


def _columns(c, table: str) -> set[str]:
    c.execute("PRAGMA table_info(%s)" % table)
    return {str(r["name"]) for r in c.fetchall()}


def upgrade() -> None:
    with get_db_cursor() as c:
        users = _columns(c, "users")
        if "is_owner" not in users:
            c.execute("ALTER TABLE users ADD COLUMN is_owner INTEGER NOT NULL DEFAULT 0")
        if "is_test_account" not in users:
            c.execute("ALTER TABLE users ADD COLUMN is_test_account INTEGER NOT NULL DEFAULT 0")

        c.execute("""
            CREATE TABLE IF NOT EXISTS instance_settings (
                id INTEGER PRIMARY KEY CHECK (id=1),
                instance_name TEXT NOT NULL DEFAULT 'PiChat',
                setup_completed INTEGER NOT NULL DEFAULT 0,
                security_level TEXT NOT NULL DEFAULT 'standard',
                registration_mode TEXT NOT NULL DEFAULT 'approval',
                theme TEXT NOT NULL DEFAULT 'pichat-dark',
                custom_theme_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        c.execute("INSERT OR IGNORE INTO instance_settings(id) VALUES (1)")

        blob_type = "BYTEA" if is_postgres() else "BLOB"
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS file_objects (
                object_key TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT NOT NULL,
                data {blob_type},
                storage_backend TEXT NOT NULL DEFAULT 'database',
                external_url TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_file_objects_created ON file_objects(created_at)")

        c.execute(f"""
            CREATE TABLE IF NOT EXISTS backup_archives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                archive_data {blob_type},
                storage_backend TEXT NOT NULL DEFAULT 'database',
                external_url TEXT NOT NULL DEFAULT '',
                integrity_status TEXT NOT NULL DEFAULT 'ok',
                label TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS api_integrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                encrypted_api_key TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                last_test_status TEXT NOT NULL DEFAULT 'never',
                last_test_message TEXT NOT NULL DEFAULT '',
                last_test_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_api_integrations_provider ON api_integrations(provider,enabled)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT '',
                ip_hash TEXT NOT NULL DEFAULT '',
                success INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_recent ON login_attempts(created_at,username,ip_hash)")
