"""Database compatibility layer for PiChat 3.4.

PiChat keeps its original parameterized SQLite-flavoured SQL so existing
features remain compatible. In online mode DATABASE_URL switches the exact
same services to PostgreSQL through a small, explicit compatibility adapter.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Optional

from config import DATABASE_PATH, DATABASE_DIR, DATABASE_URL, DATABASE_BACKEND

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except Exception:  # pragma: no cover - local SQLite installs may omit psycopg2
    psycopg2 = None
    DictCursor = None


SQLITE_INTEGRITY_ERROR = sqlite3.IntegrityError
POSTGRES_INTEGRITY_ERROR = getattr(getattr(psycopg2, "IntegrityError", None), "__class__", Exception)
IntegrityError = (sqlite3.IntegrityError, psycopg2.IntegrityError) if psycopg2 else (sqlite3.IntegrityError,)


def is_postgres() -> bool:
    return DATABASE_BACKEND == "postgresql"


def _replace_qmarks(sql: str) -> str:
    out, quoted, quote = [], False, ""
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quoted:
            out.append(ch)
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(sql[i + 1]); i += 1
                else:
                    quoted = False
            i += 1; continue
        if ch in ("'", '"'):
            quoted, quote = True, ch; out.append(ch)
        elif ch == "?":
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _pg_now_expr(modifier: str = "") -> str:
    expr = "CURRENT_TIMESTAMP"
    modifier = (modifier or "").strip()
    if modifier:
        m = re.fullmatch(r"([+-])\s*(\d+)\s*(minute|minutes|hour|hours|day|days)", modifier, re.I)
        if m:
            sign, amount, unit = m.groups()
            expr = f"({expr} {sign} INTERVAL '{int(amount)} {unit.lower()}')"
    return "to_char((%s AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')" % expr


def translate_sql(sql: str) -> str:
    q = sql
    q = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", q, flags=re.I)
    q = re.sub(r"COLLATE\s+NOCASE", "", q, flags=re.I)
    # SQLite UTC text timestamps -> PostgreSQL UTC text timestamps (preserves old comparison semantics).
    q = re.sub(r"datetime\(\s*'now'\s*,\s*'([^']+)'\s*\)", lambda m: _pg_now_expr(m.group(1)), q, flags=re.I)
    q = re.sub(r"datetime\(\s*'now'\s*\)", _pg_now_expr(), q, flags=re.I)
    # PiChat stores timestamps as UTC text for backward compatibility. SQLite's
    # datetime(?) wrapper is only a normaliser here; PostgreSQL can compare the
    # canonical YYYY-MM-DD HH:MM:SS strings directly.
    q = re.sub(r"datetime\(\s*\?\s*\)", "?", q, flags=re.I)
    q = re.sub(r"datetime\(\s*%s\s*\)", "%s", q, flags=re.I)
    # SQLite date(text_column) used by daily limits -> first 10 ISO characters.
    q = re.sub(r"\bdate\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)", r"substring(\1 from 1 for 10)", q, flags=re.I)
    # SQLite MIN/MAX accept two scalar arguments; PostgreSQL uses LEAST/GREATEST.
    # PiChat only uses these simple two-argument forms (no nested function calls).
    q = re.sub(r"\bMIN\(\s*([^(),]+?)\s*,\s*([^()]+?)\s*\)", r"LEAST(\1,\2)", q, flags=re.I)
    q = re.sub(r"\bMAX\(\s*([^(),]+?)\s*,\s*([^()]+?)\s*\)", r"GREATEST(\1,\2)", q, flags=re.I)
    # SQLite's case-insensitive LIKE is closest to PostgreSQL ILIKE for PiChat's text search.
    q = re.sub(r"\bLIKE\b", "ILIKE", q, flags=re.I)
    ignore = bool(re.search(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", q, flags=re.I))
    q = re.sub(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", q, flags=re.I)
    q = _replace_qmarks(q)
    if ignore and "ON CONFLICT" not in q.upper():
        q = q.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return q


class PostgresCursorCompat:
    def __init__(self, connection: "PostgresConnectionCompat"):
        self.connection = connection
        self._cursor = connection._raw.cursor(cursor_factory=DictCursor)
        self._virtual_rows = None
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, sql: str, params: Any = ()):
        self._virtual_rows = None
        self.lastrowid = None
        pragma = re.fullmatch(r"\s*PRAGMA\s+table_info\(([^)]+)\)\s*;?\s*", sql, re.I)
        if pragma:
            table = pragma.group(1).strip().strip('"').strip("'")
            self._cursor.execute(
                "SELECT column_name AS name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position",
                (table,),
            )
            self._virtual_rows = self._cursor.fetchall()
            self.rowcount = len(self._virtual_rows)
            return self
        q = translate_sql(sql)
        is_insert = bool(re.match(r"\s*INSERT\s+INTO\s+", q, re.I))
        table = None
        if is_insert:
            m = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", q, re.I)
            table = m.group(1) if m else None
            if table and "RETURNING" not in q.upper() and self.connection.table_has_id(table):
                q = q.rstrip().rstrip(";") + " RETURNING id"
        self._cursor.execute(q, tuple(params or ()))
        self.rowcount = self._cursor.rowcount
        if is_insert and table and "RETURNING id" in q:
            row = self._cursor.fetchone()
            if row is not None:
                try: self.lastrowid = int(row[0])
                except Exception: self.lastrowid = row[0]
        return self

    def executemany(self, sql: str, seq):
        q = translate_sql(sql)
        self._cursor.executemany(q, seq)
        self.rowcount = self._cursor.rowcount
        return self

    def fetchone(self):
        if self._virtual_rows is not None:
            return self._virtual_rows.pop(0) if self._virtual_rows else None
        return self._cursor.fetchone()

    def fetchall(self):
        if self._virtual_rows is not None:
            rows, self._virtual_rows = self._virtual_rows, []
            return rows
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        self._cursor.close()


class PostgresConnectionCompat:
    def __init__(self):
        if psycopg2 is None:
            raise RuntimeError("psycopg2-binary est requis pour PostgreSQL")
        self._raw = psycopg2.connect(DATABASE_URL, connect_timeout=15)
        self._id_cache = {}

    def table_has_id(self, table: str) -> bool:
        if table not in self._id_cache:
            cur = self._raw.cursor()
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s AND column_name='id' LIMIT 1",
                (table,),
            )
            self._id_cache[table] = bool(cur.fetchone())
            cur.close()
        return self._id_cache[table]

    def cursor(self):
        return PostgresCursorCompat(self)

    def execute(self, sql: str, params: Any = ()):
        c = self.cursor(); return c.execute(sql, params)

    def commit(self): self._raw.commit()
    def rollback(self): self._raw.rollback()
    def close(self): self._raw.close()


def get_connection():
    if is_postgres():
        return PostgresConnectionCompat()
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def get_db_cursor():
    connection = get_connection()
    cursor = connection.cursor()
    try:
        yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        try: cursor.close()
        except Exception: pass
        connection.close()


def init_database() -> None:
    """
    Crée les tables de l'application si elles n'existent pas encore.

    "IF NOT EXISTS" permet de relancer cette fonction sans risque
    (par exemple à chaque démarrage du serveur) sans effacer les données
    existantes.
    """

    # S'assure que le dossier "database/" existe avant de créer le fichier .db
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    with get_db_cursor() as cursor:

        # -------------------------------------------------------------
        # Table des utilisateurs
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT NOT NULL UNIQUE,
                password_hash   TEXT NOT NULL,
                avatar_path     TEXT,
                status_message  TEXT DEFAULT '',
                is_admin        INTEGER NOT NULL DEFAULT 0,
                is_bot          INTEGER NOT NULL DEFAULT 0,
                class_code      TEXT,
                is_banned       INTEGER NOT NULL DEFAULT 0,
                banned_at       TEXT,
                banned_reason   TEXT DEFAULT '',
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # -------------------------------------------------------------
        # Table des salons (rooms)
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                class_code  TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # -------------------------------------------------------------
        # Table des messages envoyés dans un salon
        # -------------------------------------------------------------
        # ON DELETE CASCADE : si un utilisateur ou un salon est supprimé,
        # ses messages associés le sont aussi automatiquement.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id     INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # Table des messages privés (entre deux utilisateurs)
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS private_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id   INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (sender_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (receiver_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # Table des sessions (utilisateurs actuellement connectés)
        # -------------------------------------------------------------
        # On stocke les tokens de session en base plutôt que d'utiliser
        # un JWT auto-suffisant : cela permet de vraiment "déconnecter"
        # un utilisateur (en supprimant la ligne), ce qu'un JWT classique
        # ne permet pas facilement.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # Migration légère : ajoute la colonne "is_admin" si la base
        # existait déjà avant son introduction (ex: sur une installation
        # faite avant le Milestone salons/admin). Sans ce bloc, les
        # utilisateurs ayant déjà une base .db plus ancienne auraient une
        # erreur au premier démarrage après mise à jour du code.
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = [row["name"] for row in cursor.fetchall()]

        if "is_admin" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )

        if "is_bot" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN is_bot INTEGER NOT NULL DEFAULT 0"
            )

        if "class_code" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN class_code TEXT"
            )

        if "is_banned" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0"
            )

        if "banned_at" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN banned_at TEXT"
            )

        if "banned_reason" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN banned_reason TEXT DEFAULT ''"
            )

        if "is_moderator" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN is_moderator INTEGER NOT NULL DEFAULT 0"
            )

        if "moderator_class_code" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN moderator_class_code TEXT"
            )

        if "moderator_permissions" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN moderator_permissions TEXT NOT NULL DEFAULT ''"
            )

        if "grade_title" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN grade_title TEXT DEFAULT ''"
            )

        if "grade_color" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN grade_color TEXT DEFAULT ''"
            )

        if "grade_visibility" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN grade_visibility TEXT NOT NULL DEFAULT 'full'"
            )

        if "profile_bio" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN profile_bio TEXT DEFAULT ''"
            )

        if "profile_color" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN profile_color TEXT DEFAULT '#5865f2'"
            )

        if "xp" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN xp INTEGER NOT NULL DEFAULT 0"
            )

        if "coins" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN coins INTEGER NOT NULL DEFAULT 100"
            )

        if "game_wins" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN game_wins INTEGER NOT NULL DEFAULT 0"
            )

        if "game_losses" not in existing_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN game_losses INTEGER NOT NULL DEFAULT 0"
            )

        # -------------------------------------------------------------
        # Migration des salons : rattachement facultatif à une classe
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(rooms)")
        room_columns = [row["name"] for row in cursor.fetchall()]
        if "class_code" not in room_columns:
            cursor.execute("ALTER TABLE rooms ADD COLUMN class_code TEXT")


        # -------------------------------------------------------------
        # Messages enrichis : cartes de jeu, sondages, événements...
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(messages)")
        message_columns = [row["name"] for row in cursor.fetchall()]
        if "message_type" not in message_columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN message_type TEXT NOT NULL DEFAULT 'text'")
        if "metadata_json" not in message_columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")

        # -------------------------------------------------------------
        # Demandes d'inscription soumises à validation administrateur
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS registration_requests (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT NOT NULL UNIQUE,
                password_hash   TEXT,
                class_code      TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                admin_note      TEXT DEFAULT '',
                reviewed_by     INTEGER,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed_at     TEXT,
                FOREIGN KEY (reviewed_by) REFERENCES users (id) ON DELETE SET NULL
            )
        """)

        # -------------------------------------------------------------
        # Table des bots locaux
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL UNIQUE,
                response_template TEXT NOT NULL,
                enabled           INTEGER NOT NULL DEFAULT 1,
                created_at        TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # Configuration de l'IA intégrée (clé API conservée hors base)
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_settings (
                id              INTEGER PRIMARY KEY CHECK (id = 1),
                enabled         INTEGER NOT NULL DEFAULT 1,
                provider        TEXT NOT NULL DEFAULT 'local',
                model           TEXT NOT NULL DEFAULT 'gpt-5.6',
                trigger_name    TEXT NOT NULL DEFAULT 'PiAI',
                instructions    TEXT NOT NULL DEFAULT 'Tu es PiAI, assistant utile et bienveillant de PiChat. Réponds en français de façon concise et adaptée à des élèves.',
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO ai_settings (id) VALUES (1)
        """)

        # -------------------------------------------------------------
        # Réactions sur les messages (style Discord)
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_reactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id  INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                emoji       TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(message_id, user_id, emoji),
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # Signalements de messages
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id  INTEGER NOT NULL,
                reporter_id INTEGER NOT NULL,
                reason      TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'open',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(message_id, reporter_id),
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
                FOREIGN KEY (reporter_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # Duels / mini-jeu de combat
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS duels (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id         INTEGER NOT NULL,
                message_id      INTEGER,
                challenger_id   INTEGER NOT NULL,
                opponent_id     INTEGER NOT NULL,
                challenger_hp   INTEGER NOT NULL DEFAULT 100,
                opponent_hp     INTEGER NOT NULL DEFAULT 100,
                turn_user_id    INTEGER,
                status          TEXT NOT NULL DEFAULT 'pending',
                winner_id       INTEGER,
                log_json        TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE SET NULL,
                FOREIGN KEY (challenger_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (opponent_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (turn_user_id) REFERENCES users (id) ON DELETE SET NULL,
                FOREIGN KEY (winner_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)

        # -------------------------------------------------------------
        # Réglages de fonctionnalités v0.9
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_settings (
                id                  INTEGER PRIMARY KEY CHECK (id = 1),
                games_enabled       INTEGER NOT NULL DEFAULT 1,
                tutor_enabled       INTEGER NOT NULL DEFAULT 1,
                reactions_enabled   INTEGER NOT NULL DEFAULT 1,
                reports_enabled     INTEGER NOT NULL DEFAULT 1,
                member_panel        INTEGER NOT NULL DEFAULT 1,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO feature_settings (id) VALUES (1)")

        # -------------------------------------------------------------
        # Réglages de modération / filtre de langage
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moderation_settings (
                id              INTEGER PRIMARY KEY CHECK (id = 1),
                profanity_enabled INTEGER NOT NULL DEFAULT 1,
                profanity_words TEXT NOT NULL DEFAULT 'merde,putain,connard,connasse,salope,enculé,encule,nique,ntm,fdp,bâtard,batard',
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO moderation_settings (id) VALUES (1)")

        # -------------------------------------------------------------
        # Personnalisation globale de l'interface
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ui_settings (
                id                  INTEGER PRIMARY KEY CHECK (id = 1),
                app_name            TEXT NOT NULL DEFAULT 'PiChat',
                app_subtitle        TEXT NOT NULL DEFAULT 'Campus Messenger',
                welcome_message     TEXT NOT NULL DEFAULT 'Bienvenue sur PiChat',
                logo_text           TEXT NOT NULL DEFAULT 'P',
                theme_preset        TEXT NOT NULL DEFAULT 'neon',
                primary_color       TEXT NOT NULL DEFAULT '#7c5cff',
                secondary_color     TEXT NOT NULL DEFAULT '#37b5ff',
                accent_color        TEXT NOT NULL DEFAULT '#22d3a6',
                density             TEXT NOT NULL DEFAULT 'comfortable',
                show_bot_hint       INTEGER NOT NULL DEFAULT 1,
                show_diagnostic     INTEGER NOT NULL DEFAULT 1,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO ui_settings (id) VALUES (1)")

        # -------------------------------------------------------------
        # Journal des actions d'administration
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id    INTEGER,
                action      TEXT NOT NULL,
                target      TEXT DEFAULT '',
                details     TEXT DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (actor_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)

        # -------------------------------------------------------------
        # Modération avancée v1.0.3
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(users)")
        moderation_user_columns = [row["name"] for row in cursor.fetchall()]
        if "muted_until" not in moderation_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN muted_until TEXT")
        if "mute_reason" not in moderation_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN mute_reason TEXT DEFAULT ''")
        if "ban_until" not in moderation_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN ban_until TEXT")
        if "warning_count" not in moderation_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN warning_count INTEGER NOT NULL DEFAULT 0")

        cursor.execute("PRAGMA table_info(rooms)")
        moderation_room_columns = [row["name"] for row in cursor.fetchall()]
        if "slow_mode_seconds" not in moderation_room_columns:
            cursor.execute("ALTER TABLE rooms ADD COLUMN slow_mode_seconds INTEGER NOT NULL DEFAULT 0")

        cursor.execute("PRAGMA table_info(message_reports)")
        report_columns = [row["name"] for row in cursor.fetchall()]
        if "handled_by" not in report_columns:
            cursor.execute("ALTER TABLE message_reports ADD COLUMN handled_by INTEGER")
        if "handled_at" not in report_columns:
            cursor.execute("ALTER TABLE message_reports ADD COLUMN handled_at TEXT")
        if "resolution_note" not in report_columns:
            cursor.execute("ALTER TABLE message_reports ADD COLUMN resolution_note TEXT DEFAULT ''")

        cursor.execute("PRAGMA table_info(moderation_settings)")
        advanced_setting_columns = [row["name"] for row in cursor.fetchall()]
        advanced_settings = {
            "duplicate_enabled": "INTEGER NOT NULL DEFAULT 1",
            "duplicate_window_seconds": "INTEGER NOT NULL DEFAULT 45",
            "similarity_enabled": "INTEGER NOT NULL DEFAULT 1",
            "similarity_ratio": "REAL NOT NULL DEFAULT 0.88",
            "similarity_min_length": "INTEGER NOT NULL DEFAULT 12",
            "similarity_window_seconds": "INTEGER NOT NULL DEFAULT 90",
            "burst_enabled": "INTEGER NOT NULL DEFAULT 1",
            "burst_count": "INTEGER NOT NULL DEFAULT 5",
            "burst_window_seconds": "INTEGER NOT NULL DEFAULT 4",
            "uppercase_enabled": "INTEGER NOT NULL DEFAULT 1",
            "uppercase_min_length": "INTEGER NOT NULL DEFAULT 14",
            "uppercase_ratio": "REAL NOT NULL DEFAULT 0.82",
            "rate_limit_count": "INTEGER NOT NULL DEFAULT 12",
            "rate_limit_window_seconds": "INTEGER NOT NULL DEFAULT 20",
            "repeated_char_limit": "INTEGER NOT NULL DEFAULT 14",
            "punctuation_limit": "INTEGER NOT NULL DEFAULT 12",
            "emoji_limit": "INTEGER NOT NULL DEFAULT 16",
            "word_repeat_limit": "INTEGER NOT NULL DEFAULT 7",
            "cooldown_base_seconds": "INTEGER NOT NULL DEFAULT 2",
            "cooldown_max_seconds": "INTEGER NOT NULL DEFAULT 30",
            "rapid_count": "INTEGER NOT NULL DEFAULT 3",
            "rapid_window_seconds": "REAL NOT NULL DEFAULT 1.8"
        }
        for column_name, column_definition in advanced_settings.items():
            if column_name not in advanced_setting_columns:
                cursor.execute(f"ALTER TABLE moderation_settings ADD COLUMN {column_name} {column_definition}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moderation_actions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id    INTEGER,
                target_id   INTEGER,
                action      TEXT NOT NULL,
                reason      TEXT DEFAULT '',
                duration_minutes INTEGER,
                room_id     INTEGER,
                message_id  INTEGER,
                expires_at  TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (actor_id) REFERENCES users (id) ON DELETE SET NULL,
                FOREIGN KEY (target_id) REFERENCES users (id) ON DELETE SET NULL,
                FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE SET NULL,
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moderator_notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id   INTEGER NOT NULL,
                author_id   INTEGER,
                note        TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (target_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)

        # -------------------------------------------------------------
        # AutoModo v1.0.5
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS automod_settings (
                id                  INTEGER PRIMARY KEY CHECK (id = 1),
                enabled             INTEGER NOT NULL DEFAULT 1,
                announce_actions    INTEGER NOT NULL DEFAULT 1,
                exempt_staff        INTEGER NOT NULL DEFAULT 1,
                profanity_mode      TEXT NOT NULL DEFAULT 'blur',
                link_mode           TEXT NOT NULL DEFAULT 'warn',
                max_links           INTEGER NOT NULL DEFAULT 2,
                max_mentions        INTEGER NOT NULL DEFAULT 5,
                warn_points         INTEGER NOT NULL DEFAULT 1,
                mute_points         INTEGER NOT NULL DEFAULT 4,
                mute_minutes        INTEGER NOT NULL DEFAULT 10,
                temp_ban_points     INTEGER NOT NULL DEFAULT 8,
                temp_ban_minutes    INTEGER NOT NULL DEFAULT 60,
                point_window_minutes INTEGER NOT NULL DEFAULT 1440,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO automod_settings (id) VALUES (1)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS automod_incidents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                room_id         INTEGER,
                message_id      INTEGER,
                rule            TEXT NOT NULL,
                points          INTEGER NOT NULL DEFAULT 1,
                action          TEXT NOT NULL DEFAULT 'warning',
                content_preview TEXT DEFAULT '',
                detail          TEXT DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'open',
                review_note     TEXT DEFAULT '',
                reviewed_by     INTEGER,
                reviewed_at     TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE SET NULL,
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE SET NULL,
                FOREIGN KEY (reviewed_by) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_automod_user_date ON automod_incidents(user_id,created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_automod_status ON automod_incidents(status,created_at)")

        # -------------------------------------------------------------
        # PiChat 1.1.3 : accès assistance, PyCoins, serveurs personnels
        # et cartes de code Python générées par IA.
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(rooms)")
        room_v113_columns = [row["name"] for row in cursor.fetchall()]
        room_v113_migrations = {
            "room_kind": "TEXT NOT NULL DEFAULT 'standard'",
            "owner_user_id": "INTEGER",
            "description": "TEXT DEFAULT ''",
            "icon": "TEXT DEFAULT '💬'",
            "invite_code": "TEXT"
        }
        for column_name, column_definition in room_v113_migrations.items():
            if column_name not in room_v113_columns:
                cursor.execute(f"ALTER TABLE rooms ADD COLUMN {column_name} {column_definition}")

        cursor.execute("UPDATE rooms SET room_kind='standard' WHERE room_kind IS NULL OR room_kind='' ")

        cursor.execute("PRAGMA table_info(feature_settings)")
        feature_v113_columns = [row["name"] for row in cursor.fetchall()]
        feature_v113_migrations = {
            "pycoins_enabled": "INTEGER NOT NULL DEFAULT 1",
            "custom_servers_enabled": "INTEGER NOT NULL DEFAULT 1",
            "code_lab_enabled": "INTEGER NOT NULL DEFAULT 1",
            "support_access_enabled": "INTEGER NOT NULL DEFAULT 1"
        }
        for column_name, column_definition in feature_v113_migrations.items():
            if column_name not in feature_v113_columns:
                cursor.execute(f"ALTER TABLE feature_settings ADD COLUMN {column_name} {column_definition}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_server_members (
                server_id   INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                member_role TEXT NOT NULL DEFAULT 'member',
                joined_at   TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (server_id, user_id),
                FOREIGN KEY (server_id) REFERENCES rooms (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pycoin_transactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                amount          INTEGER NOT NULL,
                balance_after   INTEGER NOT NULL,
                kind            TEXT NOT NULL,
                details         TEXT DEFAULT '',
                related_user_id INTEGER,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (related_user_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pycoin_user_date ON pycoin_transactions(user_id, created_at)")

        # PiChat 1.1.4 : paramètres administrables de l'économie et codes promo.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS economy_settings (
                id                          INTEGER PRIMARY KEY CHECK (id = 1),
                daily_reward                INTEGER NOT NULL DEFAULT 25,
                transfer_max                INTEGER NOT NULL DEFAULT 500,
                transfers_enabled           INTEGER NOT NULL DEFAULT 1,
                server_creation_cost        INTEGER NOT NULL DEFAULT 100,
                server_customization_cost   INTEGER NOT NULL DEFAULT 10,
                code_cost                   INTEGER NOT NULL DEFAULT 5,
                max_owned_servers           INTEGER NOT NULL DEFAULT 3,
                updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO economy_settings (id) VALUES (1)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pycoin_promo_codes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT NOT NULL UNIQUE,
                amount      INTEGER NOT NULL,
                max_uses    INTEGER NOT NULL DEFAULT 1,
                uses        INTEGER NOT NULL DEFAULT 0,
                active      INTEGER NOT NULL DEFAULT 1,
                expires_at  TEXT,
                note        TEXT DEFAULT '',
                created_by  INTEGER,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pycoin_promo_redemptions (
                promo_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                redeemed_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (promo_id, user_id),
                FOREIGN KEY (promo_id) REFERENCES pycoin_promo_codes (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_pycoin_rewards (
                user_id         INTEGER PRIMARY KEY,
                last_claim_date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS support_access_links (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash      TEXT NOT NULL UNIQUE,
                admin_id        INTEGER NOT NULL,
                target_user_id  INTEGER NOT NULL,
                reason          TEXT DEFAULT '',
                expires_at      TEXT NOT NULL,
                used_at         TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (admin_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (target_user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS support_sessions (
                token           TEXT PRIMARY KEY,
                admin_id        INTEGER NOT NULL,
                target_user_id  INTEGER NOT NULL,
                expires_at      TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (token) REFERENCES sessions (token) ON DELETE CASCADE,
                FOREIGN KEY (admin_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (target_user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_lab_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                room_id     INTEGER NOT NULL,
                prompt      TEXT NOT NULL,
                title       TEXT DEFAULT '',
                provider    TEXT NOT NULL DEFAULT 'local',
                status      TEXT NOT NULL DEFAULT 'created',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # PiChat 2.0 : espaces / établissements multi-communautés
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(users)")
        v2_user_columns = [row["name"] for row in cursor.fetchall()]
        if "active_space_id" not in v2_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN active_space_id INTEGER")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spaces (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                slug            TEXT NOT NULL UNIQUE,
                icon            TEXT NOT NULL DEFAULT '🏫',
                description     TEXT DEFAULT '',
                owner_user_id   INTEGER,
                invite_code     TEXT NOT NULL UNIQUE,
                visibility      TEXT NOT NULL DEFAULT 'invite',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS space_members (
                space_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                role            TEXT NOT NULL DEFAULT 'member',
                joined_at       TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (space_id, user_id),
                FOREIGN KEY (space_id) REFERENCES spaces(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS space_rooms (
                space_id        INTEGER NOT NULL,
                room_id         INTEGER NOT NULL UNIQUE,
                category        TEXT NOT NULL DEFAULT 'SALONS',
                position        INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (space_id, room_id),
                FOREIGN KEY (space_id) REFERENCES spaces(id) ON DELETE CASCADE,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_space_members_user ON space_members(user_id,space_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_space_rooms_space ON space_rooms(space_id,position)")

        # Espace central créé automatiquement lors d'une migration.
        central = cursor.execute("SELECT id FROM spaces WHERE slug='pichat-central'").fetchone()
        if central is None:
            cursor.execute("""
                INSERT INTO spaces (name,slug,icon,description,invite_code,visibility)
                VALUES ('PiChat Central','pichat-central','🏠','Espace principal créé automatiquement lors du passage à PiChat 2.0.','CENTRAL','invite')
            """)
            central_id = cursor.lastrowid
        else:
            central_id = int(central["id"])

        # Tous les comptes et salons historiques sont conservés dans Central.
        cursor.execute("""
            INSERT OR IGNORE INTO space_members (space_id,user_id,role)
            SELECT ?,id,CASE WHEN is_admin=1 THEN 'admin' ELSE 'member' END FROM users WHERE is_bot=0
        """, (central_id,))
        cursor.execute("""
            INSERT OR IGNORE INTO space_rooms (space_id,room_id,category,position)
            SELECT ?,id,CASE WHEN class_code IS NULL THEN 'GÉNÉRAL' ELSE 'CLASSES' END,id
            FROM rooms WHERE COALESCE(room_kind,'standard')!='custom'
        """, (central_id,))
        cursor.execute("""
            UPDATE users SET active_space_id=?
            WHERE active_space_id IS NULL AND is_bot=0
        """, (central_id,))

        # -------------------------------------------------------------
        # PiChat 2.1 : messagerie avancée, PiTutor+, RPG et déploiement
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(messages)")
        v21_message_columns = [row["name"] for row in cursor.fetchall()]
        for column_name, column_definition in {
            "reply_to_id": "INTEGER",
            "edited_at": "TEXT",
            "is_pinned": "INTEGER NOT NULL DEFAULT 0",
            "pinned_by": "INTEGER",
            "pinned_at": "TEXT",
        }.items():
            if column_name not in v21_message_columns:
                cursor.execute(f"ALTER TABLE messages ADD COLUMN {column_name} {column_definition}")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_room_content ON messages(room_id, content)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_room_pinned ON messages(room_id, is_pinned, id)")

        cursor.execute("PRAGMA table_info(private_messages)")
        private_columns = [row["name"] for row in cursor.fetchall()]
        for column_name, column_definition in {
            "reply_to_id": "INTEGER",
            "edited_at": "TEXT",
            "read_at": "TEXT",
            "deleted_by_sender": "INTEGER NOT NULL DEFAULT 0",
            "deleted_by_receiver": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if column_name not in private_columns:
                cursor.execute(f"ALTER TABLE private_messages ADD COLUMN {column_name} {column_definition}")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_private_pair_date ON private_messages(sender_id, receiver_id, id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_private_unread ON private_messages(receiver_id, read_at, id)")

        cursor.execute("PRAGMA table_info(feature_settings)")
        v21_feature_columns = [row["name"] for row in cursor.fetchall()]
        for column_name, column_definition in {
            "direct_messages_enabled": "INTEGER NOT NULL DEFAULT 1",
            "message_edit_enabled": "INTEGER NOT NULL DEFAULT 1",
            "pins_enabled": "INTEGER NOT NULL DEFAULT 1",
            "search_enabled": "INTEGER NOT NULL DEFAULT 1",
            "tutor_plus_enabled": "INTEGER NOT NULL DEFAULT 1",
            "rpg_enabled": "INTEGER NOT NULL DEFAULT 0",
            "gaming_profiles_enabled": "INTEGER NOT NULL DEFAULT 1",
            "internet_mode_enabled": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if column_name not in v21_feature_columns:
                cursor.execute(f"ALTER TABLE feature_settings ADD COLUMN {column_name} {column_definition}")

        cursor.execute("PRAGMA table_info(users)")
        v21_user_columns = [row["name"] for row in cursor.fetchall()]
        for column_name, column_definition in {
            "rpg_class": "TEXT NOT NULL DEFAULT 'aventurier'",
            "rpg_level": "INTEGER NOT NULL DEFAULT 1",
            "rpg_xp": "INTEGER NOT NULL DEFAULT 0",
            "rpg_energy": "INTEGER NOT NULL DEFAULT 100",
            "rpg_hp": "INTEGER NOT NULL DEFAULT 100",
            "rpg_attack": "INTEGER NOT NULL DEFAULT 12",
            "rpg_defense": "INTEGER NOT NULL DEFAULT 6",
            "rpg_agility": "INTEGER NOT NULL DEFAULT 8",
            "rpg_last_daily": "TEXT",
        }.items():
            if column_name not in v21_user_columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tutor_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                subject         TEXT NOT NULL,
                mode            TEXT NOT NULL,
                prompt          TEXT NOT NULL,
                student_answer  TEXT DEFAULT '',
                tutor_answer    TEXT NOT NULL,
                provider        TEXT NOT NULL DEFAULT 'local',
                favorite        INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tutor_history_user ON tutor_history(user_id, id DESC)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_sets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                title           TEXT NOT NULL,
                subject         TEXT NOT NULL DEFAULT 'Général',
                kind            TEXT NOT NULL DEFAULT 'flashcards',
                content_json    TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_attempts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                set_id          INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                score           INTEGER NOT NULL DEFAULT 0,
                total           INTEGER NOT NULL DEFAULT 0,
                answers_json    TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (set_id) REFERENCES study_sets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("PRAGMA table_info(duels)")
        v21_duel_columns = [row["name"] for row in cursor.fetchall()]
        for column_name, column_definition in {
            "challenger_guard": "INTEGER NOT NULL DEFAULT 0",
            "opponent_guard": "INTEGER NOT NULL DEFAULT 0",
            "challenger_energy": "INTEGER NOT NULL DEFAULT 3",
            "opponent_energy": "INTEGER NOT NULL DEFAULT 3",
        }.items():
            if column_name not in v21_duel_columns:
                cursor.execute(f"ALTER TABLE duels ADD COLUMN {column_name} {column_definition}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rpg_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                code            TEXT NOT NULL UNIQUE,
                name            TEXT NOT NULL,
                description     TEXT DEFAULT '',
                item_type       TEXT NOT NULL DEFAULT 'consumable',
                rarity          TEXT NOT NULL DEFAULT 'common',
                stat_key        TEXT DEFAULT '',
                stat_value      INTEGER NOT NULL DEFAULT 0,
                price           INTEGER NOT NULL DEFAULT 25,
                icon            TEXT NOT NULL DEFAULT '🎒',
                active          INTEGER NOT NULL DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rpg_inventory (
                user_id         INTEGER NOT NULL,
                item_id         INTEGER NOT NULL,
                quantity        INTEGER NOT NULL DEFAULT 0,
                equipped        INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES rpg_items(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rpg_quests (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT NOT NULL,
                description     TEXT DEFAULT '',
                objective       TEXT NOT NULL DEFAULT 'messages',
                target          INTEGER NOT NULL DEFAULT 5,
                reward_xp       INTEGER NOT NULL DEFAULT 25,
                reward_coins    INTEGER NOT NULL DEFAULT 10,
                icon            TEXT NOT NULL DEFAULT '📜',
                active          INTEGER NOT NULL DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rpg_quest_progress (
                user_id         INTEGER NOT NULL,
                quest_id        INTEGER NOT NULL,
                progress        INTEGER NOT NULL DEFAULT 0,
                completed_at    TEXT,
                claimed_at      TEXT,
                PRIMARY KEY (user_id, quest_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (quest_id) REFERENCES rpg_quests(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rpg_world_bosses (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                icon            TEXT NOT NULL DEFAULT '🐉',
                max_hp          INTEGER NOT NULL DEFAULT 5000,
                current_hp      INTEGER NOT NULL DEFAULT 5000,
                reward_coins    INTEGER NOT NULL DEFAULT 250,
                reward_xp       INTEGER NOT NULL DEFAULT 500,
                status          TEXT NOT NULL DEFAULT 'active',
                starts_at       TEXT NOT NULL DEFAULT (datetime('now')),
                ends_at         TEXT,
                defeated_at     TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rpg_boss_attacks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                boss_id         INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                damage          INTEGER NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (boss_id) REFERENCES rpg_world_bosses(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deployment_settings (
                id                  INTEGER PRIMARY KEY CHECK (id = 1),
                public_url          TEXT NOT NULL DEFAULT '',
                allowed_hosts       TEXT NOT NULL DEFAULT 'localhost,127.0.0.1',
                proxy_headers       INTEGER NOT NULL DEFAULT 0,
                https_enabled       INTEGER NOT NULL DEFAULT 0,
                internet_ready      INTEGER NOT NULL DEFAULT 0,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO deployment_settings (id) VALUES (1)")

        # -------------------------------------------------------------
        # PiChat 2.1.2 : badges et profils gaming (remplace l'interface RPG)
        # -------------------------------------------------------------
        cursor.execute("UPDATE feature_settings SET rpg_enabled=0 WHERE id=1")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_game_profiles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                game_key        TEXT NOT NULL,
                game_name       TEXT NOT NULL,
                username        TEXT NOT NULL,
                platform        TEXT NOT NULL DEFAULT '',
                is_public       INTEGER NOT NULL DEFAULT 1,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, game_key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_game_profiles_user ON user_game_profiles(user_id,sort_order,id)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS badge_definitions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                code            TEXT NOT NULL UNIQUE,
                name            TEXT NOT NULL,
                description     TEXT NOT NULL DEFAULT '',
                icon            TEXT NOT NULL DEFAULT '🏅',
                color           TEXT NOT NULL DEFAULT '#f0b232',
                category        TEXT NOT NULL DEFAULT 'custom',
                is_system       INTEGER NOT NULL DEFAULT 0,
                is_active       INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                user_id         INTEGER NOT NULL,
                badge_id        INTEGER NOT NULL,
                awarded_by      INTEGER,
                reason          TEXT NOT NULL DEFAULT '',
                awarded_at      TEXT NOT NULL DEFAULT (datetime('now')),
                showcased       INTEGER NOT NULL DEFAULT 1,
                display_order   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id,badge_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (badge_id) REFERENCES badge_definitions(id) ON DELETE CASCADE,
                FOREIGN KEY (awarded_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_badges_user ON user_badges(user_id,showcased,display_order)")
        starter_badges = [
            ('member','Membre','Compte membre de PiChat','💬','#5865f2','role',1),
            ('admin','Administrateur','Administrateur de PiChat','🛡️','#ed4245','role',1),
            ('moderator','Modérateur','Modérateur de PiChat','🔨','#57f287','role',1),
            ('gamer','Gamer','A renseigné au moins un pseudo de jeu','🎮','#37b5ff','gaming',1),
            ('multi-gamer','Multi-gamer','A renseigné quatre jeux ou plus','🕹️','#b06cff','gaming',1),
            ('profile-complete','Profil complet','Statut, bio et pseudo de jeu complétés','✨','#f0b232','profile',1),
        ]
        for badge in starter_badges:
            cursor.execute("""
                INSERT OR IGNORE INTO badge_definitions
                    (code,name,description,icon,color,category,is_system,is_active)
                VALUES (?,?,?,?,?,?,?,1)
            """, badge)

        # Contenu RPG historique conservé en base pour ne perdre aucune donnée.
        # L'interface RPG est désactivée et remplacée par les profils gaming.
        starter_items = [
            ('small-potion','Petite potion','Rend 25 PV','consumable','common','hp',25,20,'🧪'),
            ('iron-sword','Épée de fer','Ajoute 3 points d’attaque','equipment','uncommon','attack',3,90,'🗡️'),
            ('wood-shield','Bouclier de bois','Ajoute 2 points de défense','equipment','common','defense',2,65,'🛡️'),
            ('swift-boots','Bottes rapides','Ajoute 2 points d’agilité','equipment','rare','agility',2,140,'🥾'),
        ]
        for item in starter_items:
            cursor.execute("""INSERT OR IGNORE INTO rpg_items
                (code,name,description,item_type,rarity,stat_key,stat_value,price,icon)
                VALUES (?,?,?,?,?,?,?,?,?)""", item)
        starter_quests = [
            ('Premier message','Envoie 5 messages dans PiChat','messages',5,25,15,'💬'),
            ('Sociable','Ajoute 3 réactions à des messages','reactions',3,30,20,'❤️'),
            ('Combattant','Termine un duel','duels',1,50,25,'⚔️'),
            ('Élève motivé','Utilise PiTutor 3 fois','tutor',3,45,20,'📚'),
        ]
        for quest in starter_quests:
            cursor.execute("""INSERT INTO rpg_quests(title,description,objective,target,reward_xp,reward_coins,icon)
                SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM rpg_quests WHERE title=?)""", (*quest, quest[0]))
        if cursor.execute("SELECT 1 FROM rpg_world_bosses WHERE status='active' LIMIT 1").fetchone() is None:
            cursor.execute("""INSERT INTO rpg_world_bosses(name,icon,max_hp,current_hp,reward_coins,reward_xp,status)
                VALUES('Dragon du Cache','🐉',5000,5000,250,500,'active')""")

        # -------------------------------------------------------------
        # PiChat 2.1.3 : Arcade, défis quotidiens et classements
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(feature_settings)")
        feature_213_columns = [row["name"] for row in cursor.fetchall()]
        if "arcade_enabled" not in feature_213_columns:
            cursor.execute("ALTER TABLE feature_settings ADD COLUMN arcade_enabled INTEGER NOT NULL DEFAULT 1")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arcade_settings (
                id                      INTEGER PRIMARY KEY CHECK (id = 1),
                enabled                 INTEGER NOT NULL DEFAULT 1,
                rewards_enabled         INTEGER NOT NULL DEFAULT 1,
                rewarded_plays_per_day  INTEGER NOT NULL DEFAULT 5,
                daily_coin_cap          INTEGER NOT NULL DEFAULT 30,
                daily_challenge_coins   INTEGER NOT NULL DEFAULT 25,
                daily_challenge_xp      INTEGER NOT NULL DEFAULT 40,
                updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO arcade_settings (id) VALUES (1)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arcade_sessions (
                id              TEXT PRIMARY KEY,
                user_id         INTEGER NOT NULL,
                game_key        TEXT NOT NULL,
                state_json      TEXT NOT NULL DEFAULT '{}',
                started_at      TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at      TEXT NOT NULL,
                completed_at    TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_arcade_sessions_user ON arcade_sessions(user_id,expires_at)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arcade_scores (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                game_key        TEXT NOT NULL,
                score           INTEGER NOT NULL DEFAULT 0,
                result_label    TEXT NOT NULL DEFAULT '',
                details_json    TEXT NOT NULL DEFAULT '{}',
                coins_awarded   INTEGER NOT NULL DEFAULT 0,
                xp_awarded      INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_arcade_scores_user_date ON arcade_scores(user_id,created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_arcade_scores_game_score ON arcade_scores(game_key,score DESC)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arcade_user_stats (
                user_id         INTEGER NOT NULL,
                game_key        TEXT NOT NULL,
                best_score      INTEGER NOT NULL DEFAULT 0,
                best_label      TEXT NOT NULL DEFAULT '',
                plays           INTEGER NOT NULL DEFAULT 0,
                wins            INTEGER NOT NULL DEFAULT 0,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id,game_key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arcade_daily_claims (
                user_id         INTEGER NOT NULL,
                challenge_date  TEXT NOT NULL,
                game_key        TEXT NOT NULL,
                score           INTEGER NOT NULL DEFAULT 0,
                claimed_at      TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id,challenge_date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        arcade_badges = [
            ('arcade-player','Joueur d\'arcade','A terminé son premier mini-jeu','🕹️','#37b5ff','arcade',1),
            ('arcade-regular','Habitué de l\'arcade','A terminé 25 parties','🎟️','#b06cff','arcade',1),
            ('arcade-master','Maître de l\'arcade','A terminé 100 parties','👑','#f0b232','arcade',1),
            ('reflex-ace','Réflexe éclair','Réaction inférieure à 250 ms','⚡','#fee75c','arcade',1),
            ('memory-master','Mémoire de maître','Mémoire terminée en 12 coups ou moins','🧠','#57f287','arcade',1),
            ('quiz-star','Sans-faute','Cinq bonnes réponses au Quiz express','🌟','#f0b232','arcade',1),
            ('click-frenzy','Doigt turbo','Au moins 55 clics en dix secondes','🔥','#ed4245','arcade',1),
            ('tactical-player','Tacticien','A battu PiBot au morpion','⭕','#5865f2','arcade',1),
        ]
        for badge in arcade_badges:
            cursor.execute("""
                INSERT OR IGNORE INTO badge_definitions
                    (code,name,description,icon,color,category,is_system,is_active)
                VALUES (?,?,?,?,?,?,?,1)
            """, badge)

        # -------------------------------------------------------------
        # Salon par défaut
        # -------------------------------------------------------------
        # "INSERT OR IGNORE" : n'insère la ligne que si elle n'existe pas
        # déjà (grâce à la contrainte UNIQUE sur "name"). Cela permet à
        # tout nouvel utilisateur d'avoir au moins un salon général.
        cursor.execute("""
            INSERT OR IGNORE INTO rooms (name) VALUES ('général')
        """)
        central = cursor.execute("SELECT id FROM spaces WHERE slug='pichat-central'").fetchone()
        general = cursor.execute("SELECT id FROM rooms WHERE name='général'").fetchone()
        if central is not None and general is not None:
            cursor.execute("INSERT OR IGNORE INTO space_rooms(space_id,room_id,category,position) VALUES(?,?,'GÉNÉRAL',0)", (central["id"], general["id"]))

        # -------------------------------------------------------------
        # PiChat 2.1.4 : PiGame Studio — jeux créés avec ChatGPT
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(feature_settings)")
        feature_214_columns = [row["name"] for row in cursor.fetchall()]
        if "game_studio_enabled" not in feature_214_columns:
            cursor.execute("ALTER TABLE feature_settings ADD COLUMN game_studio_enabled INTEGER NOT NULL DEFAULT 1")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_studio_settings (
                id                      INTEGER PRIMARY KEY CHECK (id = 1),
                enabled                 INTEGER NOT NULL DEFAULT 1,
                direct_api_enabled      INTEGER NOT NULL DEFAULT 0,
                require_admin_approval  INTEGER NOT NULL DEFAULT 1,
                max_games_per_user      INTEGER NOT NULL DEFAULT 8,
                updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO game_studio_settings (id) VALUES (1)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generated_games (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id        INTEGER NOT NULL,
                title           TEXT NOT NULL,
                slug            TEXT NOT NULL UNIQUE,
                description     TEXT NOT NULL DEFAULT '',
                icon            TEXT NOT NULL DEFAULT '🎮',
                source_prompt   TEXT NOT NULL DEFAULT '',
                generation_mode TEXT NOT NULL DEFAULT 'chatgpt_web',
                html_code       TEXT NOT NULL,
                css_code        TEXT NOT NULL DEFAULT '',
                js_code         TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'draft',
                safety_report   TEXT NOT NULL DEFAULT '{}',
                review_note     TEXT NOT NULL DEFAULT '',
                reviewed_by     INTEGER,
                plays           INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                published_at    TEXT,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_generated_games_status ON generated_games(status,published_at,id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_generated_games_owner ON generated_games(owner_id,id DESC)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generated_game_plays (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id     INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                played_at   TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (game_id) REFERENCES generated_games(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_generated_game_plays_game ON generated_game_plays(game_id,played_at)")

        # -------------------------------------------------------------
        # PiChat 2.1.5 : laboratoire de test administrateur
        # -------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_lab_batches (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_code      TEXT NOT NULL UNIQUE,
                created_by      INTEGER,
                account_count   INTEGER NOT NULL DEFAULT 0,
                prefix          TEXT NOT NULL DEFAULT 'test',
                sample_data     INTEGER NOT NULL DEFAULT 1,
                include_staff   INTEGER NOT NULL DEFAULT 1,
                status          TEXT NOT NULL DEFAULT 'active',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                deleted_at      TEXT,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_lab_accounts (
                batch_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL UNIQUE,
                username        TEXT NOT NULL,
                class_code      TEXT,
                role            TEXT NOT NULL DEFAULT 'player',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (batch_id,user_id),
                FOREIGN KEY (batch_id) REFERENCES test_lab_batches(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_lab_requests (
                batch_id        INTEGER NOT NULL,
                request_id      INTEGER NOT NULL UNIQUE,
                PRIMARY KEY (batch_id,request_id),
                FOREIGN KEY (batch_id) REFERENCES test_lab_batches(id) ON DELETE CASCADE,
                FOREIGN KEY (request_id) REFERENCES registration_requests(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_lab_batches_status ON test_lab_batches(status,created_at)")

        # -------------------------------------------------------------
        # PiChat 2.2.0 : packs finaux — Messages+, Social, Sessions et Maintenance
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(sessions)")
        session_columns = [row["name"] for row in cursor.fetchall()]
        if "last_seen_at" not in session_columns:
            cursor.execute("ALTER TABLE sessions ADD COLUMN last_seen_at TEXT")
        if "user_agent" not in session_columns:
            cursor.execute("ALTER TABLE sessions ADD COLUMN user_agent TEXT DEFAULT ''")
        if "ip_address" not in session_columns:
            cursor.execute("ALTER TABLE sessions ADD COLUMN ip_address TEXT DEFAULT ''")
        cursor.execute("UPDATE sessions SET last_seen_at=created_at WHERE last_seen_at IS NULL")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS final_pack_settings (
                id                          INTEGER PRIMARY KEY CHECK (id = 1),
                scheduled_messages_enabled  INTEGER NOT NULL DEFAULT 1,
                social_enabled              INTEGER NOT NULL DEFAULT 1,
                session_manager_enabled     INTEGER NOT NULL DEFAULT 1,
                auto_backup_enabled         INTEGER NOT NULL DEFAULT 0,
                scheduled_max_days          INTEGER NOT NULL DEFAULT 30,
                edit_window_minutes         INTEGER NOT NULL DEFAULT 1440,
                delete_window_minutes       INTEGER NOT NULL DEFAULT 60,
                backup_interval_hours       INTEGER NOT NULL DEFAULT 24,
                backup_retention            INTEGER NOT NULL DEFAULT 7,
                updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO final_pack_settings (id) VALUES (1)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                room_id         INTEGER NOT NULL,
                content         TEXT NOT NULL,
                reply_to_id     INTEGER,
                send_at         TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                sent_at         TEXT,
                cancelled_at    TEXT,
                sent_message_id INTEGER,
                error_message   TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
                FOREIGN KEY (reply_to_id) REFERENCES messages(id) ON DELETE SET NULL,
                FOREIGN KEY (sent_message_id) REFERENCES messages(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_due ON scheduled_messages(status,send_at,id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_user ON scheduled_messages(user_id,status,send_at)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friendships (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_low_id     INTEGER NOT NULL,
                user_high_id    INTEGER NOT NULL,
                requested_by    INTEGER NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                responded_at    TEXT,
                UNIQUE(user_low_id,user_high_id),
                CHECK(user_low_id < user_high_id),
                FOREIGN KEY (user_low_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (user_high_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_friendships_status ON friendships(status,created_at)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_blocks (
                blocker_id      INTEGER NOT NULL,
                blocked_id      INTEGER NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (blocker_id,blocked_id),
                CHECK(blocker_id != blocked_id),
                FOREIGN KEY (blocker_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_backup_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_name     TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'success',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                error_message   TEXT NOT NULL DEFAULT ''
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auto_backup_runs_date ON auto_backup_runs(created_at DESC,id DESC)")

        # -------------------------------------------------------------
        # Administrateur
        # -------------------------------------------------------------
        # Depuis la v0.9, aucun mot de passe administrateur n'est codé en dur.
        # Une installation neuve crée le premier admin via create_admin.py --ensure.
        # Les admins déjà présents dans une base migrée sont conservés.

    # PiChat 3.4: migrations are versioned and idempotent. They run only after
    # the complete legacy schema exists, preserving every 3.3 feature.
    from migrations.runner import apply_migrations
    apply_migrations()
