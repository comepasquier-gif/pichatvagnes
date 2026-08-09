from __future__ import annotations

from database import get_db_cursor


def upgrade() -> None:
    with get_db_cursor() as c:
        # Une instance ne doit avoir qu'un seul propriétaire. Les autres admins
        # restent possibles, mais /setup ne peut pas créer deux owners en course.
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_owner ON users(is_owner) WHERE is_owner=1")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_test_account ON users(is_test_account)")
