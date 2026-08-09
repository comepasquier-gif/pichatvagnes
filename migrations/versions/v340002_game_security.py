from __future__ import annotations

from database import get_db_cursor


def upgrade() -> None:
    with get_db_cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                achievement_key TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                unlocked_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(game_id,user_id,achievement_key),
                FOREIGN KEY(game_id) REFERENCES generated_games(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_leaderboard_entries (
                game_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY(game_id,user_id),
                FOREIGN KEY(game_id) REFERENCES generated_games(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_game_leaderboard_score ON game_leaderboard_entries(game_id,score DESC)")
